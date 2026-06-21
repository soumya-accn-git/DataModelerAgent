"""
Central configuration for DataModelerAgent.

Credentials are loaded in this priority order:
  1. System environment variables (highest priority)
  2. .env file (canonical secrets source — git-ignored)
  3. Neo4j_instance_detl.txt (legacy fallback)
  4. Hardcoded defaults (lowest priority)

To update credentials: edit .env (copy from .env.example if missing)
"""

import os
import re

ROOT_DIR = os.path.dirname(__file__)


# ── File loader ───────────────────────────────────────────────────────────────

def _load_file(filename: str) -> None:
    """Load KEY=VALUE pairs from a file into os.environ (no overwrite)."""
    path = os.path.join(ROOT_DIR, filename)
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and blank lines
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip()
            if key not in os.environ:
                os.environ[key] = val


# Load in reverse priority (later = higher priority, won't overwrite earlier)
_load_file("Neo4j_instance_detl.txt")   # legacy fallback
_load_file(".env")                        # canonical secrets source (wins)


# ── Neo4j Aura (from Neo4j_instance_detl.txt) ─────────────────────────────────
NEO4J_URI         = os.environ.get("NEO4J_URI",           "neo4j+s://2f8b84a7.databases.neo4j.io")
NEO4J_USER        = os.environ.get("NEO4J_USERNAME",      "2f8b84a7")
NEO4J_PASSWORD    = os.environ.get("NEO4J_PASSWORD",      "")
NEO4J_DATABASE    = os.environ.get("NEO4J_DATABASE",      "2f8b84a7")
AURA_INSTANCEID   = os.environ.get("AURA_INSTANCEID",     "2f8b84a7")
AURA_INSTANCENAME = os.environ.get("AURA_INSTANCENAME",   "Instance01")

# ── Ollama ────────────────────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

# Generation options. num_ctx is the input context window — Ollama's small
# default silently truncates long BRDs + the SKILL.md prompt, which is the main
# cause of missed entities/relationships. num_predict is the max output tokens.
OLLAMA_NUM_CTX     = int(os.environ.get("OLLAMA_NUM_CTX",     "32768"))
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "8192"))
# Publish back to the environment so agent.ollama_client (which reads these
# env vars at call time) picks up any file/.env override.
os.environ.setdefault("OLLAMA_NUM_CTX",     str(OLLAMA_NUM_CTX))
os.environ.setdefault("OLLAMA_NUM_PREDICT", str(OLLAMA_NUM_PREDICT))

# ── ChromaDB ──────────────────────────────────────────────────────────────────
CHROMA_PATH = os.environ.get("CHROMA_PATH", "./chroma_db")
