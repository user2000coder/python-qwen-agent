"""
BCOS Configuration
CPU Ollama Mode
"""


# ==============================
# Ollama
# ==============================

MODEL = "qwen2.5:3b"


OLLAMA_HOST = (
    "http://127.0.0.1:11434"
)



# ==============================
# Generation
# ==============================

# CPU nên để thấp
TEMPERATURE = 0.2



# ==============================
# Agent Control
# ==============================

MAX_TOOL_ITERATIONS = 1



# ==============================
# Search
# ==============================

SEARCH_RESULTS = 5


# Explicit backend list.
#
# ddgs "auto" prepends wikipedia + grokipedia and sorts by engine
# priority, while max_workers = min(providers, ceil(max_results/10)+1)
# is only 2 at SEARCH_RESULTS = 5 — so the entire first batch went to
# two encyclopedia engines that return one result each. These six are
# real search backends (bing and yandex ship disabled upstream).

SEARCH_BACKEND = (
    "duckduckgo,brave,mojeek,"
    "startpage,google,yahoo"
)


# ddgs defaults to region "us-en", which pins every engine to English
# and en.wikipedia.org for a Vietnamese-language agent.

SEARCH_REGION = "vn-vi"


# Per-engine wait inside ddgs is this value, and it is applied once
# per engine beyond max_workers — so keep it small.

SEARCH_TIMEOUT = 8


# Retries on a transient backend failure. "No results found" is not
# transient and is not retried.

SEARCH_RETRIES = 2