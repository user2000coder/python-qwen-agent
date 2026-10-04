"""
Regression tests for the BCOS defects fixed on this branch.

Run:

    python tests/test_regressions.py

Offline by design: no Ollama, no network, no filesystem outside
the repository.
"""

import os
import sys
from pathlib import Path


# ============================================================
# BCOS modules import each other flat ("from llm import LLM"),
# so agent/ has to be on sys.path.
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

AGENT_DIR = ROOT / "agent"

for entry in (str(ROOT), str(AGENT_DIR)):

    if entry not in sys.path:
        sys.path.insert(0, entry)


# The fake Ollama client is installed at MODULE scope. It used to be
# installed inside one test that a later test then depended on, so
# running that later test alone (pytest -k, a shuffle) raised
# ModuleNotFoundError.

import types as _types

if "ollama" not in sys.modules:

    _fake_ollama = _types.ModuleType("ollama")

    class _FakeOllamaClient:

        def __init__(self, host=None):
            pass

        def chat(self, **kwargs):

            content = ""

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

    _fake_ollama.Client = _FakeOllamaClient

    sys.modules["ollama"] = _fake_ollama


import paths
from memory import Memory
from planner import Planner
from problem import (
    ProblemClassifier,
    ProblemInput,
    ProblemReconstructor,
    ProblemType,
)
from protocol import Action
from tools.file import FileTool


# ============================================================
# Fake LLM
# ============================================================

class FakeLLM:
    """
    Every case below must be routed deterministically, so the
    LLM planner fallback is never expected to run.
    """

    def chat(self, messages):
        raise AssertionError(
            "LLM fallback reached: routing is no longer "
            "deterministic for this input"
        )


# ============================================================
# TEST 1
#
# Planner.plan() called reconstruct(question, source_type="text")
# while reconstruct() accepted no such argument, so every single
# question raised TypeError before reaching any tool.
# ============================================================

def test_reconstruct_accepts_source_type():

    reconstructor = ProblemReconstructor()

    problem = reconstructor.reconstruct(
        "SQLite có hỗ trợ SAVEPOINT không?",
        source_type="text",
    )

    assert problem.input.source_type == "text", (
        "source_type should reach ProblemInput"
    )

    # An explicit source_type must override the one already
    # carried by a ProblemInput.
    problem = reconstructor.reconstruct(
        ProblemInput(
            raw_text="API bị deadlock",
            source_type="text",
        ),
        source_type="technical",
    )

    assert problem.input.source_type == "technical", (
        "explicit source_type should override ProblemInput"
    )

    # Omitting it must keep whatever the caller already set.
    problem = reconstructor.reconstruct(
        ProblemInput(
            raw_text="API bị deadlock",
            source_type="external",
        )
    )

    assert problem.input.source_type == "external", (
        "omitted source_type should be left untouched"
    )


# ============================================================
# TEST 2
#
# The whole pipeline used to die on the first question.
# ============================================================

def test_planner_does_not_crash():

    planner = Planner(FakeLLM())

    questions = [
        "Tính 125 * 8",
        "PostgreSQL có hỗ trợ row locking không?",
        "Nên dùng Redis lock hay PostgreSQL lock?",
        "API bị deadlock khi concurrent writes",
        "Thiết kế database warehouse",
        "Giải phương trình 2*x + 5 = 15",
    ]

    for question in questions:

        result = planner.plan(
            [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        )

        assert result.action is not None, (
            f"No action planned for: {question}"
        )


# ============================================================
# TEST 3
#
# A fact_lookup question whose text happens to contain a
# "complex" keyword (locking, transaction, concurrency, ...)
# was hijacked by the deterministic keyword fallback and
# answered from model memory instead of being searched.
# ============================================================

def test_fact_lookup_with_complex_keyword_routes_to_search():

    planner = Planner(FakeLLM())

    reconstructor = ProblemReconstructor()

    classifier = ProblemClassifier()

    # A capability lookup ("does X support Y") is answerable from
    # one authoritative page. is_complex_reasoning() used to return
    # True for any question combining a database keyword with a
    # "có hỗ trợ" form, so these went to the Council and were
    # answered from model memory instead of being searched.
    #
    # The variant without a question mark matters: evidence
    # requirements are only populated when the text contains a
    # literal "?", so gating on them left the same question
    # broken when typed without punctuation.

    must_search = [
        "PostgreSQL có hỗ trợ row locking không?",
        "PostgreSQL có hỗ trợ row locking không",
        "SQLite có hỗ trợ SAVEPOINT trong transaction không?",
        "SQLite có hỗ trợ SAVEPOINT không",
    ]

    for question in must_search:

        problem = classifier.classify(
            reconstructor.reconstruct(question)
        )

        assert (
            problem.primary_problem_type
            == ProblemType.FACT_LOOKUP
        ), (
            f"Expected fact_lookup for: {question}"
        )

        result = planner.plan(
            [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        )

        assert result.action == Action.SEARCH, (
            f"\nExpected SEARCH for a capability lookup\n"
            f"Question: {question}\n"
            f"Actual:   {result.action}\n"
        )

    # The other half of the contract. Hoisting the FACT_LOOKUP
    # branch above is_complex_reasoning() made all of these route
    # to a single web search — the classifier types them
    # fact_lookup too, so the problem type alone cannot tell a
    # comparison from a capability lookup.

    must_stay_complex = [
        "So sánh PostgreSQL và MySQL về transaction isolation?",
        "Ưu nhược điểm của microservice là gì?",
        "Rủi ro khi dùng row locking trong warehouse là gì?",
        "Kế hoạch migrate database sang PostgreSQL như thế nào?",
        "Hệ thống của tôi nên scale như thế nào?",
        "Redis có nhanh hơn PostgreSQL không?",
        "Benchmark nào cho thấy PostgreSQL nhanh hơn?",
    ]

    for question in must_stay_complex:

        result = planner.plan(
            [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        )

        assert result.action == Action.COMPLEX, (
            f"\nA reasoning question must keep the Council\n"
            f"Question: {question}\n"
            f"Actual:   {result.action}\n"
        )


# ============================================================
# TEST 3b
#
# Runtime paths were resolved against the working directory, so
# launching from the project root silently replaced the BCOS
# system prompt with a four-line stub. Asserting properties of
# paths.py is not enough: reverting llm.py alone left the suite
# green.
# ============================================================

def test_system_prompt_loads_from_any_cwd():

    from llm import LLM

    stub_marker = "Ưu tiên Evidence."

    original_cwd = os.getcwd()

    try:

        for cwd in (str(ROOT), str(AGENT_DIR), os.sep):

            os.chdir(cwd)

            prompt = LLM().load_prompt()

            assert len(prompt) > 500, (
                f"From cwd={cwd} the prompt is {len(prompt)} "
                "characters — that is the built-in stub, not "
                "agent/prompts/bcos.txt"
            )

            assert "BCOS" in prompt, (
                f"From cwd={cwd} the loaded prompt does not "
                "mention BCOS"
            )

            assert prompt.strip() != stub_marker, (
                f"From cwd={cwd} the stub fallback was used"
            )

    finally:

        os.chdir(original_cwd)


# ============================================================
# TEST 4
#
# FileTool.validate_path() compared paths with startswith(),
# so a sibling directory sharing the "data" prefix escaped the
# sandbox.
# ============================================================

def test_file_tool_rejects_prefix_sibling_escape():

    import tempfile
    import shutil

    tool = FileTool()

    # Build the whole fixture in a temp directory: creating
    # agent/data_secret/ inside the repository left an untracked
    # directory behind whenever cleanup did not run, and
    # .gitignore only covers agent/data/.

    workspace = Path(
        tempfile.mkdtemp(
            prefix="bcos-sandbox-"
        )
    )

    base = workspace / "data"

    base.mkdir()

    tool.ALLOWED_DIR = base

    sibling = Path(
        str(base) + "_secret"
    )

    sibling.mkdir()

    secret = sibling / "key.txt"

    secret.write_text(
        "LEAK",
        encoding="utf-8",
    )

    try:

        escapes = [
            str(secret),
            os.path.join(
                "..",
                sibling.name,
                "key.txt",
            ),
            os.path.join(
                "data",
                "..",
                sibling.name,
                "key.txt",
            ),
            "/etc/passwd",
        ]

        for candidate in escapes:

            result = tool.run(candidate)

            assert not result.get("success"), (
                f"Sandbox escape allowed: {candidate}"
            )

            assert "LEAK" not in str(result), (
                f"Sandbox leaked file content: {candidate}"
            )

    finally:

        shutil.rmtree(
            workspace,
            ignore_errors=True,
        )


# ============================================================
# TEST 5
#
# FileTool must still read the documented "data/example.txt"
# form, from any working directory.
# ============================================================

def test_file_tool_reads_allowed_file():

    tool = FileTool()

    base = Path(
        os.path.realpath(
            tool.ALLOWED_DIR
        )
    )

    base.mkdir(
        parents=True,
        exist_ok=True,
    )

    sample = base / "__regression_sample.txt"

    sample.write_text(
        "hello bcos",
        encoding="utf-8",
    )

    original_cwd = os.getcwd()

    try:

        for cwd in (str(ROOT), str(AGENT_DIR), os.sep):

            os.chdir(cwd)

            for candidate in (
                f"data/{sample.name}",
                sample.name,
            ):

                result = tool.run(candidate)

                assert result.get("success"), (
                    f"Failed to read {candidate} "
                    f"from cwd={cwd}: {result.get('error')}"
                )

                assert "hello bcos" in str(
                    result.get("content", "")
                ), (
                    f"Wrong content for {candidate} "
                    f"from cwd={cwd}"
                )

    finally:

        os.chdir(original_cwd)

        sample.unlink(
            missing_ok=True
        )


# ============================================================
# TEST 6
#
# Runtime paths were resolved against the working directory, so
# launching from the project root silently replaced the BCOS
# system prompt with a stub and wrote history to a second file.
# ============================================================

def test_runtime_paths_are_cwd_independent():

    original_cwd = os.getcwd()

    expected = {
        "prompts": paths.PROMPTS_DIR,
        "history": paths.HISTORY_DIR,
        "memory": Memory.FILE,
        "data": FileTool.ALLOWED_DIR,
    }

    try:

        for cwd in (str(ROOT), str(AGENT_DIR), os.sep):

            os.chdir(cwd)

            for name, value in expected.items():

                assert Path(value).is_absolute(), (
                    f"{name} path is not absolute: {value}"
                )

                assert str(value).startswith(
                    str(AGENT_DIR)
                ), (
                    f"{name} path escapes the source tree "
                    f"from cwd={cwd}: {value}"
                )

        assert (
            paths.PROMPTS_DIR / "bcos.txt"
        ).exists(), (
            "BCOS system prompt file is missing"
        )

    finally:

        os.chdir(original_cwd)


# ============================================================
# TEST 7
#
# Polar ("yes/no") questions used to end in a non-answer even
# when the verifier had already concluded SUPPORTED.
# ============================================================

def test_polar_question_detection():

    from agent import Agent

    bcos = Agent()

    bcos.trace_enabled = False

    polar = [
        "SQLite có hỗ trợ SAVEPOINT không?",
        "PostgreSQL có hỗ trợ row locking không?",
        "Có phải SQLite hỗ trợ SAVEPOINT?",
        "Does SQLite support SAVEPOINT?",
        "Is Redis faster than PostgreSQL?",
        # no question mark
        "PostgreSQL có hỗ trợ row locking không",
        # written without diacritics
        "sqlite co ho tro savepoint khong?",
        "ban da lam xong chua?",
        # yogurt, but genuinely a yes/no question about it
        "sua chua co ngon khong",
    ]

    # Every entry below was misclassified as polar by the first
    # version of this detector, which matched the particle as a
    # SUFFIX. Asserting "Có" for these is worse than a vague
    # answer, so they are the real contract of this function.
    #
    # Several of them contain "?", so a detector reduced to
    # `"?" in question` fails here — the previous list was
    # satisfied by exactly that.

    not_polar = [
        "ai là tổng thống mỹ 2026",
        "Thiết kế database warehouse",
        "Tính 125 * 8",
        "",
        # "chua" = sour, not "chưa" = yet
        "Thành phần của sữa chua?",
        "Tại sao sữa bị chua?",
        "Giá canh chua bao nhiêu?",
        # "không" = zero / aviation, not the polar particle
        "Doanh thu ngành hàng không?",
        "Tồn kho hiện tại bằng không.",
        "Áp suất chân không là gì?",
        # diacritic-less Vietnamese colliding with English
        # auxiliaries: can -> Can Tho, do -> Do dau
        "Can Tho co bao nhieu dan?",
        "Do dau ma lam phat tang?",
        "Will Smith sinh nam nao?",
        "Độ ẩm hôm nay thế nào?",
        # English requests and non-questions
        "Can you list the steps to configure row locking?",
        "Do not use row locking here",
        "Have a look at the deadlock trace",
    ]

    for question in polar:

        assert bcos.is_polar_question(question), (
            f"Expected polar: {question!r}"
        )

    for question in not_polar:

        assert not bcos.is_polar_question(question), (
            f"Expected non-polar: {question!r}"
        )


# ============================================================
# TEST 8
#
# SUPPORTED evidence must produce a grounded answer, not
# "chưa trích xuất được thực thể".
# ============================================================

def test_supported_answer_is_grounded():

    from agent import Agent

    bcos = Agent()

    bcos.trace_enabled = False

    verification = {
        "status": bcos.evidence_verifier.SUPPORTED,
        "classifications": [
            {
                "label": bcos.evidence_verifier.SUPPORTS,
                "reason": "Evidence describes SAVEPOINT.",
                "title": "SQLite SAVEPOINT",
                "url": (
                    "https://sqlite.org/"
                    "lang_savepoint.html"
                ),
                "candidate_names": [],
            }
        ],
    }

    answer = bcos._answer_supported(
        "SQLite có hỗ trợ SAVEPOINT không?",
        verification,
    )

    assert "chưa trích" not in answer, (
        "SUPPORTED evidence still produces a non-answer:\n"
        f"{answer}"
    )

    assert answer.startswith("Có"), (
        "Polar question with SUPPORTED evidence should be "
        f"answered affirmatively, got:\n{answer}"
    )

    assert "sqlite.org" in answer, (
        f"Answer should cite its source, got:\n{answer}"
    )


# ============================================================
# TEST 12
#
# The REPL caught EOFError in its generic handler and looped
# forever when stdin was closed (a pipe, a non-interactive run).
# ============================================================

def test_cli_exits_on_eof():

    import subprocess

    completed = subprocess.run(
        [
            sys.executable,
            str(AGENT_DIR / "main.py"),
        ],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert completed.returncode == 0, (
        "The CLI must exit cleanly on EOF, got "
        f"returncode={completed.returncode}\n"
        f"stderr:\n{completed.stderr[-2000:]}"
    )

    assert "Hết input" in completed.stdout, (
        "The CLI should say why it stopped:\n"
        f"{completed.stdout[-2000:]}"
    )


# ============================================================
# TEST RUNNER
# ============================================================

def run_all_tests():

    tests = [
        test_reconstruct_accepts_source_type,
        test_planner_does_not_crash,
        test_fact_lookup_with_complex_keyword_routes_to_search,
        test_system_prompt_loads_from_any_cwd,
        test_file_tool_rejects_prefix_sibling_escape,
        test_file_tool_reads_allowed_file,
        test_runtime_paths_are_cwd_independent,
        test_polar_question_detection,
        test_supported_answer_is_grounded,
        test_cli_exits_on_eof,
    ]

    print()
    print("=" * 60)
    print("BCOS Regression Tests")
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

        except Exception as exc:

            failed += 1

            print(
                f"FAIL: {test.__name__}"
            )

            print(
                str(exc)
            )

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
