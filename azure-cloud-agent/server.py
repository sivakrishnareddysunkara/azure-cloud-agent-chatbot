import csv
import json
import os
import time

import jwt
import requests
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.orchestrator import collect_resource_details
from config import (
    AUTH_MODE,
    AZURE_AD_AUDIENCE,
    AZURE_AD_CLIENT_ID,
    AZURE_AD_SCOPE,
    AZURE_AD_TENANT_ID,
)
from llm.explain import answer_governance_query, stream_governance_query
from tools.resource_graph import discover_public_network_resources, discover_resources

app = FastAPI(title="Azure Governance Chat")
app.mount("/static", StaticFiles(directory="web"), name="static")
app.mount("/exports", StaticFiles(directory="exports"), name="exports")

_jwks_cache = {"keys": None, "fetched_at": 0}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    resource_count: int


def _wants_public_network_excel(message: str) -> bool:
    lowered = message.lower()
    return "public network" in lowered and any(
        keyword in lowered for keyword in ("excel", "spreadsheet", "csv")
    )


def _wants_resources_export(message: str) -> bool:
    lowered = message.lower()
    return any(keyword in lowered for keyword in ("export", "excel", "spreadsheet", "csv"))


def _write_resources_csv(records):
    os.makedirs("exports", exist_ok=True)
    path = os.path.join("exports", "resources_overview.csv")
    headers = [
        "name",
        "type",
        "location",
        "resourceGroup",
        "id",
        "publicNetworkAccess",
        "privateEndpointCount",
        "encryption",
        "managedVirtualNetwork",
        "provisioned_by",
        "kind",
        "sku",
        "identity",
        "tags",
    ]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key) for key in headers}
            row["tags"] = json.dumps(row.get("tags") or {})
            row["sku"] = json.dumps(row.get("sku") or {})
            row["identity"] = json.dumps(row.get("identity") or {})
            writer.writerow(row)
    return path


def _write_public_network_csv(records):
    os.makedirs("exports", exist_ok=True)
    path = os.path.join("exports", "public_network_access.csv")
    headers = ["name", "type", "location", "resourceGroup", "id", "publicNetworkAccess"]
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for record in records:
            writer.writerow({key: record.get(key) for key in headers})
    return path


def _jwks_url():
    return f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/discovery/v2.0/keys"


def _issuer():
    return f"https://login.microsoftonline.com/{AZURE_AD_TENANT_ID}/v2.0"


def _get_jwks():
    now = time.time()
    if _jwks_cache["keys"] and now - _jwks_cache["fetched_at"] < 3600:
        return _jwks_cache["keys"]

    response = requests.get(_jwks_url(), timeout=10)
    response.raise_for_status()
    jwks = response.json()
    _jwks_cache["keys"] = jwks.get("keys", [])
    _jwks_cache["fetched_at"] = now
    return _jwks_cache["keys"]


def _verify_bearer_token(token: str):
    if not AZURE_AD_TENANT_ID:
        raise HTTPException(status_code=500, detail="Azure AD settings not configured")

    audiences = []
    if AZURE_AD_AUDIENCE:
        audiences.append(AZURE_AD_AUDIENCE)
    if AZURE_AD_CLIENT_ID:
        audiences.append(AZURE_AD_CLIENT_ID)
        audiences.append(f"api://{AZURE_AD_CLIENT_ID}")

    if not audiences:
        raise HTTPException(status_code=500, detail="Azure AD audience not configured")

    header = jwt.get_unverified_header(token)
    keys = _get_jwks()
    key = next((k for k in keys if k.get("kid") == header.get("kid")), None)
    if not key:
        raise HTTPException(status_code=401, detail="Invalid token")

    public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
    try:
        jwt.decode(
            token,
            public_key,
            algorithms=[header.get("alg", "RS256")],
            audience=audiences,
            issuer=_issuer(),
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid token") from exc


def require_auth(request: Request):
    if AUTH_MODE.lower() != "azure_ad":
        return

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    token = auth.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    _verify_bearer_token(token)


@app.get("/")
def index():
    return FileResponse("web/index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/auth/config")
def auth_config():
    audience = AZURE_AD_AUDIENCE or AZURE_AD_CLIENT_ID
    if AZURE_AD_SCOPE:
        scopes = [AZURE_AD_SCOPE]
    elif audience:
        if audience.startswith("api://"):
            scopes = [f"{audience}/.default"]
        else:
            scopes = [f"api://{audience}/.default"]
    else:
        scopes = []

    return {
        "tenant_id": AZURE_AD_TENANT_ID,
        "client_id": AZURE_AD_CLIENT_ID,
        "audience": audience,
        "scopes": scopes,
        "auth_mode": AUTH_MODE,
    }


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, _auth=Depends(require_auth)):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if _wants_public_network_excel(payload.message):
        try:
            records = discover_public_network_resources()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Resource discovery failed: {exc}") from exc

        _write_public_network_csv(records)
        response = (
            f"Created export at /exports/public_network_access.csv with {len(records)} resources "
            "that report public network access enabled."
        )
        return ChatResponse(response=response, resource_count=len(records))

    if _wants_resources_export(payload.message):
        try:
            resources = discover_resources()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Resource discovery failed: {exc}") from exc

        details = []
        for resource in resources:
            detail = collect_resource_details(resource)
            details.append(detail)

        _write_resources_csv(details)
        response = (
            f"Created export at /exports/resources_overview.csv with {len(details)} resources."
        )
        return ChatResponse(response=response, resource_count=len(details))

    try:
        resources = discover_resources()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resource discovery failed: {exc}") from exc

    details = []
    for resource in resources:
        detail = collect_resource_details(resource)
        details.append(detail)

    if not details:
        return ChatResponse(
            response="No resources found in the subscription.",
            resource_count=0,
        )

    try:
        response = answer_governance_query(details, payload.message)
    except ValueError as exc:
        response = (
            "LLM configuration is missing. Set AZURE_OPENAI_ENDPOINT, "
            "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT on the server."
        )
        return ChatResponse(response=response, resource_count=len(details))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM request failed: {exc}") from exc

    return ChatResponse(response=response, resource_count=len(details))


@app.post("/chat/stream")
def chat_stream(payload: ChatRequest, _auth=Depends(require_auth)):
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if _wants_public_network_excel(payload.message):
        try:
            records = discover_public_network_resources()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Resource discovery failed: {exc}") from exc

        _write_public_network_csv(records)
        message = (
            f"Created export at /exports/public_network_access.csv with {len(records)} resources "
            "that report public network access enabled."
        )
        return StreamingResponse(iter([message]), media_type="text/plain")

    if _wants_resources_export(payload.message):
        try:
            resources = discover_resources()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Resource discovery failed: {exc}") from exc

        details = []
        for resource in resources:
            detail = collect_resource_details(resource)
            details.append(detail)

        _write_resources_csv(details)
        message = (
            f"Created export at /exports/resources_overview.csv with {len(details)} resources."
        )
        return StreamingResponse(iter([message]), media_type="text/plain")

    try:
        resources = discover_resources()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resource discovery failed: {exc}") from exc

    details = []
    for resource in resources:
        detail = collect_resource_details(resource)
        details.append(detail)

    if not details:
        return StreamingResponse(
            iter(["No resources found in the subscription."])
        )

    def _stream():
        try:
            for chunk in stream_governance_query(details, payload.message):
                yield chunk
        except ValueError:
            yield (
                "LLM configuration is missing. Set AZURE_OPENAI_ENDPOINT, "
                "AZURE_OPENAI_API_KEY, and AZURE_OPENAI_DEPLOYMENT on the server."
            )
        except Exception as exc:
            yield f"\n[Error] {exc}"

    return StreamingResponse(
        _stream(),
        media_type="text/plain",
        headers={"X-Resource-Count": str(len(details))},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
