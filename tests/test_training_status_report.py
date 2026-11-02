import json
from pathlib import Path


def test_training_status_report_is_structured_and_secret_free(tmp_path):
    from tools.generate_training_status_report import build_training_status_report

    data_root = tmp_path / "TrevorData"
    (data_root / "knowledge_hub").mkdir(parents=True)
    (data_root / "knowledge_hub" / "manifest.json").write_text("{}", encoding="utf-8")
    backup_root = tmp_path / "backups"
    backup_day = backup_root / "2026-11-02"
    backup_day.mkdir(parents=True)
    snapshot = backup_day / "trevor-data-2026-11-02.trevor.enc"
    snapshot.write_bytes(b"ciphertext")
    manifest = backup_day / "trevor-data-2026-11-02.manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "snapshot_sha256": "known",
                "snapshot_size": snapshot.stat().st_size,
                "archive_sha256": "known-archive",
            }
        ),
        encoding="utf-8",
    )
    retrieval = tmp_path / "retrieval.json"
    retrieval.write_text(
        json.dumps(
            {
                "cases": 38,
                "metrics": {
                    "hit_rate": 0.8,
                    "mrr": 0.7,
                    "citation_correctness": 0.75,
                    "privacy_leakage": 0,
                },
                "api_key": "must not be copied",
            }
        ),
        encoding="utf-8",
    )

    report = build_training_status_report(
        repo_root=tmp_path,
        data_root=data_root,
        backup_root=backup_root,
        retrieval_report=retrieval,
        git_info={"branch": "codex/test", "dirty_files": [], "ahead": 0, "behind": 0},
    )

    assert report["schema_version"] == 1
    assert report["intro_zh"]
    assert report["summary_zh"]
    assert "readiness" in report["field_descriptions_zh"]
    assert report["readiness"]["backup"] is True
    assert report["retrieval"]["citation_correctness"] == 0.75
    assert "must not be copied" not in json.dumps(report)


def test_training_status_report_flags_missing_or_stale_layers(tmp_path):
    from tools.generate_training_status_report import build_training_status_report

    report = build_training_status_report(
        repo_root=tmp_path,
        data_root=tmp_path / "missing-data",
        backup_root=tmp_path / "missing-backups",
        retrieval_report=tmp_path / "missing-retrieval.json",
        git_info={"branch": "codex/test", "dirty_files": ["secret.env"], "ahead": 1, "behind": 2},
    )

    assert report["readiness"]["data"] is False
    assert report["readiness"]["backup"] is False
    assert report["readiness"]["retrieval"] is False
    assert report["git"]["dirty_files"] == ["secret.env"]
    assert "尚未" in report["summary_zh"]
