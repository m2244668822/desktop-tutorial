#!/usr/bin/env python3
"""Run the bounded, metadata-only n8n training/evaluation pipeline."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATA_ROOT = Path(os.environ.get("TREVOR_DATA_DIR", str(BASE_DIR / "TrevorData"))).expanduser()
DEFAULT_BACKUP_ROOT = BASE_DIR.parent / "TrevorBackups"
DEFAULT_HEALTH_URL = "http://127.0.0.1:5001/health/ready"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if int(getattr(response, "status", 200) or 200) != 200:
            raise RuntimeError(f"health_http_{response.status}")
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("health_payload_not_object")
    return payload


def _run_tool(command: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd),
        timeout=timeout,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _safe_run_id(value: str | None) -> str:
    candidate = str(value or "").strip()
    if RUN_ID_PATTERN.fullmatch(candidate):
        return candidate
    return "n8n-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]


def _tmp_path(target: Path, run_id: str) -> Path:
    return target.with_name(f"{target.stem}.{run_id}.tmp{target.suffix or '.json'}")


def _inside(path: Path, *roots: Path) -> bool:
    resolved = path.expanduser().resolve()
    for root in roots:
        try:
            resolved.relative_to(root.expanduser().resolve())
            return True
        except ValueError:
            continue
    return False


def _load_report(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("report_not_object")
    return payload


def _sanitize_health(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": str(payload.get("status", "")),
        "required_ready": bool(payload.get("required_ready")),
        "optional_gaps": [str(item) for item in payload.get("optional_gaps", []) or []],
        "degraded_reasons": [str(item) for item in payload.get("degraded_reasons", []) or []],
    }


def _sanitize_retrieval(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics", {}) if isinstance(payload.get("metrics"), dict) else {}
    no_hit = metrics.get("no_hit", {}) if isinstance(metrics.get("no_hit"), dict) else {}
    stale = metrics.get("stale", {}) if isinstance(metrics.get("stale"), dict) else {}
    return {
        "generated_at": str(payload.get("generated_at", "")),
        "cases": int(payload.get("cases", 0) or 0),
        "hit_rate": float(payload.get("hit_rate", metrics.get("hit_rate", 0.0)) or 0.0),
        "mrr": float(payload.get("mrr", metrics.get("mrr", 0.0)) or 0.0),
        "citation_correctness": float(metrics.get("citation_correctness", 0.0) or 0.0),
        "privacy_leakage": int(metrics.get("privacy_leakage", 0) or 0),
        "no_hit_false_positive": int(no_hit.get("false_positive", 0) or 0),
        "stale_cases": int(stale.get("cases", 0) or 0),
        "stale_retrieved": int(stale.get("retrieved", 0) or 0),
    }


def _sanitize_training(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("readiness", {}) if isinstance(payload.get("readiness"), dict) else {}
    return {
        "generated_at": str(payload.get("generated_at", "")),
        "summary_zh": str(payload.get("summary_zh", "")),
        "readiness": {key: bool(readiness.get(key)) for key in ("data", "retrieval", "backup", "git")},
    }


def _gate_errors(health: dict[str, Any], retrieval: dict[str, Any], training: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not health.get("required_ready"):
        errors.append("health_gate_failed")
    if retrieval:
        if retrieval["cases"] < 30:
            errors.append("retrieval_cases_below_gate")
        if retrieval["hit_rate"] < 0.75:
            errors.append("retrieval_hit_rate_below_gate")
        if retrieval["privacy_leakage"] != 0:
            errors.append("privacy_leakage_detected")
        if retrieval["stale_retrieved"] != 0:
            errors.append("stale_retrieval_detected")
    if training and not all(training.get("readiness", {}).values()):
        errors.append("training_readiness_failed")
    return errors


def _summary_zh(gate_passed: bool, errors: list[str], retrieval: dict[str, Any]) -> str:
    if gate_passed:
        return (
            "n8n 訓練／評估流程已通過 gate；"
            f"retrieval hit rate 為 {retrieval.get('hit_rate', 0.0):.4f}。"
        )
    reason = "、".join(errors) if errors else "未知原因"
    return f"n8n 訓練／評估流程尚未通過 gate；待處理：{reason}。"


def _replace_report(temp_path: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(temp_path, target)


def run_pipeline(
    *,
    repo_root: str | Path,
    data_root: str | Path,
    backup_root: str | Path,
    retrieval_report: str | Path,
    training_report: str | Path,
    health_url: str = DEFAULT_HEALTH_URL,
    python_executable: str = sys.executable,
    run_id: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root).expanduser().resolve()
    data = Path(data_root).expanduser().resolve()
    backup = Path(backup_root).expanduser().resolve()
    retrieval_target = Path(retrieval_report).expanduser().resolve()
    training_target = Path(training_report).expanduser().resolve()
    current_run = _safe_run_id(run_id)
    errors: list[str] = []
    health: dict[str, Any] = {}
    retrieval: dict[str, Any] = {}
    training: dict[str, Any] = {}
    artifacts = {
        "retrieval_report": str(retrieval_target),
        "training_report": str(training_target),
    }
    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_id": current_run,
        "gate_passed": False,
        "intro_zh": "中文說明：這份 n8n 流程只保存健康、檢索與訓練準備的 aggregate 指標。",
        "summary_zh": "n8n 訓練／評估流程尚未開始。",
        "field_descriptions_zh": {
            "health": "Trevor 核心服務是否可用。",
            "retrieval": "golden-set 檢索品質與 stale／隱私指標。",
            "training": "資料、檢索、備份與 Git 四層訓練準備狀態。",
            "gate_passed": "是否達到本輪手動訓練／評估交付門檻。",
        },
        "health": health,
        "retrieval": retrieval,
        "training": training,
        "artifacts": artifacts,
        "errors": errors,
    }

    if not _inside(retrieval_target, data, backup, repo) or not _inside(training_target, data, backup, repo):
        errors.append("artifact_path_outside_allowlist")
        payload["summary_zh"] = _summary_zh(False, errors, retrieval)
        return payload

    previous_data_root = os.environ.get("TREVOR_DATA_DIR")
    os.environ["TREVOR_DATA_DIR"] = str(data)
    try:
        try:
            health = _sanitize_health(_fetch_json(health_url, timeout=8.0))
            payload["health"] = health
        except Exception:
            errors.append("health_probe_failed")
            payload["summary_zh"] = _summary_zh(False, errors, retrieval)
            return payload

        if not health.get("required_ready"):
            errors.append("health_gate_failed")
            payload["summary_zh"] = _summary_zh(False, errors, retrieval)
            return payload

        retrieval_tmp = _tmp_path(retrieval_target, current_run)
        retrieval_cmd = [
            python_executable,
            str(repo / "tools" / "evaluate_knowledge_retrieval.py"),
            "--workspace",
            str(repo),
            "--cases",
            str(repo / "config" / "knowledge_retrieval_eval.json"),
            "--top-k",
            "5",
            "--output",
            str(retrieval_tmp),
        ]
        try:
            retrieval_result = _run_tool(retrieval_cmd, cwd=repo, timeout=120)
        except subprocess.TimeoutExpired:
            retrieval_result = None
            errors.append("retrieval_evaluation_timeout")
        except OSError:
            retrieval_result = None
            errors.append("retrieval_evaluation_launch_failed")

        fresh_retrieval = False
        if retrieval_tmp.exists():
            try:
                retrieval_payload = _load_report(retrieval_tmp)
                retrieval = _sanitize_retrieval(retrieval_payload)
                payload["retrieval"] = retrieval
                _replace_report(retrieval_tmp, retrieval_target)
                fresh_retrieval = True
            except (OSError, ValueError, TypeError):
                errors.append("retrieval_report_invalid")
                retrieval_tmp.unlink(missing_ok=True)
        if retrieval_result is not None and retrieval_result.returncode != 0:
            errors.append("retrieval_evaluation_failed")
        if not fresh_retrieval and "retrieval_evaluation_failed" not in errors:
            errors.append("retrieval_report_missing")

        if fresh_retrieval:
            training_tmp = _tmp_path(training_target, current_run)
            training_cmd = [
                python_executable,
                str(repo / "tools" / "generate_training_status_report.py"),
                "--repo",
                str(repo),
                "--data-root",
                str(data),
                "--backup-root",
                str(backup),
                "--retrieval-report",
                str(retrieval_target),
                "--output",
                str(training_tmp),
            ]
            try:
                training_result = _run_tool(training_cmd, cwd=repo, timeout=120)
            except subprocess.TimeoutExpired:
                training_result = None
                errors.append("training_status_timeout")
            except OSError:
                training_result = None
                errors.append("training_status_launch_failed")
            if training_tmp.exists():
                try:
                    training_payload = _load_report(training_tmp)
                    training = _sanitize_training(training_payload)
                    payload["training"] = training
                    _replace_report(training_tmp, training_target)
                except (OSError, ValueError, TypeError):
                    errors.append("training_report_invalid")
                    training_tmp.unlink(missing_ok=True)
            if training_result is not None and training_result.returncode != 0:
                errors.append("training_status_generation_failed")
        errors.extend(error for error in _gate_errors(health, retrieval, training) if error not in errors)
        payload["errors"] = errors
        payload["gate_passed"] = not errors
        payload["summary_zh"] = _summary_zh(payload["gate_passed"], errors, retrieval)
        return payload
    finally:
        if previous_data_root is None:
            os.environ.pop("TREVOR_DATA_DIR", None)
        else:
            os.environ["TREVOR_DATA_DIR"] = previous_data_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=BASE_DIR)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--retrieval-report", type=Path)
    parser.add_argument("--training-report", type=Path)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    data_root = args.data_root.expanduser().resolve()
    retrieval_report = args.retrieval_report or data_root / "knowledge_hub" / "reports" / "retrieval_eval_latest.json"
    training_report = args.training_report or data_root / "knowledge_hub" / "reports" / "training_status_latest.json"
    payload = run_pipeline(
        repo_root=args.repo_root,
        data_root=data_root,
        backup_root=args.backup_root,
        retrieval_report=retrieval_report,
        training_report=training_report,
        health_url=args.health_url,
        python_executable=args.python_executable,
        run_id=args.run_id,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
