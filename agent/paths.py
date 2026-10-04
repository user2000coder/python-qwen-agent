"""
BCOS Runtime Paths

Every runtime resource (prompts, history, logs, cache, data) lives
next to the BCOS source tree, not next to the process working
directory.

Resolving these paths against the current working directory made
BCOS behave differently depending on where it was launched from:

    python agent/main.py        (cwd = project root)
        -> prompts/bcos.txt not found
        -> the BCOS system prompt was silently replaced by a stub
        -> history written to ./history/conversation.json

    cd agent && python main.py  (cwd = agent)
        -> prompts/bcos.txt found
        -> history written to agent/history/conversation.json

The two divergent conversation histories in this repository are the
observable trace of that defect.
"""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent

PROMPTS_DIR = BASE_DIR / "prompts"

HISTORY_DIR = BASE_DIR / "history"

LOGS_DIR = BASE_DIR / "logs"

CACHE_DIR = BASE_DIR / "cache"

DATA_DIR = BASE_DIR / "data"
