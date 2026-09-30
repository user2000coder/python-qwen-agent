"""
Regression tests for the BCOS evidence chain.

Run:

    python tests/test_evidence_chain.py

Every defect covered here had the same symptom — the agent saying
"evidence hiện có chưa đủ", or answering from model memory — while
the cause was somewhere else entirely:

    * the planner never routing to the tool
    * the tool failing and the failure being relabelled
      "not enough evidence"
    * a successful payload being dropped for having the wrong shape
    * the Judge never receiving the evidence at all

Offline by design: no Ollama, no network.
"""

import io
import contextlib
import json
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

AGENT_DIR = ROOT / "agent"

for entry in (str(ROOT), str(AGENT_DIR)):

    if entry not in sys.path:
        sys.path.insert(0, entry)


# ============================================================
# Stub Ollama before importing anything that reaches it.
# ============================================================

_INSUFFICIENT = (
    "Xin lỗi, evidence hiện có chưa đủ "
    "để trả lời câu hỏi này."
)


class _FakeOllamaClient:

    def __init__(self, host=None):
        pass

    def chat(self, **kwargs):

        if kwargs.get("stream"):

            return iter(
                [
                    {
                        "message": {
                            "content": _INSUFFICIENT
                        }
                    }
                ]
            )

        return {
            "message": {
                "content": _INSUFFICIENT
            }
        }


_fake_ollama = types.ModuleType("ollama")

_fake_ollama.Client = _FakeOllamaClient

sys.modules.setdefault(
    "ollama",
    _fake_ollama,
)


from agent import Agent
from paths import DATA_DIR
from planner import Planner
from protocol import Action
from tools.search import SearchTool


# ============================================================
# Helpers
# ============================================================

class PlannerLLM:
    """Planner LLM that must never be reached."""

    def chat(self, messages):
        raise AssertionError(
            "LLM planner fallback reached: routing is no "
            "longer deterministic for this input"
        )


class BoomLLM:
    """Planner LLM that always fails."""

    def chat(self, messages):
        raise ConnectionError(
            "Ollama down"
        )


def plan(question, llm=None):

    planner = Planner(
        llm or PlannerLLM()
    )

    return planner.plan(
        [
            {
                "role": "user",
                "content": question,
            }
        ]
    )


def make_agent():

    bcos = Agent()

    bcos.trace_enabled = False

    return bcos


def ask(bcos, question):
    """Run a question, returning (answer, captured stdout)."""

    buffer = io.StringIO()

    with contextlib.redirect_stdout(
        buffer
    ):

        out = bcos.ask(
            question
        )

        if (
            hasattr(out, "__iter__")
            and not isinstance(out, str)
        ):
            out = "".join(out)

    return out, buffer.getvalue()


class FailingSearch:

    def run(self, query, **kwargs):

        return {
            "success": False,
            "source": "web_search",
            "query": query,
            "error": "403 Forbidden",
            "count": 0,
            "results": [],
        }


class EmptySearch:

    def run(self, query, **kwargs):

        return {
            "success": True,
            "source": "web_search",
            "query": query,
            "count": 0,
            "results": [],
        }


class GoodSearch:

    MARKER = "ZZ_EVIDENCE_MARKER_7781"

    def run(self, query, **kwargs):

        return {
            "success": True,
            "source": "web_search",
            "query": query,
            "count": 1,
            "results": [
                {
                    "title": "Redis distributed locks",
                    "url": "https://redis.io/docs/locks",
                    "content": (
                        f"{self.MARKER} Redis dùng "
                        "SET NX PX cho distributed lock."
                    ),
                }
            ],
        }


# ============================================================
# TEST 1 — a failed tool is not "not enough evidence"
# ============================================================

def test_failed_search_is_reported_as_a_tool_failure():

    bcos = make_agent()

    bcos.tools[
        Action.SEARCH
    ] = FailingSearch()

    answer, captured = ask(
        bcos,
        "ai là tổng thống mỹ 2026",
    )

    assert "403" in answer, (
        "The tool's own error must reach the user, not be "
        f"replaced by a verdict about the claim:\n{answer}"
    )

    assert "chưa đủ" not in answer, (
        "A blocked search must not be reported as the "
        f"evidence being insufficient:\n{answer}"
    )

    assert "Tool hoàn tất" not in captured, (
        "Success must not be announced for a failed tool"
    )


# ============================================================
# TEST 2 — payloads with no `results` list still reach the
#          verifier
# ============================================================

def test_structured_payloads_are_made_verifiable():

    bcos = make_agent()

    # FileTool shape.
    adapted = bcos.as_verifiable_result(
        {
            "success": True,
            "file": "data/notes.txt",
            "content": "SQLite hỗ trợ SAVEPOINT.",
            "confidence": "high",
        }
    )

    results = adapted.get(
        "results"
    )

    assert isinstance(results, list) and results, (
        "FileTool payload must gain a results list"
    )

    assert "SAVEPOINT" in results[0]["content"], (
        "The file content must survive the adaptation"
    )

    # CoinGecko shape.
    adapted = bcos.as_verifiable_result(
        {
            "success": True,
            "source": "CoinGecko",
            "data_type": "crypto_price",
            "asset": "Bitcoin",
            "symbol": "BTC",
            "price_usd": 61234.5,
            "confidence": "high",
        }
    )

    results = adapted.get(
        "results"
    )

    assert isinstance(results, list) and results, (
        "CoinGecko payload must gain a results list"
    )

    assert "61234.5" in results[0]["content"], (
        "The fetched price must survive the adaptation"
    )

    # A payload that already has results is left alone.
    original = {
        "success": True,
        "results": [
            {
                "title": "t",
                "url": "u",
                "content": "c",
            }
        ],
    }

    assert (
        bcos.as_verifiable_result(original)
        is original
    ), (
        "A payload that already carries results must not "
        "be rewritten"
    )


# ============================================================
# TEST 3 — a file that was read produces an answer
# ============================================================

def test_file_content_reaches_the_verifier():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    sample = DATA_DIR / "__chain_sample.txt"

    sample.write_text(
        "SQLite hỗ trợ SAVEPOINT trong transaction.",
        encoding="utf-8",
    )

    try:

        bcos = make_agent()

        buffer = io.StringIO()

        with contextlib.redirect_stdout(
            buffer
        ):

            answer = "".join(
                bcos._handle_tool(
                    "SQLite có hỗ trợ SAVEPOINT không?",
                    Action.FILE,
                    {
                        "path": f"data/{sample.name}"
                    },
                )
            )

        assert "chưa đủ" not in answer, (
            "A file that was read successfully must not "
            f"yield an insufficient-evidence answer:\n{answer}"
        )

        assert _INSUFFICIENT not in answer, (
            "The answer must come from the verified file, "
            "not from the LLM fallback"
        )

    finally:

        sample.unlink(
            missing_ok=True
        )


# ============================================================
# TEST 4 — the Judge receives the evidence
# ============================================================

def test_judge_receives_evidence():

    prompts = []

    class RecordingClient:

        def __init__(self, host=None):
            pass

        def chat(self, **kwargs):

            prompts.append(
                "".join(
                    message.get("content", "")
                    for message in kwargs.get(
                        "messages",
                        []
                    )
                )
            )

            content = "KẾT LUẬN: ..."

            if kwargs.get("stream"):

                return iter(
                    [
                        {
                            "message": {
                                "content": content
                            }
                        }
                    ]
                )

            return {
                "message": {
                    "content": content
                }
            }

    bcos = make_agent()

    bcos.llm.client = RecordingClient()

    bcos.council.llm = bcos.llm

    bcos.tools[
        Action.SEARCH
    ] = GoodSearch()

    ask(
        bcos,
        "Nên dùng Redis lock hay PostgreSQL lock?",
    )

    assert len(prompts) >= 3, (
        "Expected at least the two workers and the Judge, "
        f"got {len(prompts)} LLM calls"
    )

    judge_prompt = prompts[-1]

    assert GoodSearch.MARKER in judge_prompt, (
        "The Judge's prompt must contain the retrieved "
        "evidence. Council.compact_evidence read a 'result' "
        "key that Agent.format_complex_evidence does not "
        "emit, so every entry collapsed to "
        "source='', success=false, results=[]."
    )

    assert "EVIDENCE_1" in judge_prompt, (
        "Citation anchors must reach the Judge"
    )


# ============================================================
# TEST 5 — zero evidence skips the Council entirely
# ============================================================

def test_zero_evidence_skips_the_council():

    calls = []

    class CountingClient:

        def __init__(self, host=None):
            pass

        def chat(self, **kwargs):

            calls.append(1)

            content = (
                "KẾT LUẬN: Redis nhanh hơn 10x. "
                "Độ tin cậy: CAO."
            )

            if kwargs.get("stream"):

                return iter(
                    [
                        {
                            "message": {
                                "content": content
                            }
                        }
                    ]
                )

            return {
                "message": {
                    "content": content
                }
            }

    for label, tool in (
        ("failed searches", FailingSearch()),
        ("zero-result searches", EmptySearch()),
    ):

        calls.clear()

        bcos = make_agent()

        bcos.llm.client = CountingClient()

        bcos.council.llm = bcos.llm

        bcos.tools[
            Action.SEARCH
        ] = tool

        answer, _ = ask(
            bcos,
            "Nên dùng Redis lock hay PostgreSQL lock?",
        )

        assert calls == [], (
            f"With {label} the Council must not run at all; "
            f"it made {len(calls)} LLM calls"
        )

        assert "Độ tin cậy: CAO" not in answer, (
            f"With {label} the agent must not return a "
            f"confident fabricated answer:\n{answer}"
        )

        assert "không thu được evidence" in answer.lower(), (
            f"With {label} the answer must name the retrieval "
            f"failure:\n{answer}"
        )


# ============================================================
# TEST 6 — FILE is reachable, and steals nothing
# ============================================================

def test_file_routing():

    should_route = [
        "đọc file data/example.txt",
        "mở data/example.txt",
        "xem nội dung data/notes.json",
        "read file example.txt",
        "cat data/example.txt",
        "phân tích data/log/app.log",
    ]

    for question in should_route:

        result = plan(question)

        assert result.action == Action.FILE, (
            f"Expected FILE for {question!r}, got "
            f"{result.action}"
        )

        assert result.parameters.get("path"), (
            f"FILE route must carry a path for {question!r}"
        )

    must_not_route = [
        "ai là tổng thống mỹ 2026",
        "SQLite có hỗ trợ SAVEPOINT không?",
        "tài liệu ở https://sqlite.org/lang_savepoint.html nói gì",
        "so sánh sqlite.org và postgresql.org",
        "Tính 125 * 8",
        "www.example.com có gì",
    ]

    for question in must_not_route:

        # These may legitimately reach the LLM fallback, so the
        # planner here is allowed to call it.
        result = Planner(
            _PermissiveLLM()
        ).plan(
            [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        )

        assert result.action != Action.FILE, (
            f"{question!r} must not be routed to FILE"
        )


class _PermissiveLLM:

    def chat(self, messages):
        return "{}"


# ============================================================
# TEST 7 — "bao nhiêu" no longer hijacks the calculator
# ============================================================

def test_calculator_routing():

    arithmetic = {
        "Tính 125 * 8": "125 * 8",
        "1 + 1 bằng bao nhiêu": "1 + 1",
        "2 + 3 * 4": "2 + 3 * 4",
        "kết quả của 25 * 4 là bao nhiêu": "25 * 4",
    }

    for question, expected in arithmetic.items():

        result = Planner(
            _PermissiveLLM()
        ).plan(
            [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        )

        assert result.action == Action.CALCULATOR, (
            f"Expected CALCULATOR for {question!r}, got "
            f"{result.action}"
        )

        assert (
            result.parameters.get("expression")
            == expected
        ), (
            f"Expected expression {expected!r} for "
            f"{question!r}, got "
            f"{result.parameters.get('expression')!r}"
        )

    not_arithmetic = [
        "dân số Việt Nam bao nhiêu",
        "GDP Nhật Bản bao nhiêu",
        "Hà Nội có bao nhiêu quận",
    ]

    for question in not_arithmetic:

        result = Planner(
            _PermissiveLLM()
        ).plan(
            [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        )

        assert result.action != Action.CALCULATOR, (
            f"{question!r} must not be routed to the "
            "calculator — the extracted 'expression' is "
            "Vietnamese text and the user was shown "
            "'Calculator error: invalid syntax'"
        )


# ============================================================
# TEST 8 — bitcoin price detection
# ============================================================

def test_bitcoin_price_detection():

    tool = SearchTool()

    is_price = [
        "giá bitcoin hôm nay",
        "giá btc hiện tại",
        "bitcoin to usd",
        "BTC/USD rate",
        "bitcoin price today",
        "tỷ giá bitcoin",
    ]

    not_price = [
        # "gia" as a syllable of an ordinary compound
        "cách giao dịch bitcoin an toàn",
        "làm sao tham gia mạng bitcoin",
        "bitcoin được chấp nhận ở những quốc gia nào",
        "gia đình tôi nên mua bitcoin không",
        "giá trị nội tại của bitcoin là gì",
        "đánh giá bitcoin có phải bong bóng không",
        "Bitcoin adoption in Georgia",
        # a time word alone is not a price question
        "current state of bitcoin regulation in the EU",
        "bitcoin hiện tại có bao nhiêu node",
        # the spot endpoint cannot answer these
        "giá bitcoin năm 2017",
        "btc price prediction 2030",
        "giá bitcoin theo EUR",
    ]

    for question in is_price:

        assert tool.is_bitcoin_price_query(question), (
            f"Expected a price query: {question!r}"
        )

    for question in not_price:

        assert not tool.is_bitcoin_price_query(question), (
            f"Must not be treated as a price query — the web "
            f"search would be skipped: {question!r}"
        )


# ============================================================
# TEST 9 — every tool payload shares one envelope
# ============================================================

def test_tool_envelope_is_consistent():

    tool = SearchTool()

    required = {
        "success",
        "source",
        "data_type",
        "query",
        "count",
        "results",
    }

    shapes = {
        "web success": tool.web_success(
            "q",
            [
                {
                    "title": "T",
                    "href": "https://u",
                    "body": "B",
                }
            ],
        ),
    }

    for name, payload in shapes.items():

        missing = required - set(payload)

        assert not missing, (
            f"{name} payload is missing {sorted(missing)}"
        )

    assert shapes["web success"]["count"] == 1, (
        "count must match the number of results"
    )

    assert (
        shapes["web success"]["results"][0]["url"]
        == "https://u"
    ), (
        "ddgs returns the link under 'href'"
    )


# ============================================================
# TEST 10 — a planner degradation is never silent
# ============================================================

def test_planner_fallback_is_not_silent():

    result = plan(
        "kể chuyện cười",
        llm=BoomLLM(),
    )

    assert result.action == Action.ANSWER, (
        "A planner failure should still degrade to ANSWER"
    )

    assert getattr(result, "error", None), (
        "The degradation must be recorded on the result, so "
        "the caller can tell it apart from a real "
        "classification"
    )

    assert "Ollama down" in result.error, (
        f"The cause must be preserved, got {result.error!r}"
    )


# ============================================================
# TEST 11 — logging actually writes
# ============================================================

def test_logging_writes_to_the_log_file():

    import log

    logger = log.get(
        "regression_probe"
    )

    marker = "ZZ_LOG_PROBE_7781"

    logger.warning(
        marker
    )

    for handler in logger.handlers + logging_handlers():

        try:
            handler.flush()
        except Exception:
            pass

    assert log.LOG_FILE.exists(), (
        f"{log.LOG_FILE} should exist after a log call"
    )

    contents = log.LOG_FILE.read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert marker in contents, (
        "Nothing in BCOS used to write a log, which is why a "
        "TypeError that broke every question surfaced only as "
        "'Qwen cannot search'"
    )


def logging_handlers():

    import logging

    return logging.getLogger(
        "bcos"
    ).handlers


# ============================================================
# TEST RUNNER
# ============================================================

def run_all_tests():

    tests = [
        test_failed_search_is_reported_as_a_tool_failure,
        test_structured_payloads_are_made_verifiable,
        test_file_content_reaches_the_verifier,
        test_judge_receives_evidence,
        test_zero_evidence_skips_the_council,
        test_file_routing,
        test_calculator_routing,
        test_bitcoin_price_detection,
        test_tool_envelope_is_consistent,
        test_planner_fallback_is_not_silent,
        test_logging_writes_to_the_log_file,
    ]

    print()
    print("=" * 60)
    print("BCOS Evidence Chain Regression Tests")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for test in tests:

        try:

            test()

            passed += 1

            print(
                f"PASS: {test.__name__}"
            )

        except Exception:

            failed += 1

            print(
                f"FAIL: {test.__name__}"
            )

            import traceback

            traceback.print_exc()

    print()
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)

    print(
        f"TOTAL : {len(tests)}"
    )

    print(
        f"PASS  : {passed}"
    )

    print(
        f"FAIL  : {failed}"
    )

    print("=" * 60)

    if failed:

        raise SystemExit(
            1
        )

    print(
        "ALL TESTS PASSED"
    )


if __name__ == "__main__":

    run_all_tests()
