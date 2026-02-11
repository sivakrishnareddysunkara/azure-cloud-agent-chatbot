from azure.identity import DefaultAzureCredential
from azure.mgmt.storage import StorageManagementClient
from config import SUBSCRIPTION_ID

def inspect_storage(resource):
    rg = resource["resourceGroup"]
    name = resource["name"]

    client = StorageManagementClient(
        DefaultAzureCredential(), SUBSCRIPTION_ID
    )

    acc = client.storage_accounts.get_properties(rg, name)

    return {
        "name": name,
        "sku": acc.sku.name,
        "https_only": acc.enable_https_traffic_only
    }
