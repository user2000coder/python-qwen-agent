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