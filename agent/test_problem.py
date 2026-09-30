from problem import ProblemInput, ProblemReconstructor, ProblemClassifier
from planner import Planner


tests = [
    {
        "input": "Tính 125 * 8",
        "expected_type": "calculation",
        "expected_action": "calculator",
    },
    {
        "input": "PostgreSQL có hỗ trợ row locking không?",
        "expected_type": "fact_lookup",
        "expected_action": "search",
    },
    {
        "input": "Nên dùng Redis lock hay PostgreSQL lock?",
        "expected_type": "decision",
        "expected_action": "complex",
    },
    {
        "input": "API bị deadlock khi concurrent writes",
        "expected_type": "debug",
        "expected_action": "complex",
    },
    {
        "input": "Thiết kế database warehouse",
        "expected_type": "design",
        "expected_action": "complex",
    },
    {
        "input": "Giải phương trình 2*x + 5 = 15",
        "expected_type": "mathematics",
        "expected_action": "complex",
    },
]


class FakeLLM:
    """
    Offline stand-in for the Ollama client.

    Every input below is expected to be routed deterministically
    by the problem model, so the LLM fallback must never be
    reached. It raises rather than returning "{}": Planner.parse
    turns "{}" into Action.ANSWER, a silent default that would let
    a future routing regression pass unnoticed for any case whose
    expectation happens to be "answer".
    """

    def chat(self, messages):
        raise AssertionError(
            "LLM planner fallback reached: routing is no "
            "longer deterministic for this input"
        )


reconstructor = ProblemReconstructor()
classifier = ProblemClassifier()
planner = Planner(FakeLLM())


passed = 0
failed = 0


for test in tests:

    text = test["input"]

    print("\n" + "=" * 70)
    print("INPUT:", text)

    # --------------------------------------------------
    # Reconstruct
    # --------------------------------------------------

    problem = reconstructor.reconstruct(
        ProblemInput(raw_text=text)
    )

    # --------------------------------------------------
    # Classify
    # --------------------------------------------------

    classifier.classify(problem)

    actual_type = (
        problem.primary_problem_type.value
    )

    # --------------------------------------------------
    # Planner
    # --------------------------------------------------

    result = planner.plan(
        [
            {
                "role": "user",
                "content": text,
            }
        ]
    )

    actual_action = (
        result.action.value
        if hasattr(result.action, "value")
        else str(result.action).lower()
    )

    expected_type = test["expected_type"]
    expected_action = test["expected_action"]

    type_ok = (
        actual_type == expected_type
    )

    action_ok = (
        actual_action == expected_action
    )

    print("TYPE:")
    print("  expected:", expected_type)
    print("  actual:  ", actual_type)
    print("  result:  ", "PASS" if type_ok else "FAIL")

    print("ACTION:")
    print("  expected:", expected_action)
    print("  actual:  ", actual_action)
    print("  result:  ", "PASS" if action_ok else "FAIL")

    if type_ok and action_ok:
        passed += 1
        print("\nSTATUS: PASS")
    else:
        failed += 1
        print("\nSTATUS: FAIL")


# ======================================================
# SUMMARY
# ======================================================

print("\n" + "=" * 70)
print("PLANNER TEST SUMMARY")
print("=" * 70)

print("PASSED:", passed)
print("FAILED:", failed)
print("TOTAL: ", len(tests))

if failed == 0:
    print("\nALL PLANNER TESTS PASSED")
else:
    print("\nSOME PLANNER TESTS FAILED")
    raise SystemExit(1)
