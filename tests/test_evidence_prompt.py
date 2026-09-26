"""
Offline tests for:

A. EvidenceVerifier._llm_classify() prompt layout
B. Agent answer helpers when the LLM fails

Run (from repository root):

    pytest -q tests/test_evidence_prompt.py
"""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
AGENT_DIR = ROOT / "agent"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from agent.evidence_verifier import EvidenceVerifier


# ============================================================
# Fake LLMs
# ============================================================

class RecordingLLM:

    def __init__(self, response):
        self.response = response
        self.messages = None

    def chat(self, messages):
        self.messages = messages
        return self.response


class FailingLLM:

    def chat(self, messages):
        raise RuntimeError("ollama down")


# ============================================================
# A. Prompt layout
# ============================================================

QUESTION = "Qwen mới nhất hiện nay là gì?"
TITLE = "Qwen 4 Max announced at Apsara 2026"
CONTENT = "Alibaba announced Qwen 4 Max, its newest model family."


def classify(llm):
    return EvidenceVerifier(llm)._llm_classify(
        QUESTION,
        TITLE,
        CONTENT,
        "EVIDENCE_1_R1",
        "https://example.com/qwen",
    )


def test_real_evidence_is_in_last_user_message():
    llm = RecordingLLM(
        '{"label": "SUPPORTS", "reason": "Mentions Qwen 4 Max", "confidence": 0.9}'
    )

    classify(llm)

    system, user = llm.messages

    assert system["role"] == "system"
    assert user["role"] == "user"

    # Real question/evidence only in the user message.
    assert QUESTION in user["content"]
    assert TITLE in user["content"]
    assert CONTENT in user["content"]

    assert QUESTION not in system["content"]
    assert TITLE not in system["content"]

    # Examples are explicitly marked as examples.
    assert "VÍ DỤ MINH HỌA" in system["content"]


def test_rules_contain_literal_json_schema():
    llm = RecordingLLM('{"label": "IRRELEVANT", "reason": "x", "confidence": 0.1}')

    classify(llm)

    system = llm.messages[0]["content"]

    # rules is a plain string: braces must be single, not "{{".
    assert '"label": "SUPPORTS | CONTRADICTS | IRRELEVANT"' in system
    assert "{{" not in system


def test_long_content_is_truncated():
    llm = RecordingLLM('{"label": "IRRELEVANT", "reason": "x", "confidence": 0.1}')

    EvidenceVerifier(llm)._llm_classify(
        QUESTION, TITLE, "x" * 5000, "R1", "https://example.com"
    )

    assert "x" * 1500 in llm.messages[1]["content"]
    assert "x" * 1501 not in llm.messages[1]["content"]


def test_supports_label_is_kept():
    result = classify(
        RecordingLLM(
            '{"label": "SUPPORTS", "reason": "Mentions Qwen 4 Max", "confidence": 0.9}'
        )
    )

    assert result["label"] == EvidenceVerifier.SUPPORTS
    assert result["method"] == "llm-fallback"


def test_invalid_json_is_irrelevant():
    result = classify(RecordingLLM("not json"))

    assert result["label"] == EvidenceVerifier.IRRELEVANT
    assert result["method"] == "llm-fallback-error"


# ============================================================
# B. Agent answer helpers with a failing LLM
#
# agent/agent.py is loaded under another module name so it
# does not shadow the "agent" package imported above.
# ============================================================

@pytest.fixture(scope="module")
def agent_module():
    pytest.importorskip("ollama")
    pytest.importorskip("ddgs")

    inserted = str(AGENT_DIR) not in sys.path

    if inserted:
        sys.path.insert(0, str(AGENT_DIR))

    try:
        spec = importlib.util.spec_from_file_location(
            "bcos_agent_core",
            AGENT_DIR / "agent.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if inserted and str(AGENT_DIR) in sys.path:
            sys.path.remove(str(AGENT_DIR))

    return module


def fake_agent():
    verifier = EvidenceVerifier(FailingLLM())

    return SimpleNamespace(
        llm=FailingLLM(),
        evidence_verifier=verifier,
    )


def test_insufficient_answer_survives_llm_failure(agent_module):
    answer = agent_module.Agent._answer_insufficient(
        fake_agent(),
        QUESTION,
        {"status": EvidenceVerifier.INSUFFICIENT},
    )

    assert isinstance(answer, str)
    assert "chưa đủ" in answer


def test_conflicted_answer_survives_llm_failure(agent_module):
    answer = agent_module.Agent._answer_conflicted(
        fake_agent(),
        QUESTION,
        {"status": EvidenceVerifier.CONFLICTED, "classifications": []},
    )

    assert isinstance(answer, str)
    assert "mâu thuẫn" in answer
