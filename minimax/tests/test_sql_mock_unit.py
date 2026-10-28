"""Fake DB driver contract test; *not* evidence of a seekdb connection."""

import sqlite3
from contextlib import contextmanager

from sddflow import db


class Cursor:
    def __init__(self, conn):
        self.cur = conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.cur.close()

    def execute(self, sql, params=()):
        self.cur.execute(sql.replace("%s", "?"), params)
        self.rowcount = self.cur.rowcount
        return self

    def fetchall(self):
        return [dict(row) for row in self.cur.fetchall()]


class SqliteShim:
    def __init__(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row

    def cursor(self):
        return Cursor(self.raw)


def test_index_and_retrieve_really_use_sql(monkeypatch):
    driver = SqliteShim()
    sql_calls = []

    @contextmanager
    def fake_connection():
        yield driver

    monkeypatch.setattr(db, "connection", fake_connection)
    monkeypatch.setattr(db, "save_json", lambda *args: None)
    try:
        index = db.ingest()
        assert index["ingested"] == 4
        rows, audit = db.search("min_stock", ["filter_products", "min_stock"])
        assert {row["kind"] for row in rows} == {"spec", "code", "test"}
        assert len(rows) == 4
        assert "WHERE task_id = %s AND (" in audit["sql"]
        assert "specs/inventory_filter.md" in {r["source_path"] for r in rows}
    finally:
        driver.raw.close()
