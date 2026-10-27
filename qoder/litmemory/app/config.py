"""Runtime configuration for LitMemory.

All values can be overridden with environment variables (see .env.example).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
load_dotenv(PROJECT_DIR / ".env")

DATA_DIR = Path(os.environ.get("LITMEMORY_DATA_DIR", str(PROJECT_DIR / "data"))).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR = Path(os.environ.get("LITMEMORY_MODEL_DIR", str(DATA_DIR / "models"))).resolve()
MODEL_DIR.mkdir(parents=True, exist_ok=True)

# --- seekdb ---------------------------------------------------------------
SEEKDB_HOST = os.environ.get("SEEKDB_HOST", "127.0.0.1")
SEEKDB_PORT = int(os.environ.get("SEEKDB_PORT", "2881"))
SEEKDB_USER = os.environ.get("SEEKDB_USER", "root")
SEEKDB_PASSWORD = os.environ.get("SEEKDB_PASSWORD", "")
SEEKDB_DATABASE = os.environ.get("SEEKDB_DATABASE", "litmemory")
SEEKDB_TENANT = os.environ.get("SEEKDB_TENANT", "sys")
SEEKDB_COLLECTION = os.environ.get("SEEKDB_COLLECTION", "litmemory_notes")

# --- PowerContext ---------------------------------------------------------
POWERCONTEXT_URL = os.environ.get("POWERCONTEXT_URL", "http://127.0.0.1:8000")
POWERCONTEXT_SCOPE = os.environ.get("POWERCONTEXT_SCOPE", "project:litmemory:demo")
POWERCONTEXT_TIMEOUT = float(os.environ.get("POWERCONTEXT_TIMEOUT", "20"))

# --- embeddings -----------------------------------------------------------
# BGE-small-zh gives good Chinese semantic recall while staying ~100 MB.
EMBEDDING_MODEL = os.environ.get("LITMEMORY_EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
EMBEDDING_DIM_FALLBACK = int(os.environ.get("LITMEMORY_EMBEDDING_DIM", "512"))

# --- app ------------------------------------------------------------------
APP_HOST = os.environ.get("LITMEMORY_HOST", "0.0.0.0")
APP_PORT = int(os.environ.get("LITMEMORY_PORT", "8765"))
AUTOSEED = os.environ.get("LITMEMORY_AUTOSEED", "1") not in {"0", "false", "False", ""}
LOG_DIR = DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
