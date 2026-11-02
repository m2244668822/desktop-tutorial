import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / "automation" / "n8n" / "trevor-training-evaluation.json"


def _workflow():
    return json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _write(tmp_path, payload):
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_validator_accepts_current_training_workflow():
    from tools.validate_n8n_training_workflow import validate_workflow

    assert validate_workflow(WORKFLOW_PATH) == []


def test_validator_rejects_active_schedule_credentials_and_missing_nodes(tmp_path):
    from tools.validate_n8n_training_workflow import validate_workflow

    payload = _workflow()
    payload["active"] = True
    payload["nodes"] = [node for node in payload["nodes"] if node["name"] != "Health gate"]
    payload["nodes"][0]["type"] = "n8n-nodes-base.scheduleTrigger"
    payload["nodes"][0]["credentials"] = {"httpBasicAuth": {"id": "secret"}}

    errors = validate_workflow(_write(tmp_path, payload))

    assert "workflow_must_be_inactive" in errors
    assert "manual_trigger_required" in errors
    assert "schedule_or_webhook_trigger_forbidden" in errors
    assert "credentials_forbidden" in errors
    assert "required_node_missing:Health gate" in errors


def test_validator_rejects_external_urls_and_dynamic_commands(tmp_path):
    from tools.validate_n8n_training_workflow import validate_workflow

    payload = _workflow()
    http_node = next(node for node in payload["nodes"] if node["name"] == "Read Trevor readiness")
    http_node["parameters"]["url"] = "https://example.invalid/collect"
    training_node = next(node for node in payload["nodes"] if node["name"] == "Run fixed training evaluator")
    training_node["parameters"]["url"] = "={{ $json.userUrl }}"

    errors = validate_workflow(_write(tmp_path, payload))

    assert "external_url_forbidden" in errors
    assert "dynamic_url_forbidden" in errors
    assert "fixed_training_endpoint_required" in errors


def test_validator_rejects_invalid_json(tmp_path):
    from tools.validate_n8n_training_workflow import validate_workflow

    path = tmp_path / "broken.json"
    path.write_text("{not-json", encoding="utf-8")

    assert validate_workflow(path) == ["invalid_json"]


def test_validator_rejects_missing_workflow_id(tmp_path):
    from tools.validate_n8n_training_workflow import validate_workflow

    payload = _workflow()
    payload.pop("id", None)

    assert "workflow_id_required" in validate_workflow(_write(tmp_path, payload))


def test_smoke_script_is_bounded_and_does_not_start_or_delete_n8n():
    script = (ROOT / "tools" / "smoke_test_n8n_training_evaluation.ps1").read_text(encoding="utf-8")

    assert "healthz" in script
    assert "Start-Process" in script
    assert "WaitForExit" in script
    assert "Timeout" in script
    assert "taskkill.exe" in script
    assert "N8N_USER_MANAGEMENT_DISABLED" in script
    assert "import:workflow" in script
    assert "Start-N8n" not in script
    assert "Remove-Item" not in script


def test_smoke_script_has_a_python_environment_fallback():
    script = (ROOT / "tools" / "smoke_test_n8n_training_evaluation.ps1").read_text(encoding="utf-8")

    assert "TREVOR_PYTHON" in script
    assert "Get-Command python" in script
