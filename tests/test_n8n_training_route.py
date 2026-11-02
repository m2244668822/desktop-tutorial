import sys
import types
from pathlib import Path
from types import SimpleNamespace


def test_bridge_training_route_calls_fixed_wrapper(monkeypatch, tmp_path):
    import desktop_chat_app

    captured = {}

    def fake_run_pipeline(**kwargs):
        captured.update(kwargs)
        return {"schema_version": 1, "run_id": "test", "gate_passed": True}

    fake_module = types.SimpleNamespace(run_pipeline=fake_run_pipeline)
    monkeypatch.setitem(sys.modules, "n8n_training_evaluation", fake_module)

    bridge = desktop_chat_app.DesktopBridge.__new__(desktop_chat_app.DesktopBridge)
    bridge.workspace = tmp_path
    bridge.paths = SimpleNamespace(data=tmp_path / "TrevorData")

    result = bridge.run_n8n_training_evaluation()

    assert result["gate_passed"] is True
    assert captured["repo_root"] == tmp_path
    assert captured["data_root"] == tmp_path / "TrevorData"
    assert captured["health_url"] == "http://127.0.0.1:5001/health/ready"
    assert captured["retrieval_report"].name == "retrieval_eval_latest.json"
    assert captured["training_report"].name == "training_status_latest.json"


def test_web_server_declares_local_n8n_training_endpoint():
    web_server = Path(__file__).resolve().parents[1] / "core" / "web_server.py"
    text = web_server.read_text(encoding="utf-8-sig")

    assert 'route_path == "/api/n8n/training-evaluation"' in text
    assert "run_n8n_training_evaluation" in text
    assert "127.0.0.1" in text
