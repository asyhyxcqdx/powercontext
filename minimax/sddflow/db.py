"""Real seekdb/OceanBase SQL storage. No SQLite fallback or fake in-memory DB."""

from __future__ import annotations

import os
from contextlib import contextmanager, closing
from pathlib import Path
from typing import Iterator

from .utils import ROOT, file_sha, read_task, safe_source, save_json, timestamp

TABLE_SQL = """
CREATE TABLE IF NOT EXISTS sdd_documents (
    task_id VARCHAR(100) NOT NULL,
    source_path VARCHAR(255) NOT NULL,
    kind VARCHAR(16) NOT NULL,
    symbol VARCHAR(100) NOT NULL,
    content LONGTEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    indexed_at VARCHAR(40) NOT NULL,
    PRIMARY KEY (task_id, source_path)
)
"""


@contextmanager
def connection() -> Iterator:
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("Missing PyMySQL: python -m pip install -r requirements.txt") from exc

    if os.getenv("OB_HOST"):
        # Explicit remote seekdb or OceanBase connection; never silently fall back.
        with closing(pymysql.connect(
            host=os.environ["OB_HOST"],
            port=int(os.getenv("OB_PORT", "2881")),
            user=os.getenv("OB_USER", "root@test"),
            password=os.getenv("OB_PASSWORD", ""),
            database=os.getenv("OB_DATABASE", "test"),
            charset="utf8mb4", autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )) as conn:
            yield conn
    else:
        try:
            import pylibseekdb
        except ImportError as exc:
            raise RuntimeError("Embedded seekdb is required: pip install pylibseekdb==1.4.0.post1") from exc
        dbpath = ROOT / "runtime" / "seekdb.db"
        dbpath.parent.mkdir(parents=True, exist_ok=True)
        with closing(pylibseekdb.open(str(dbpath))) as db:
            options = db.connection_options()
            with closing(pymysql.connect(
                database="test", autocommit=True,
                charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                **options,
            )) as conn:
                yield conn


def _docs() -> list[dict]:
    task = read_task()
    records = []
    for kind, paths in task["required_sources"].items():
        for rel in paths:
            file = safe_source(rel)
            text = file.read_text(encoding="utf-8")
            symbol = "filter_products" if "filter_products" in text else ""
            records.append({
                "source_path": rel,
                "kind": kind,
                "symbol": symbol,
                "content": text,
                "sha256": file_sha(file),
                "indexed_at": timestamp(),
            })
    return records


def ingest() -> dict:
    records = _docs()
    task_id = read_task()["task_id"]
    sql_log = []
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(TABLE_SQL)
            # Rebuild this task's small document set to prevent stale/removed source rows.
            cursor.execute("DELETE FROM sdd_documents WHERE task_id = %s", (task_id,))
            sql_log.append({"sql": "DELETE FROM sdd_documents WHERE task_id = %s",
                            "parameters": [task_id], "affected": cursor.rowcount})
            insert_sql = """INSERT INTO sdd_documents
                (task_id, source_path, kind, symbol, content, sha256, indexed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)"""
            for rec in records:
                cursor.execute(insert_sql, (task_id,) + tuple(rec[k] for k in (
                    "source_path", "kind", "symbol", "content", "sha256", "indexed_at")))
                sql_log.append({"sql": "INSERT INTO sdd_documents (...) VALUES (%s,...)",
                                "source_path": rec["source_path"], "sha256": rec["sha256"],
                                "affected": cursor.rowcount})
            cursor.execute("SELECT source_path, kind, sha256 FROM sdd_documents WHERE task_id = %s ORDER BY source_path",
                           (task_id,))
            persisted = list(cursor.fetchall())
    if {r["source_path"] for r in persisted} != {r["source_path"] for r in records}:
        raise RuntimeError("seekdb persistence verification failed")
    result = {"database": "OceanBase/seekdb SQL (embedded if OB_HOST unset)",
              "ingested": len(records), "rows_returned": persisted, "queries": sql_log,
              "time": timestamp()}
    save_json(ROOT / "evidence" / "database_ingest.json", result)
    return result


def search(query: str, keywords: list[str]) -> tuple[list[dict], dict]:
    # Retrieval is driven by actual task terms, not a hard-coded answer map.
    terms = list(dict.fromkeys(w.lower().strip() for w in keywords if w.strip()))
    if not terms:
        raise ValueError("At least one query term required")
    where = " OR ".join("(LOWER(content) LIKE %s OR LOWER(source_path) LIKE %s)" for _ in terms)
    sql = ("SELECT source_path, kind, symbol, content, sha256, indexed_at "
           "FROM sdd_documents WHERE task_id = %s AND (" + where + ") ORDER BY source_path")
    params = [read_task()["task_id"]] + [f"%{w}%" for w in terms for _ in range(2)]
    with connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            docs = list(cursor.fetchall())
    for doc in docs:
        real = safe_source(doc["source_path"])
        if file_sha(real) != doc["sha256"]:
            raise RuntimeError(f"Stale database row for {doc['source_path']}; run ingest again")
    audit = {"time": timestamp(), "task_query": query, "sql": sql,
             "parameters": params, "returned_rows": [
                 {"source_path": d["source_path"], "kind": d["kind"],
                  "sha256": d["sha256"]} for d in docs]}
    save_json(ROOT / "evidence" / "database_last_query.json", audit)
    return docs, audit
