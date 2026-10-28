"""Build context; run target/regression tests; apply actual MiniMax generation."""

from __future__ import annotations

import ast
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import db
from .minimax_client import generate
from .powercontext_client import PowerContext
from .utils import ROOT, file_sha, read_task, run_dir, safe_source, save_json, timestamp


def context(*, include_powercontext: bool = True) -> dict:
    task = read_task()
    docs, audit = db.search(task["query"], task["keywords"])
    found = {d["source_path"] for d in docs}
    missing = [p for paths in task["required_sources"].values() for p in paths if p not in found]
    if missing:
        raise RuntimeError(f"Missing required verified sources in seekdb query: {missing}")
    state = {"records": [], "latest": None}
    prepared = None
    if include_powercontext:
        pc = PowerContext()
        state = pc.read_state()
        prepared = pc.prepare(task["query"])
    result = {
        "task": task, "source_provenance": [
            {"path": d["source_path"], "kind": d["kind"], "symbol": d["symbol"],
             "sha256": d["sha256"], "content": d["content"]}
            for d in docs],
        "sql_retrieval": audit,
        "powercontext_state": {"latest": state.get("latest"),
                               "records": state.get("records", []),
                               "prepared": prepared},
        "built_at": timestamp(),
    }
    save_json(ROOT / "evidence" / "context_latest.json", result)
    return result


def _cmd_pytest(test: str, code_label: str, folder: Path) -> dict:
    code = safe_source(read_task()["target_file"])
    before_sha = file_sha(code)
    argv = [sys.executable, "-m", "pytest", "-q", test]
    result = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=90,
                            env={**os.environ, "PYTHONPATH": str(ROOT)})
    log = {
        "command": " ".join(argv), "cwd": ".", "exit_code": result.returncode,
        "stdout": result.stdout, "stderr": result.stderr,
        "code_version": code_label, "code_sha256": before_sha,
        "time_utc": timestamp(), "test_source_sha256": file_sha(safe_source(test)),
    }
    save_json(folder / ("feature.json" if "feature" in test else "regression.json"), log)
    if file_sha(code) != before_sha:
        raise RuntimeError("Test unexpectedly changed the business source")
    return log


def _functional_failure(log: dict) -> bool:
    """Reject import/collection/environment failures as purported target behavior failures."""
    stdout = log["stdout"]
    return (log["exit_code"] == 1 and " failed" in stdout
            and ("AssertionError" in stdout or re.search(r"^E\s+assert\b", stdout, re.M))
            and "ERROR collecting" not in stdout and "ModuleNotFoundError" not in stdout)


def test_pair(stage: str) -> dict:
    if stage not in {"before", "after"}:
        raise ValueError(stage)
    task = read_task()
    source = safe_source(task["target_file"])
    initial = safe_source(task["baseline_file"])
    if stage == "before" and file_sha(source) != file_sha(initial):
        raise RuntimeError("Baseline test requires unchanged before code; run reset-code")
    folder = run_dir(f"{stage}_tests")
    feature = _cmd_pytest(task["feature_tests"], stage, folder)
    regression = _cmd_pytest(task["regression_tests"], stage, folder)
    passed = (_functional_failure(feature) and regression["exit_code"] == 0) if stage == "before" else (
        feature["exit_code"] == 0 and regression["exit_code"] == 0)
    outcome = {"stage": stage, "acceptance": "PASS" if passed else "FAIL",
               "feature_exit_code": feature["exit_code"],
               "regression_exit_code": regression["exit_code"],
               "feature_behavior_failure": _functional_failure(feature),
               "code_sha256": file_sha(source), "log_dir": folder.relative_to(ROOT).as_posix()}
    save_json(folder / "summary.json", outcome)
    if not passed:
        raise RuntimeError(f"{stage} tests do not meet acceptance conditions; see {folder}: {outcome}")
    return outcome


def _strip_code(text: str) -> str:
    cleaned = text.strip()
    fence = re.fullmatch(r"```(?:python)?\s*\n(.*?)\n```", cleaned, flags=re.S | re.I)
    if fence:
        cleaned = fence.group(1)
    return cleaned.rstrip() + "\n"


def _validate_candidate(source: str, baseline: str) -> None:
    new_tree = ast.parse(source)
    old_tree = ast.parse(baseline)
    new_funcs = [n for n in new_tree.body if isinstance(n, ast.FunctionDef)]
    old_funcs = [n for n in old_tree.body if isinstance(n, ast.FunctionDef)]
    if len(new_funcs) != 1 or len(old_funcs) != 1 or new_funcs[0].name != "filter_products":
        raise ValueError("Model must keep the one original filter_products function")
    if ast.dump(new_funcs[0].args, include_attributes=False) != ast.dump(old_funcs[0].args, include_attributes=False):
        raise ValueError("Model must not change the public filter_products signature")
    # No new module-level executable statements or unrequested classes/functions.
    for node in new_tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue  # module docstring
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            continue
        if isinstance(node, ast.FunctionDef) and node.name == "filter_products":
            continue
        raise ValueError("Model output contains an unexpected top-level statement")
    for node in ast.walk(new_tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if not isinstance(node, ast.ImportFrom) or node.module != "__future__":
                raise ValueError("Model may not add imports")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec", "compile", "open", "__import__"}:
            raise ValueError("Unexpected execution/File IO by model")
    if source == baseline:
        raise ValueError("Model returned unchanged source")


def model_apply() -> dict:
    task = read_task()
    source_file = safe_source(task["target_file"])
    baseline_file = safe_source(task["baseline_file"])
    before = source_file.read_text(encoding="utf-8")
    if file_sha(source_file) != file_sha(baseline_file):
        raise RuntimeError("Model-apply must begin from the untouched baseline. Run reset-code to retry")
    ctx = context(include_powercontext=True)
    folder = run_dir("minimax_live")
    save_json(folder / "model_context.json", ctx)
    model_content, proof = generate(ctx)
    save_json(folder / "minimax_development_record.json", proof)
    (folder / "model_return.txt").write_text(model_content, encoding="utf-8")
    candidate = _strip_code(model_content)
    try:
        _validate_candidate(candidate, before)
    except (ValueError, SyntaxError) as exc:
        save_json(folder / "candidate_rejection.json", {"reason": str(exc), "time": timestamp()})
        raise
    (folder / "candidate.py").write_text(candidate, encoding="utf-8")
    source_file.write_text(candidate, encoding="utf-8")
    try:
        tests = test_pair("after")
    except Exception:
        source_file.write_text(before, encoding="utf-8")
        save_json(folder / "candidate_rejection.json", {
            "reason": "candidate tests failed; baseline restored", "time": timestamp()})
        raise
    diff = "".join(difflib.unified_diff(before.splitlines(True), candidate.splitlines(True),
                                        fromfile="a/workshop/inventory.py", tofile="b/workshop/inventory.py"))
    (folder / "code.diff").write_text(diff, encoding="utf-8")
    (folder / "before.py").write_text(before, encoding="utf-8")
    (folder / "after.py").write_text(candidate, encoding="utf-8")
    # The current generated snapshot becomes judge-replayable only after a real MiniMax call.
    after_path = ROOT / "snapshots" / "after" / "inventory.py"
    after_path.parent.mkdir(parents=True, exist_ok=True)
    after_path.write_text(candidate, encoding="utf-8")
    summary = {"provider": "MiniMax", "model": proof["model_returned"] or proof["model_requested"],
               "source": task["target_file"], "before_sha256": file_sha(baseline_file),
               "after_sha256": file_sha(source_file), "tests": tests,
               "evidence_folder": folder.relative_to(ROOT).as_posix(), "time": timestamp()}
    save_json(folder / "summary.json", summary)
    save_json(ROOT / "evidence" / "model_last_success.json", summary)
    return summary


def reset_code() -> dict:
    task = read_task()
    dest = safe_source(task["target_file"])
    shutil.copy2(safe_source(task["baseline_file"]), dest)
    return {"status": "RESET_TO_BASELINE", "sha256": file_sha(dest)}


def reproduce_offline() -> dict:
    """Never call MiniMax here; verify the exact stored before/after images with one test set."""
    task = read_task()
    after = ROOT / "snapshots" / "after" / "inventory.py"
    if not after.is_file():
        raise RuntimeError("After snapshot missing. Run REAL model-apply first; no simulated after evidence")
    dest = safe_source(task["target_file"])
    original = dest.read_bytes()
    folder = run_dir("offline_replay")
    try:
        dest.write_bytes(safe_source(task["baseline_file"]).read_bytes())
        before_f = _cmd_pytest(task["feature_tests"], "replay-before", folder / "before")
        before_r = _cmd_pytest(task["regression_tests"], "replay-before", folder / "before")
        dest.write_bytes(after.read_bytes())
        after_f = _cmd_pytest(task["feature_tests"], "replay-after", folder / "after")
        after_r = _cmd_pytest(task["regression_tests"], "replay-after", folder / "after")
        good = all([_functional_failure(before_f), before_r["exit_code"] == 0,
                    after_f["exit_code"] == 0, after_r["exit_code"] == 0])
    finally:
        dest.write_bytes(original)
    report = {"status": "PASS" if good else "FAIL", "before_feature_exit": before_f["exit_code"],
              "before_regression_exit": before_r["exit_code"],
              "after_feature_exit": after_f["exit_code"],
              "after_regression_exit": after_r["exit_code"],
              "restored_original_sha256": file_sha(dest), "log_dir": folder.relative_to(ROOT).as_posix()}
    save_json(folder / "summary.json", report)
    if not good:
        raise RuntimeError(f"Offline replay failed; see {folder}")
    return report
