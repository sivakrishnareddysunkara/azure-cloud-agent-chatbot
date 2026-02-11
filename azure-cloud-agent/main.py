import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from agent.orchestrator import process_resource
from tools.resource_graph import discover_resources


def main():
    resources = discover_resources()

    print(f"Discovered {len(resources)} resources")

    for r in resources:
        result = process_resource(r)
        if result:
            print("\n--- RESOURCE SUMMARY ---")
            print(result)


if __name__ == "__main__":
    main()