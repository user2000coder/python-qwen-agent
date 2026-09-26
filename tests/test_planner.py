"""
Offline tests for BCOS Planner, Planner.parse(),
ProblemReconstructor and ProblemClassifier.

No Ollama, no network: a fake LLM is injected.

Run (from repository root):

    pytest -q tests/test_planner.py
"""

import sys
from pathlib import Path

import pytest


# ============================================================
# Import planner modules from agent/.
#
# agent/ uses top-level imports ("from protocol import ...",
# "from problem.models import ..."), so agent/ must be on
# sys.path while importing. It is removed afterwards so that
# "import agent" elsewhere (tests/test_evidence_verifier.py)
# is not shadowed by agent/agent.py.
# ============================================================

AGENT_DIR = str(
    Path(__file__).resolve().parents[1] / "agent"
)

_inserted = AGENT_DIR not in sys.path

if _inserted:
    sys.path.insert(0, AGENT_DIR)

try:
    from planner import Planner, PlannerResult
    from protocol import Action
    from problem import (
        ProblemClassifier,
        ProblemReconstructor,
        ProblemType,
    )
finally:
    if _inserted and AGENT_DIR in sys.path:
        sys.path.remove(AGENT_DIR)


# ============================================================
# Fake LLM
# ============================================================

class FakeLLM:

    def __init__(self, response='{"action": "answer", "parameters": {}}', error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def chat(self, messages):
        self.calls += 1

        if self.error is not None:
            raise self.error

        return self.response


def history(text):
    return [{"role": "user", "content": text}]


def model_problem(text):
    problem = ProblemReconstructor().reconstruct(text)
    return ProblemClassifier().classify(problem)


# ============================================================
# Deterministic routing (LLM must NOT be called)
# ============================================================

@pytest.mark.parametrize(
    "question, expected_expression",
    [
        ("2 + 3", "2 + 3"),
        ("tính 10 * 20", "10 * 20"),
        ("Tính 125 * 8", "125 * 8"),
        # Expression must come from the ProblemModel,
        # not the raw question text.
        ("2 + 3 bằng mấy?", "2 + 3"),
    ],
)
def test_calculator_routing(question, expected_expression):
    llm = FakeLLM()
    result = Planner(llm).plan(history(question))

    assert result.action == Action.CALCULATOR
    assert result.parameters == {"expression": expected_expression}
    assert llm.calls == 0


def test_calculation_without_expression_is_not_sent_to_calculator():
    question = "tính tổng doanh thu"

    assert model_problem(question).primary_problem_type == ProblemType.CALCULATION

    llm = FakeLLM()
    result = Planner(llm).plan(history(question))

    assert result.action != Action.CALCULATOR
    assert llm.calls == 1


@pytest.mark.parametrize(
    "question, expected_types",
    [
        ("giải phương trình 2*x + 5 = 15", {ProblemType.MATHEMATICS}),
        ("tại sao code Python này bị lỗi?", {ProblemType.DEBUG}),
        (
            "tại sao chương trình chạy chậm?",
            {ProblemType.CAUSAL, ProblemType.OPTIMIZATION, ProblemType.DEBUG},
        ),
        ("nên dùng SQLite hay PostgreSQL?", {ProblemType.DECISION}),
        ("thiết kế kiến trúc AI agent", {ProblemType.DESIGN}),
        ("API bị deadlock khi concurrent writes", {ProblemType.DEBUG}),
    ],
)
def test_complex_routing(question, expected_types):
    assert model_problem(question).primary_problem_type in expected_types

    llm = FakeLLM()
    result = Planner(llm).plan(history(question))

    assert result.action == Action.COMPLEX
    assert result.parameters == {}
    assert llm.calls == 0


def test_latest_qwen_routes_to_search():
    question = "Qwen mới nhất hiện nay là gì?"

    assert model_problem(question).primary_problem_type == ProblemType.FACT_LOOKUP

    llm = FakeLLM()
    result = Planner(llm).plan(history(question))

    assert result.action == Action.SEARCH
    assert result.parameters == {"query": question}
    assert llm.calls == 0


def test_time_sensitive_fact_lookup_routes_to_search():
    # "hiện nay" is not a Planner.need_search() keyword;
    # the ProblemModel's required external evidence routes it.
    question = "Ai là CEO của OpenAI hiện nay?"

    llm = FakeLLM()
    result = Planner(llm).plan(history(question))

    assert result.action == Action.SEARCH
    assert result.parameters == {"query": question}
    assert llm.calls == 0


def test_stable_fact_is_not_forced_to_search():
    # A question mark alone must not force SEARCH.
    question = "Python là gì?"

    assert model_problem(question).primary_problem_type == ProblemType.FACT_LOOKUP

    llm = FakeLLM('{"action": "answer", "parameters": {}}')
    result = Planner(llm).plan(history(question))

    assert result.action == Action.ANSWER
    assert result.parameters == {}
    assert llm.calls == 1


# ============================================================
# Empty input
# ============================================================

@pytest.mark.parametrize(
    "messages",
    [
        [],
        history(""),
        history("   \n\t "),
        [{"role": "user", "content": None}],
        [{"role": "user"}],
        ["not a dict"],
    ],
)
def test_empty_input_returns_answer(messages):
    llm = FakeLLM()
    result = Planner(llm).plan(messages)

    assert result.action == Action.ANSWER
    assert result.parameters == {}
    assert llm.calls == 0


def test_reconstructor_rejects_empty_input():
    with pytest.raises(ValueError):
        ProblemReconstructor().reconstruct("   ")


# ============================================================
# LLM fallback robustness
# ============================================================

FALLBACK_QUESTION = "Python là gì?"


def test_llm_exception_returns_answer():
    llm = FakeLLM(error=RuntimeError("ollama down"))
    result = Planner(llm).plan(history(FALLBACK_QUESTION))

    assert result.action == Action.ANSWER
    assert llm.calls == 1


def test_llm_invalid_json_returns_answer():
    result = Planner(FakeLLM("not json at all")).plan(history(FALLBACK_QUESTION))

    assert result.action == Action.ANSWER


def test_llm_unknown_action_returns_answer():
    result = Planner(
        FakeLLM('{"action": "mathematics", "parameters": {}}')
    ).plan(history(FALLBACK_QUESTION))

    assert result.action == Action.ANSWER


def test_llm_search_without_query_uses_question():
    result = Planner(
        FakeLLM('{"action": "search", "parameters": {}}')
    ).plan(history(FALLBACK_QUESTION))

    assert result.action == Action.SEARCH
    assert result.parameters == {"query": FALLBACK_QUESTION}


def test_llm_calculator_without_expression_returns_answer():
    result = Planner(
        FakeLLM('{"action": "calculator", "parameters": {"expression": null}}')
    ).plan(history(FALLBACK_QUESTION))

    assert result.action == Action.ANSWER


def test_llm_file_without_path_returns_answer():
    result = Planner(
        FakeLLM('{"action": "file"}')
    ).plan(history(FALLBACK_QUESTION))

    assert result.action == Action.ANSWER


# ============================================================
# Planner.parse()
# ============================================================

@pytest.fixture
def planner():
    return Planner(FakeLLM())


def test_parse_plain_json(planner):
    result = planner.parse(
        '{"action":"calculator","parameters":{"expression":"1+1"}}'
    )

    assert isinstance(result, PlannerResult)
    assert result.action == Action.CALCULATOR
    assert result.parameters == {"expression": "1+1"}


def test_parse_markdown_json(planner):
    text = (
        "```json\n"
        '{"action": "search", "parameters": {"query": "Qwen"}}\n'
        "```"
    )

    result = planner.parse(text)

    assert result.action == Action.SEARCH
    assert result.parameters == {"query": "Qwen"}


def test_parse_json_inside_text(planner):
    text = (
        'Tôi chọn: {"action": "complex", "parameters": {"x": 1}} '
        "vì câu hỏi cần phân tích."
    )

    result = planner.parse(text)

    assert result.action == Action.COMPLEX
    assert result.parameters == {}


def test_parse_json_with_extra_braces_in_text(planner):
    text = (
        "Note {not json}. "
        '{"action": "file", "parameters": {"path": "data/a.txt"}} '
        "trailing {brace}"
    )

    result = planner.parse(text)

    assert result.action == Action.FILE
    assert result.parameters == {"path": "data/a.txt"}


def test_parse_action_case_and_whitespace(planner):
    result = planner.parse('{"action": " Search ", "parameters": {"query": "x"}}')

    assert result.action == Action.SEARCH
    assert result.parameters == {"query": "x"}


@pytest.mark.parametrize(
    "text",
    [
        "",
        "no json here",
        '{"action": "calculator", "parameters": ',
        "[1, 2, 3]",
        '{"action": "unknown_tool", "parameters": {}}',
        '{"action": 42, "parameters": {}}',
        '{"action": null}',
    ],
)
def test_parse_invalid_returns_answer(planner, text):
    result = planner.parse(text)

    assert result.action == Action.ANSWER
    assert result.parameters == {}


@pytest.mark.parametrize("value", [None, 123, {"a": 1}, ["x"]])
def test_parse_non_text_response_returns_answer(planner, value):
    result = planner.parse(value)

    assert result.action == Action.ANSWER


def test_parse_missing_action_defaults_to_answer(planner):
    result = planner.parse('{"parameters": {"query": "x"}}')

    assert result.action == Action.ANSWER
    assert result.parameters == {}


def test_parse_missing_parameters(planner):
    result = planner.parse('{"action": "calculator"}')

    assert result.action == Action.CALCULATOR
    assert result.parameters == {"expression": ""}


@pytest.mark.parametrize(
    "parameters, expected",
    [
        ('{"expression": null}', ""),
        ('{"expression": 5}', "5"),
        ('{"expression": 2.5}', "2.5"),
        ('{"expression": true}', ""),
        ('{"expression": ["1+1"]}', ""),
        ('{"expression": {"a": 1}}', ""),
        ('{"expression": "  1 + 1  "}', "1 + 1"),
        ('["expression", "1+1"]', ""),
        ('"1+1"', ""),
    ],
)
def test_parse_wrong_parameter_types(planner, parameters, expected):
    result = planner.parse(
        '{"action": "calculator", "parameters": ' + parameters + "}"
    )

    assert result.action == Action.CALCULATOR
    assert result.parameters == {"expression": expected}


# ============================================================
# Reconstruction ≠ Classification
# ============================================================

def test_reconstructor_does_not_classify():
    problem = ProblemReconstructor().reconstruct("tính 10 * 20")

    assert problem.primary_problem_type == ProblemType.UNKNOWN
    assert problem.problem_types == []
    assert "classification_primary" not in problem.metadata


def test_reconstructor_extracts_equation_and_unknown():
    problem = ProblemReconstructor().reconstruct(
        "giải phương trình 2*x + 5 = 15"
    )

    assert problem.metadata["equations"] == ["2*x + 5 = 15"]
    assert [u.name for u in problem.unknowns] == ["x"]
    assert "calculation_expression" not in problem.metadata


def test_reconstructor_extracts_calculation_expression():
    problem = ProblemReconstructor().reconstruct("tính 10 * 20")

    assert problem.metadata["calculation_expression"] == "10 * 20"
    assert any(
        r.name == "calculation" and r.expression == "10 * 20"
        for r in problem.relations
    )


def test_question_mark_evidence_is_not_required():
    problem = ProblemReconstructor().reconstruct("Python là gì?")

    assert problem.evidence_requirements
    assert not any(r.required for r in problem.evidence_requirements)


def test_time_sensitive_evidence_is_required():
    problem = ProblemReconstructor().reconstruct("Qwen mới nhất hiện nay là gì?")

    assert any(
        r.required and r.source_type == "external"
        for r in problem.evidence_requirements
    )
