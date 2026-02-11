from tools.vm_inspector import inspect_vm
from tools.storage_inspector import inspect_storage
from tools.security_inspector import check_security
from llm.explain import explain_resource


def _detect_provisioning_source(resource):
    tags = resource.get("tags") or {}
    tag_keys = [str(key).lower() for key in tags.keys()]
    tag_values = [str(value).lower() for value in tags.values()]
    managed_by = str(resource.get("managedBy") or "").lower()

    terraform_markers = ["terraform", "managed-by", "managedby", "createdby", "provisioner"]
    if any("terraform" in managed_by for _ in [0]):
        return "terraform (managedBy)"

    for marker in terraform_markers:
        if any(marker in key for key in tag_keys) or any(marker in value for value in tag_values):
            if "terraform" in marker or any("terraform" in value for value in tag_values):
                return "terraform (tags)"

    return "unknown"


def _extract_generic_details(resource):
    props = resource.get("properties") or {}
    private_endpoints = props.get("privateEndpointConnections")
    if isinstance(private_endpoints, list):
        private_endpoint_count = len(private_endpoints)
    else:
        private_endpoint_count = None

    details = {
        "inspector": "generic",
        "tags": resource.get("tags") or {},
        "kind": resource.get("kind"),
        "sku": resource.get("sku"),
        "identity": resource.get("identity"),
        "managedBy": resource.get("managedBy"),
        "publicNetworkAccess": props.get("publicNetworkAccess"),
        "privateEndpointCount": private_endpoint_count,
        "encryption": props.get("encryption") or props.get("encryptionServices"),
        "managedVirtualNetwork": props.get("managedVirtualNetwork")
        or props.get("managedVirtualNetworkType")
        or props.get("managedNetwork"),
        "provisioned_by": _detect_provisioning_source(resource),
    }

    return details


def collect_resource_details(resource):
    rtype = resource["type"]
    base = {
        "type": rtype,
        "name": resource.get("name"),
        "location": resource.get("location"),
        "resourceGroup": resource.get("resourceGroup"),
        "id": resource.get("id"),
    }

    if rtype == "Microsoft.Compute/virtualMachines":
        details = inspect_vm(resource)
    elif rtype == "Microsoft.Storage/storageAccounts":
        details = inspect_storage(resource)
    else:
        details = _extract_generic_details(resource)

    for key, value in base.items():
        details.setdefault(key, value)

    security = check_security(rtype, details)
    details["security_issues"] = security

    return details


def process_resource(resource):
    details = collect_resource_details(resource)
    if not details:
        return None

    return explain_resource(details)
