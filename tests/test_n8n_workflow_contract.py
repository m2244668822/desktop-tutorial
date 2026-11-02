import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / "automation" / "n8n" / "trevor-local-health-check.json"


def test_local_health_workflow_is_manual_inactive_and_local_only():
    payload = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    assert payload["active"] is False
    node_types = {node["type"] for node in payload["nodes"]}
    assert node_types == {
        "n8n-nodes-base.manualTrigger",
        "n8n-nodes-base.httpRequest",
    }
    urls = [
        node.get("parameters", {}).get("url", "")
        for node in payload["nodes"]
        if node["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert urls == ["http://127.0.0.1:5001/health/ready"]
    assert all("credentials" not in node for node in payload["nodes"])
