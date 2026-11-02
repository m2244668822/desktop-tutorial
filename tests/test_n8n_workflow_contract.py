import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "automation" / "n8n" / "trevor-training-evaluation.json"


def _workflow():
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def test_training_workflow_is_manual_and_inactive():
    workflow = _workflow()
    nodes = workflow["nodes"]
    triggers = [node for node in nodes if node["type"].endswith("Trigger")]

    assert workflow["name"] == "Trevor Training Evaluation (Manual)"
    assert workflow["active"] is False
    assert len(triggers) == 1
    assert triggers[0]["type"] == "n8n-nodes-base.manualTrigger"
    assert {node["name"] for node in nodes} >= {
        "Manual Trigger",
        "Read Trevor readiness",
        "Health gate",
        "Run fixed training evaluator",
        "Sanitize result",
    }


def test_training_workflow_has_no_external_or_credentialed_edges():
    workflow = _workflow()
    encoded = json.dumps(workflow, ensure_ascii=False)

    assert "credentials" not in encoded
    assert "scheduleTrigger" not in encoded
    assert "webhook" not in encoded.lower()
    assert "127.0.0.1:5001/health/ready" in encoded
    assert "http://" not in encoded.replace("http://127.0.0.1:5001/health/ready", "")


def test_execute_command_is_fixed_and_does_not_interpolate_item_data():
    workflow = _workflow()
    execute_nodes = [node for node in workflow["nodes"] if node["type"] == "n8n-nodes-base.executeCommand"]

    assert len(execute_nodes) == 1
    command = execute_nodes[0]["parameters"]["command"]
    assert "n8n_training_evaluation.py" in command
    assert "--repo-root" in command
    assert "--data-root" in command
    assert "--backup-root" in command
    assert "--health-url" in command
    assert "{{$json" not in command
    assert "{{ $json" not in command
    assert "$input" not in command


def test_connections_enforce_health_gate_then_sanitize():
    workflow = _workflow()
    connections = workflow["connections"]

    assert connections["Manual Trigger"]["main"][0][0]["node"] == "Read Trevor readiness"
    assert connections["Read Trevor readiness"]["main"][0][0]["node"] == "Health gate"
    assert connections["Health gate"]["main"][0][0]["node"] == "Run fixed training evaluator"
    assert connections["Health gate"]["main"][1][0]["node"] == "Health gate failure"
    assert connections["Run fixed training evaluator"]["main"][0][0]["node"] == "Sanitize result"
    assert connections["Health gate failure"]["main"][0][0]["node"] == "Sanitize result"


def test_sanitize_code_has_an_explicit_allowlist():
    workflow = _workflow()
    sanitize = next(node for node in workflow["nodes"] if node["name"] == "Sanitize result")
    code = sanitize["parameters"]["jsCode"]

    for field in ["schema_version", "run_id", "gate_passed", "health", "retrieval", "training", "artifacts", "errors"]:
        assert field in code
    assert "results" not in code
    assert "query" not in code
