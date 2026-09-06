"""
Regression tests for BCOS EvidenceVerifier.

Run:

    python tests/test_evidence_verifier.py

These tests intentionally do NOT call Ollama.
A fake LLM is used so the test suite is:
    - deterministic
    - fast
    - offline
    - reproducible
"""

import sys
from pathlib import Path


# ============================================================
# Make project root importable when running:
#
#     python tests/test_evidence_verifier.py
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from agent.evidence_verifier import EvidenceVerifier


# ============================================================
# Fake LLM
# ============================================================

class FakeLLM:
    """
    EvidenceVerifier should rely on deterministic rules whenever
    possible.

    For fallback classification we deliberately return a neutral
    answer so the tests can verify that deterministic rules are
    working correctly.
    """

    def chat(self, messages):

        return """
        {
            "label": "IRRELEVANT",
            "reason": "Fake LLM fallback",
            "confidence": 0.5
        }
        """


# ============================================================
# Helpers
# ============================================================

def make_verifier():
    return EvidenceVerifier(
        FakeLLM()
    )


def make_evidence(
    results
):
    """
    Convert a simple list of result dictionaries into the
    evidence structure expected by EvidenceVerifier.
    """

    return [
        {
            "query": "test query",
            "result": {
                "success": True,
                "source": "test",
                "results": results,
            },
        }
    ]


def result(
    title,
    content,
    url="https://example.com"
):

    return {
        "title": title,
        "url": url,
        "content": content,
    }


# ============================================================
# Assertions
# ============================================================

def assert_status(
    verifier,
    question,
    evidence,
    expected,
    test_name
):

    verification = verifier.verify(
        question,
        evidence
    )

    actual = verification.get(
        "status"
    )

    assert actual == expected, (
        f"\n[{test_name}] FAILED\n"
        f"Expected: {expected}\n"
        f"Actual:   {actual}\n"
        f"Verification:\n"
        f"{verification}\n"
    )

    print(
        f"PASS: {test_name}"
    )

    return verification


# ============================================================
# TEST 1
# ============================================================

def test_us_president_2026():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "Tổng thống Mỹ Donald Trump",
                (
                    "Donald Trump là Tổng thống Hoa Kỳ "
                    "trong năm 2026. Ông nhậm chức ngày "
                    "20 tháng 1 năm 2025."
                )
            )
        ]
    )

    verification = assert_status(
        verifier,
        "ai là tổng thống mỹ 2026",
        evidence,
        verifier.SUPPORTED,
        "US president 2026"
    )

    supporting = verification.get(
        "supporting_evidence",
        []
    )

    assert supporting, (
        "Expected supporting evidence "
        "for US president 2026"
    )


# ============================================================
# TEST 2
# ============================================================

def test_sqlite_savepoint():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "SQLite SAVEPOINT",
                (
                    "The SAVEPOINT command starts a new "
                    "database transaction."
                ),
                url="https://sqlite.org/lang_savepoint.html"
            )
        ]
    )

    assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.SUPPORTED,
        "SQLite SAVEPOINT"
    )


# ============================================================
# TEST 3
# ============================================================

def test_postgresql_savepoint():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "PostgreSQL SAVEPOINT",
                (
                    "SAVEPOINT establishes a new savepoint "
                    "within the current transaction."
                ),
                url="https://www.postgresql.org/docs/current/sql-savepoint.html"
            )
        ]
    )

    assert_status(
        verifier,
        "PostgreSQL có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.SUPPORTED,
        "PostgreSQL SAVEPOINT"
    )


# ============================================================
# TEST 4
# ============================================================

def test_insufficient_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "Weather today",
                (
                    "The weather is sunny today."
                )
            )
        ]
    )

    assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.INSUFFICIENT,
        "Insufficient evidence"
    )


# ============================================================
# TEST 5
# ============================================================

def test_contradicted_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "SQLite SAVEPOINT",
                (
                    "SQLite does not support SAVEPOINT."
                )
            )
        ]
    )

    verification = assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.CONTRADICTED,
        "Contradicted evidence"
    )

    contradictions = verification.get(
        "contradicting_evidence",
        []
    )

    assert contradictions, (
        "Expected contradicting evidence"
    )


# ============================================================
# TEST 6
# ============================================================

def test_conflicting_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "SQLite official documentation",
                (
                    "The SAVEPOINT command starts a new "
                    "transaction."
                ),
                url="https://sqlite.org/lang_savepoint.html"
            ),
            result(
                "Incorrect source",
                (
                    "SQLite does not support SAVEPOINT."
                ),
                url="https://example.com/incorrect"
            )
        ]
    )

    verification = assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.CONFLICTED,
        "Conflicting evidence"
    )

    assert verification.get(
        "support_count",
        0
    ) > 0, (
        "Expected at least one supporting result"
    )

    assert verification.get(
        "contradiction_count",
        0
    ) > 0, (
        "Expected at least one contradicting result"
    )


# ============================================================
# TEST 7
# ============================================================

def test_wrong_entity():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "President of France",
                (
                    "Emmanuel Macron is the President "
                    "of France."
                )
            )
        ]
    )

    assert_status(
        verifier,
        "ai là tổng thống mỹ 2026",
        evidence,
        verifier.INSUFFICIENT,
        "Wrong entity"
    )


# ============================================================
# TEST 8
# ============================================================

def test_old_temporal_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "Donald Trump presidency 2017-2021",
                (
                    "Donald Trump served as the 45th "
                    "President of the United States "
                    "from January 20, 2017 to January 20, 2021."
                )
            )
        ]
    )

    assert_status(
        verifier,
        "ai là tổng thống mỹ 2026",
        evidence,
        verifier.INSUFFICIENT,
        "Old temporal evidence"
    )


# ============================================================
# TEST 9
# ============================================================

def test_biden_old_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "Joe Biden is President",
                (
                    "Joe Biden is the President of the "
                    "United States."
                )
            )
        ]
    )

    assert_status(
        verifier,
        "ai là tổng thống mỹ 2026",
        evidence,
        verifier.INSUFFICIENT,
        "Biden old evidence"
    )


# ============================================================
# TEST 10
# ============================================================

def test_president_current_2026():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "Donald Trump is the current President",
                (
                    "Donald Trump is the incumbent "
                    "President of the United States. "
                    "He took office on January 20, 2025. "
                    "This information is current in 2026."
                )
            )
        ]
    )

    verification = assert_status(
        verifier,
        "ai là tổng thống mỹ 2026",
        evidence,
        verifier.SUPPORTED,
        "Current president 2026"
    )

    # The verifier should extract the candidate.
    candidates = []

    for item in verification.get(
        "classifications",
        []
    ):

        if item.get(
            "label"
        ) != verifier.SUPPORTS:
            continue

        for name in item.get(
            "candidate_names",
            []
        ):

            if name not in candidates:
                candidates.append(
                    name
                )

    assert "Donald Trump" in candidates, (
        "Expected Donald Trump to be extracted "
        "as the supported candidate"
    )


# ============================================================
# TEST 11
# ============================================================

def test_entity_mismatch_sqlite_vs_postgresql():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "PostgreSQL SAVEPOINT",
                (
                    "PostgreSQL supports SAVEPOINT "
                    "inside transactions."
                )
            )
        ]
    )

    assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.INSUFFICIENT,
        "SQLite vs PostgreSQL entity mismatch"
    )


# ============================================================
# TEST 12
# ============================================================

def test_empty_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        []
    )

    assert_status(
        verifier,
        "ai là tổng thống mỹ 2026",
        evidence,
        verifier.INSUFFICIENT,
        "Empty evidence"
    )


# ============================================================
# TEST 13
# ============================================================

def test_unrelated_database_evidence():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "PostgreSQL performance",
                (
                    "PostgreSQL can process many concurrent "
                    "connections and provides transaction "
                    "isolation."
                )
            )
        ]
    )

    assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.INSUFFICIENT,
        "Related database but wrong claim"
    )


# ============================================================
# TEST 14
# ============================================================

def test_supported_savepoint_with_noise():

    verifier = make_verifier()

    evidence = make_evidence(
        [
            result(
                "SQLite WAL mode",
                (
                    "SQLite WAL allows readers and writers "
                    "to operate concurrently."
                )
            ),
            result(
                "SQLite SAVEPOINT documentation",
                (
                    "The SAVEPOINT command starts a new "
                    "transaction."
                ),
                url="https://sqlite.org/lang_savepoint.html"
            ),
            result(
                "SQLite unrelated documentation",
                (
                    "SQLite is a small embedded database."
                )
            )
        ]
    )

    verification = assert_status(
        verifier,
        "SQLite có hỗ trợ SAVEPOINT không?",
        evidence,
        verifier.SUPPORTED,
        "SAVEPOINT with noisy evidence"
    )

    assert verification.get(
        "support_count",
        0
    ) >= 1, (
        "Expected SAVEPOINT evidence to survive noise"
    )


# ============================================================
# TEST RUNNER
# ============================================================

def run_all_tests():

    tests = [
        test_us_president_2026,
        test_sqlite_savepoint,
        test_postgresql_savepoint,
        test_insufficient_evidence,
        test_contradicted_evidence,
        test_conflicting_evidence,
        test_wrong_entity,
        test_old_temporal_evidence,
        test_biden_old_evidence,
        test_president_current_2026,
        test_entity_mismatch_sqlite_vs_postgresql,
        test_empty_evidence,
        test_unrelated_database_evidence,
        test_supported_savepoint_with_noise,
    ]

    print()
    print("=" * 60)
    print("BCOS EvidenceVerifier Regression Tests")
    print("=" * 60)
    print()

    passed = 0
    failed = 0

    for test in tests:

        try:

            test()
            passed += 1

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