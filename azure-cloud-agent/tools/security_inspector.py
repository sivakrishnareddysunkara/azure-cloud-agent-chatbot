def check_security(resource_type, details):
    issues = []

    if resource_type == "Microsoft.Storage/storageAccounts":
        if not details.get("https_only", True):
            issues.append("Storage account allows HTTP traffic")

    if resource_type == "Microsoft.Compute/virtualMachines":
        # placeholder for future NSG / Public IP checks
        pass

    return issues
