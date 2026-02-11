from openai import AzureOpenAI
from config import OPENAI_ENDPOINT, OPENAI_KEY, OPENAI_DEPLOYMENT

_client = None


def _require_openai_config():
    missing = []
    if not OPENAI_ENDPOINT:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not OPENAI_KEY:
        missing.append("AZURE_OPENAI_API_KEY")
    if not OPENAI_DEPLOYMENT:
        missing.append("AZURE_OPENAI_DEPLOYMENT")
    if missing:
        raise ValueError("Missing OpenAI configuration: " + ", ".join(missing))


def _get_client():
    global _client
    if _client is None:
        _require_openai_config()
        _client = AzureOpenAI(
            api_key=OPENAI_KEY,
            api_version="2024-02-01",
            azure_endpoint=OPENAI_ENDPOINT,
        )
    return _client


def explain_resource(details, question=None):
    prompt = f"""
    Explain this Azure resource:
    {details}
    Include cost, security, and optimization suggestions.
    """

    if question:
        prompt += f"\nUser question: {question}\n"

    response = _get_client().chat.completions.create(
        model=OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content


def answer_governance_query(resources, question):
    prompt = f"""
    You are an Azure governance assistant.
    Use the resource data below to answer the user question.
    Be specific, cite resource names, and call out security, cost, compliance,
    and optimization opportunities. If data is missing, say so.

    Resource data:
    {resources}

    User question: {question}
    """

    response = _get_client().chat.completions.create(
        model=OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
    )

    return response.choices[0].message.content


def stream_governance_query(resources, question):
    prompt = f"""
    You are an Azure governance assistant.
    Use the resource data below to answer the user question.
    Be specific, cite resource names, and call out security, cost, compliance,
    and optimization opportunities. If data is missing, say so.

    Resource data:
    {resources}

    User question: {question}
    """

    stream = _get_client().chat.completions.create(
        model=OPENAI_DEPLOYMENT,
        messages=[{"role": "user", "content": prompt}],
        stream=True,
    )

    for event in stream:
        if not event.choices:
            continue
        delta = event.choices[0].delta.content or ""
        if delta:
            yield delta
