import json
import subprocess
from pathlib import Path

import pytest


def _health_ready():
    return {
        "status": "ready",
        "required_ready": True,
        "optional_gaps": [],
        "intro_zh": "health",
        "summary_zh": "ready",
    }


def _retrieval_report(**overrides):
    payload = {
        "generated_at": "2026-11-02T10:00:00+00:00",
        "cases": 38,
        "hit_rate": 1.0,
        "mrr": 0.86,
        "metrics": {
            "citation_correctness": 0.78,
            "privacy_leakage": 0,
            "no_hit": {"false_positive": 0},
            "stale": {"retrieved": 0},
        },
        "results": [
            {
                "query": "private query must not leave wrapper",
                "evidence": [{"path": "private text must not leave wrapper"}],
            }
        ],
    }
    payload.update(overrides)
    return payload


def _training_report(**overrides):
    payload = {
        "generated_at": "2026-11-02T10:00:01+00:00",
        "summary_zh": "訓練準備狀態：可交付。",
        "readiness": {"data": True, "retrieval": True, "backup": True, "git": True},
        "retrieval": {"cases": 38, "hit_rate": 1.0},
    }
    payload.update(overrides)
    return payload


def _patch_runtime(monkeypatch, module, tmp_path, retrieval, training, *, health=None, returncodes=None):
    health_payload = health or _health_ready()
    monkeypatch.setattr(module, "_fetch_json", lambda url, timeout: health_payload)
    returncodes = returncodes or {"retrieval": 0, "training": 0}

    def fake_run(command, *, cwd, timeout):
        command_text = " ".join(str(part) for part in command)
        if "evaluate_knowledge_retrieval.py" in command_text:
            output = Path(command[command.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if returncodes["retrieval"] == 0:
                output.write_text(json.dumps(retrieval), encoding="utf-8")
            return subprocess.CompletedProcess(command, returncodes["retrieval"], "", "retrieval-error")
        if "generate_training_status_report.py" in command_text:
            output = Path(command[command.index("--output") + 1])
            output.parent.mkdir(parents=True, exist_ok=True)
            if returncodes["training"] == 0:
                output.write_text(json.dumps(training), encoding="utf-8")
            return subprocess.CompletedProcess(command, returncodes["training"], "", "training-error")
        raise AssertionError(f"unexpected command: {command_text}")

    monkeypatch.setattr(module, "_run_tool", fake_run)


def _run_pipeline(module, tmp_path):
    return module.run_pipeline(
        repo_root=tmp_path,
        data_root=tmp_path / "data",
        backup_root=tmp_path / "backups",
        retrieval_report=tmp_path / "data" / "retrieval.json",
        training_report=tmp_path / "data" / "training.json",
        health_url="http://127.0.0.1:5001/health/ready",
        python_executable="python",
        run_id="run-test-001",
    )


def test_pipeline_success_is_aggregate_only(monkeypatch, tmp_path):
    import tools.n8n_training_evaluation as module

    retrieval = _retrieval_report()
    _patch_runtime(monkeypatch, module, tmp_path, retrieval, _training_report())

    payload = _run_pipeline(module, tmp_path)

    assert payload["gate_passed"] is True
    assert payload["run_id"] == "run-test-001"
    assert payload["retrieval"]["hit_rate"] == 1.0
    assert payload["retrieval"]["stale_retrieved"] == 0
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "private query" not in encoded
    assert "private text" not in encoded
    assert '"results"' not in encoded


def test_health_gate_stops_tools(monkeypatch, tmp_path):
    import tools.n8n_training_evaluation as module

    called = False

    def fail_run(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("tool must not run when health gate fails")

    _patch_runtime(
        monkeypatch,
        module,
        tmp_path,
        _retrieval_report(),
        _training_report(),
        health={"status": "degraded", "required_ready": False, "degraded_reasons": ["database_not_ready"]},
    )
    monkeypatch.setattr(module, "_run_tool", fail_run)

    payload = _run_pipeline(module, tmp_path)

    assert payload["gate_passed"] is False
    assert "health_gate_failed" in payload["errors"]
    assert called is False


@pytest.mark.parametrize(
    "retrieval_overrides, expected_error",
    [
        ({"cases": 29}, "retrieval_cases_below_gate"),
        ({"hit_rate": 0.74}, "retrieval_hit_rate_below_gate"),
        ({"metrics": {"citation_correctness": 0.78, "privacy_leakage": 1, "no_hit": {"false_positive": 0}, "stale": {"retrieved": 0}}}, "privacy_leakage_detected"),
        ({"metrics": {"citation_correctness": 0.78, "privacy_leakage": 0, "no_hit": {"false_positive": 0}, "stale": {"retrieved": 1}}}, "stale_retrieval_detected"),
    ],
)
def test_retrieval_gate_lists_each_failure(monkeypatch, tmp_path, retrieval_overrides, expected_error):
    import tools.n8n_training_evaluation as module

    _patch_runtime(monkeypatch, module, tmp_path, _retrieval_report(**retrieval_overrides), _training_report())

    payload = _run_pipeline(module, tmp_path)

    assert payload["gate_passed"] is False
    assert expected_error in payload["errors"]


def test_failed_evaluator_does_not_reuse_old_latest_report(monkeypatch, tmp_path):
    import tools.n8n_training_evaluation as module

    old_report = tmp_path / "data" / "retrieval.json"
    old_report.parent.mkdir(parents=True)
    old_report.write_text(json.dumps(_retrieval_report()), encoding="utf-8")
    _patch_runtime(
        monkeypatch,
        module,
        tmp_path,
        _retrieval_report(),
        _training_report(),
        returncodes={"retrieval": 2, "training": 0},
    )

    payload = _run_pipeline(module, tmp_path)

    assert payload["gate_passed"] is False
    assert "retrieval_evaluation_failed" in payload["errors"]
    assert payload["retrieval"] == {}


def test_training_readiness_failure_is_structured(monkeypatch, tmp_path):
    import tools.n8n_training_evaluation as module

    _patch_runtime(
        monkeypatch,
        module,
        tmp_path,
        _retrieval_report(),
        _training_report(readiness={"data": True, "retrieval": False, "backup": True, "git": True}),
    )

    payload = _run_pipeline(module, tmp_path)

    assert payload["gate_passed"] is False
    assert "training_readiness_failed" in payload["errors"]
    assert payload["training"]["readiness"]["retrieval"] is False
