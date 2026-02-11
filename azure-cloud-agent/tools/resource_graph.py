from azure.identity import DefaultAzureCredential
from azure.mgmt.resourcegraph import ResourceGraphClient
from azure.mgmt.resourcegraph.models import QueryRequest
from config import SUBSCRIPTION_ID

def discover_resources():
    credential = DefaultAzureCredential()
    client = ResourceGraphClient(credential)

    query = QueryRequest(
        subscriptions=[SUBSCRIPTION_ID],
        query="""
        Resources
        | project name, type, location, resourceGroup, id, tags, kind, sku, identity, managedBy, properties
        """
    )
    return client.resources(query).data


def discover_public_network_resources():
    credential = DefaultAzureCredential()
    client = ResourceGraphClient(credential)

    query = QueryRequest(
        subscriptions=[SUBSCRIPTION_ID],
        query="""
        Resources
        | extend publicNetworkAccess = tostring(properties.publicNetworkAccess)
        | where publicNetworkAccess =~ "Enabled" or publicNetworkAccess =~ "enabled"
        | project name, type, location, resourceGroup, id, publicNetworkAccess
        """,
    )
    return client.resources(query).data
