"""The harness's OpenAI key: `OPENAI_API_KEY`, else the repository's gitignored `.env`.

Only test harnesses call this; the library never reads `.env` and takes the key as `api_key=`.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def openai_key() -> str:
    if key := os.environ.get("OPENAI_API_KEY"):
        return key
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENAI_API_KEY" and value.strip():
                return value.strip().strip("'\"")
    return ""
