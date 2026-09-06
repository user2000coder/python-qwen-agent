from pathlib import Path

# ============================================
# BCOS Agent Scaffold
# ============================================

DIRECTORIES = [
    "agent",
    "agent/tools",
    "agent/prompts",
    "agent/logs",
    "agent/history",
    "agent/cache",
    "agent/data",
]

FILES = [
    # Core
    "agent/main.py",
    "agent/config.py",
    "agent/llm.py",
    "agent/protocol.py",
    "agent/planner.py",
    "agent/agent.py",
    "agent/memory.py",

    # Tools
    "agent/tools/__init__.py",
    "agent/tools/search.py",
    "agent/tools/calculator.py",
    "agent/tools/file.py",
    "agent/tools/python.py",

    # Prompt
    "agent/prompts/bcos.txt",

    # Runtime
    "agent/logs/agent.log",
    "agent/history/conversation.json",

    # Cache
    "agent/cache/.gitkeep",

    # Data
    "agent/data/.gitkeep",

    # Project
    "agent/requirements.txt",
    "agent/README.md",
]

# ============================================
# Create Directories
# ============================================

print("=" * 60)
print("Creating BCOS Agent Project...")
print("=" * 60)

for directory in DIRECTORIES:
    Path(directory).mkdir(parents=True, exist_ok=True)
    print(f"[DIR ] {directory}")

# ============================================
# Create Files
# ============================================

for file in FILES:

    path = Path(file)

    if not path.exists():
        path.touch()
        print(f"[FILE] {file}")
    else:
        print(f"[SKIP] {file}")

print("\n" + "=" * 60)
print("✅ BCOS Agent scaffold created successfully!")
print("=" * 60)

print(
"""
Project Structure

agent/
│
├── main.py
├── config.py
├── llm.py
├── protocol.py
├── planner.py
├── agent.py
├── memory.py
│
├── tools/
│   ├── __init__.py
│   ├── search.py
│   ├── calculator.py
│   ├── file.py
│   └── python.py
│
├── prompts/
│   └── bcos.txt
│
├── logs/
│   └── agent.log
│
├── history/
│   └── conversation.json
│
├── cache/
│
├── data/
│
├── requirements.txt
└── README.md
"""
)