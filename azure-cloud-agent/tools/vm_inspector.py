from azure.identity import DefaultAzureCredential
from azure.mgmt.compute import ComputeManagementClient
from config import SUBSCRIPTION_ID


def inspect_vm(resource):
    rg = resource["resourceGroup"]
    name = resource["name"]

    client = ComputeManagementClient(
        DefaultAzureCredential(),
        SUBSCRIPTION_ID
    )

    vm = client.virtual_machines.get(rg, name)

    return {
        "name": name,
        "size": vm.hardware_profile.vm_size,
        "os": str(vm.storage_profile.os_disk.os_type),
        "location": vm.location
    }
