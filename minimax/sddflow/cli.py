"""CLI entrypoint: python -m sddflow.cli <command>."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from . import db, runner
from .powercontext_client import PowerContext
from .utils import ROOT, file_sha, read_task, safe_source, save_json, timestamp


def verify_spec_refresh() -> dict:
    task = read_task()
    path = safe_source(task["required_sources"]["spec"][0])
    original = path.read_bytes()
    marker = "SPEC_REFRESH_PROBE_2026_REQUIREMENT_CHANGED"
    old_sha = file_sha(path)
    try:
        # Simulate a meaningful spec revision; the query must read the NEW SQL row.
        revised = original.decode("utf-8") + (
            "\n## Revision: v2 test import\n" + marker +
            ": min_stock must remain inclusive; amended version was re-ingested.\n")
        path.write_text(revised, encoding="utf-8")
        db.ingest()
        fresh = runner.context(include_powercontext=False)
        spec = [d for d in fresh["source_provenance"] if d["path"] == task["required_sources"]["spec"][0]]
        good = bool(spec and marker in spec[0]["content"] and spec[0]["sha256"] != old_sha)
        report = {"result": "PASS" if good else "FAIL",
                  "marker": marker, "old_spec_sha256": old_sha,
                  "updated_spec_sha256": spec[0]["sha256"] if spec else None,
                  "query_returned_updated_content": good,
                  "time": timestamp()}
    finally:
        path.write_bytes(original)
        db.ingest()
        # Restore the canonical task context report as well as the database:
        # the temporary v2 probe must not remain as the latest context.
        runner.context(include_powercontext=False)
    report["original_spec_restored_sha256"] = file_sha(path)
    save_json(ROOT / "evidence" / "spec_refresh_verification.json", report)
    if not good:
        raise RuntimeError(f"Spec refresh did not return updated spec via SQL: {report}")
    return report


def audit() -> dict:
    required = [
        "database_ingest.json", "database_last_query.json", "state_last_write.json",
        "state_last_read.json", "context_latest.json", "model_last_success.json",
        "spec_refresh_verification.json",
    ]
    task = read_task()
    report = {"time": timestamp(), "required_evidence": {}, "status": "NOT_READY"}
    for key in required:
        report["required_evidence"][key] = (ROOT / "evidence" / key).is_file()
    after = ROOT / "snapshots" / "after" / "inventory.py"
    report["after_snapshot_present"] = after.is_file()
    working = safe_source(task["target_file"])
    report["working_source_matches_after_snapshot"] = bool(after.is_file() and file_sha(after) == file_sha(working))
    if after.is_file():
        report["after_snapshot_sha256"] = file_sha(after)
    report["all_required_sources_present"] = all(
        safe_source(path).is_file() for v in task["required_sources"].values() for path in v)
    if all(report["required_evidence"].values()) and after.is_file():
        model = json.loads((ROOT / "evidence" / "model_last_success.json").read_text())
        state = json.loads((ROOT / "evidence" / "state_last_read.json").read_text())
        spec = json.loads((ROOT / "evidence" / "spec_refresh_verification.json").read_text())
        def evidence_status(path, field, expected):
            file = ROOT / "evidence" / path
            return file.is_file() and json.loads(file.read_text()).get(field) == expected
        report["status"] = ("READY_FOR_REVIEW" if (
            model["after_sha256"] == file_sha(after)
            and report["working_source_matches_after_snapshot"]
            and model.get("tests", {}).get("acceptance") == "PASS"
            and evidence_status("04_before_test.json", "acceptance", "PASS")
            and evidence_status("09_after_test.json", "acceptance", "PASS")
            and evidence_status("14_offline_replay.json", "status", "PASS")
            and any("stage=validated" in item for item in state.get("records", []))
            and spec["result"] == "PASS") else "INCOMPLETE")
    save_json(ROOT / "evidence" / "submission_audit.json", report)
    return report


def doctor() -> dict:
    import importlib.util
    info = {"time": timestamp(), "python": sys.version.split()[0], "cwd": str(ROOT),
            "seekdb_library": importlib.util.find_spec("pylibseekdb") is not None,
            "pymysql_library": importlib.util.find_spec("pymysql") is not None,
            "pytest_library": importlib.util.find_spec("pytest") is not None,
            "minimax_key_configured": bool(os.getenv("MINIMAX_API_KEY", "")
                                            and not os.getenv("MINIMAX_API_KEY", "").startswith("REPLACE_"))}
    try:
        info["git_head"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
        info["git_branch"] = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        info["git_head"] = None
        info["git_branch"] = None
    try:
        info["powercontext_health"] = PowerContext().health()
    except RuntimeError as exc:
        info["powercontext_error"] = str(exc)
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ["doctor", "init-scope", "ingest", "context", "state-read",
                 "baseline-test", "model-apply", "after-test", "reset-code",
                 "reproduce-offline", "verify-spec-refresh", "audit"]:
        sp = sub.add_parser(name)
        if name == "context":
            sp.add_argument("--no-state", action="store_true")
        if name == "state-read":
            sp.add_argument("--require-stage", default="")
    sp = sub.add_parser("state-write")
    sp.add_argument("--stage", required=True)
    sp.add_argument("--next", required=True, help="Next concrete action, no pipe character")
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            out = doctor()
        elif args.command == "init-scope":
            out = {"scope_id": PowerContext().init_scope()}
        elif args.command == "ingest":
            out = db.ingest()
        elif args.command == "context":
            out = runner.context(include_powercontext=not args.no_state)
        elif args.command == "state-read":
            out = PowerContext().read_state()
            if args.require_stage and not any(f"stage={args.require_stage}" in r for r in out["records"]):
                raise RuntimeError(f"Saved PowerContext state for stage={args.require_stage} not found")
        elif args.command == "state-write":
            sha = file_sha(safe_source(read_task()["target_file"]))
            out = PowerContext().write_state(args.stage, args.next, sha)
        elif args.command == "baseline-test":
            out = runner.test_pair("before")
        elif args.command == "model-apply":
            out = runner.model_apply()
        elif args.command == "after-test":
            out = runner.test_pair("after")
        elif args.command == "reset-code":
            out = runner.reset_code()
        elif args.command == "reproduce-offline":
            out = runner.reproduce_offline()
        elif args.command == "verify-spec-refresh":
            out = verify_spec_refresh()
        elif args.command == "audit":
            out = audit()
        else:
            raise AssertionError(args.command)
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"command": args.command, "error": str(exc),
                          "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
