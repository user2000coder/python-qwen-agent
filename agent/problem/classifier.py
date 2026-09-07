from __future__ import annotations

import re
from typing import Dict, List

from .models import ProblemModel, ProblemType


class ProblemClassifier:
    """
    Classifies a reconstructed ProblemModel.

    Contract:
        ProblemModel -> ProblemModel

    The classifier:
    - scores multiple possible problem types;
    - preserves multiple applicable types;
    - selects one primary type;
    - stores scores and ranking in metadata.

    This classifier is deterministic.
    It does not use an LLM.
    """

    # ================================================================
    # Keyword groups
    # ================================================================

    DEBUG_KEYWORDS = (
        # English
        "deadlock",
        "deadlock detected",
        "timeout",
        "timed out",
        "exception",
        "traceback",
        "crash",
        "crashed",
        "error",
        "errors",
        "failed",
        "failure",
        "bug",
        "broken",
        "hang",
        "hung",
        "freeze",
        "frozen",
        "race condition",
        "concurrent writes",
        "concurrency issue",
        "not working",
        "does not work",
        "doesn't work",

        # Vietnamese
        "lỗi",
        "lỗi xảy ra",
        "bị lỗi",
        "gặp lỗi",
        "thất bại",
        "không hoạt động",
        "không chạy",
        "bị treo",
        "treo",
        "ngoại lệ",
        "xung đột",
        "đồng thời",
        "ghi đồng thời",
    )

    OPTIMIZATION_KEYWORDS = (
        "optimize",
        "optimization",
        "optimise",
        "performance",
        "faster",
        "slow",
        "latency",
        "throughput",
        "minimize",
        "maximize",
        "reduce cost",
        "increase performance",
        "tối ưu",
        "tối ưu hóa",
        "hiệu năng",
        "tốc độ",
        "độ trễ",
        "giảm chi phí",
        "tăng hiệu năng",
    )

    DECISION_KEYWORDS = (
        "should i",
        "should we",
        "which should",
        "which one",
        "choose",
        "choice",
        "decision",
        "decide",
        "better option",
        "best option",
        "trade-off",
        "tradeoff",
        "compare",
        "versus",
        "vs",
        "nên dùng",
        "nên chọn",
        "chọn",
        "lựa chọn",
        "quyết định",
        "phương án",
        "cái nào tốt hơn",
        "cái nào phù hợp",
        "so với",
        "hay",
    )

    CAUSAL_KEYWORDS = (
        "why",
        "why does",
        "why did",
        "cause",
        "caused by",
        "root cause",
        "because",
        "reason",
        "explain why",
        "nguyên nhân",
        "tại sao",
        "vì sao",
        "do đâu",
        "lý do",
        "nguyên nhân gốc",
        "vì sao xảy ra",
    )

    DESIGN_KEYWORDS = (
        "design",
        "architecture",
        "architect",
        "schema",
        "database design",
        "system design",
        "api design",
        "design a",
        "build a system",
        "thiết kế",
        "kiến trúc",
        "thiết kế hệ thống",
        "thiết kế database",
        "thiết kế cơ sở dữ liệu",
        "thiết kế api",
        "xây dựng hệ thống",
        "mô hình hóa",
    )

    MATHEMATICS_KEYWORDS = (
        "equation",
        "equations",
        "solve equation",
        "solve for",
        "unknown variable",
        "algebra",
        "integral",
        "derivative",
        "differentiate",
        "differential equation",
        "matrix",
        "linear algebra",
        "polynomial",
        "quadratic",
        "calculate x",
        "phương trình",
        "giải phương trình",
        "ẩn số",
        "đại số",
        "tích phân",
        "đạo hàm",
        "phương trình vi phân",
        "ma trận",
        "đa thức",
        "bậc hai",
    )

    CALCULATION_KEYWORDS = (
        "calculate",
        "calculation",
        "compute",
        "what is",
        "how much",
        "sum",
        "subtract",
        "multiply",
        "divide",
        "tính",
        "tính toán",
        "bao nhiêu",
        "cộng",
        "trừ",
        "nhân",
        "chia",
    )

    FACT_LOOKUP_KEYWORDS = (
        "what is",
        "what are",
        "is it true",
        "does",
        "do",
        "can",
        "support",
        "supported",
        "when",
        "where",
        "who",
        "which",
        "how does",
        "có hỗ trợ",
        "có phải",
        "là gì",
        "như thế nào",
        "khi nào",
        "ở đâu",
        "ai",
        "hỗ trợ",
    )

    # ================================================================
    # Primary precedence
    # ================================================================

    PRIMARY_PRECEDENCE = (
        ProblemType.DEBUG,
        ProblemType.OPTIMIZATION,
        ProblemType.DECISION,
        ProblemType.CAUSAL,
        ProblemType.DESIGN,
        ProblemType.MATHEMATICS,
        ProblemType.CALCULATION,
        ProblemType.FACT_LOOKUP,
        ProblemType.UNKNOWN,
    )

    MIN_SCORE = 1

    # ================================================================
    # Public API
    # ================================================================

    def classify(self, problem: ProblemModel) -> ProblemModel:
        """
        Classify a ProblemModel.

        Returns the SAME ProblemModel object after mutation.

        Contract:

            ProblemModel -> ProblemModel
        """

        if not isinstance(problem, ProblemModel):
            raise TypeError(
                "classify() expects a ProblemModel, "
                f"got {type(problem).__name__}"
            )

        scores = self.score(problem)

        ranked_types = self._rank_types(scores)

        if not ranked_types:
            ranked_types = [ProblemType.UNKNOWN]

        primary_type = self._select_primary_type(
            scores=scores,
            ranked_types=ranked_types,
        )

        problem.problem_types = ranked_types
        problem.primary_problem_type = primary_type

        # Store diagnostic information.
        problem.metadata["classification_version"] = "1.2"

        problem.metadata["classification_scores"] = {
            problem_type.value: score
            for problem_type, score in scores.items()
        }

        problem.metadata["classification_primary"] = (
            primary_type.value
        )

        problem.metadata["classification_ranking"] = [
            problem_type.value
            for problem_type in ranked_types
        ]

        return problem

    # ================================================================
    # Scoring
    # ================================================================

    def score(
        self,
        problem: ProblemModel,
    ) -> Dict[ProblemType, int]:
        """
        Calculate scores for every ProblemType.
        """

        text = self._normalized_text(problem)

        scores: Dict[ProblemType, int] = {
            problem_type: 0
            for problem_type in ProblemType
        }

        # ------------------------------------------------------------
        # DEBUG
        # ------------------------------------------------------------

        debug_hits = self._count_keyword_hits(
            text,
            self.DEBUG_KEYWORDS,
        )

        if debug_hits:
            scores[ProblemType.DEBUG] += debug_hits * 5

        # Strong structural signals.
        if problem.metadata.get("failure_detected"):
            scores[ProblemType.DEBUG] += 8

        if problem.metadata.get("has_error"):
            scores[ProblemType.DEBUG] += 8

        # Concurrency-specific failure signals.
        if self._contains_any(
            text,
            (
                "deadlock",
                "race condition",
                "concurrent",
                "concurrency",
                "đồng thời",
                "xung đột",
                "ghi đồng thời",
            ),
        ):
            scores[ProblemType.DEBUG] += 5

        # ------------------------------------------------------------
        # OPTIMIZATION
        # ------------------------------------------------------------

        optimization_hits = self._count_keyword_hits(
            text,
            self.OPTIMIZATION_KEYWORDS,
        )

        scores[ProblemType.OPTIMIZATION] += (
            optimization_hits * 3
        )

        # ------------------------------------------------------------
        # DECISION
        # ------------------------------------------------------------

        decision_hits = self._count_keyword_hits(
            text,
            self.DECISION_KEYWORDS,
        )

        scores[ProblemType.DECISION] += (
            decision_hits * 3
        )

        if self._has_multiple_alternatives(text):
            scores[ProblemType.DECISION] += 5

        # ------------------------------------------------------------
        # CAUSAL
        # ------------------------------------------------------------

        causal_hits = self._count_keyword_hits(
            text,
            self.CAUSAL_KEYWORDS,
        )

        scores[ProblemType.CAUSAL] += (
            causal_hits * 3
        )

        # ------------------------------------------------------------
        # DESIGN
        # ------------------------------------------------------------

        design_hits = self._count_keyword_hits(
            text,
            self.DESIGN_KEYWORDS,
        )

        scores[ProblemType.DESIGN] += (
            design_hits * 3
        )

        # IMPORTANT:
        #
        # Do NOT add DESIGN merely because an entity such as API,
        # database, PostgreSQL, etc. exists.
        #
        # Entity != problem type.
        #
        # Example:
        #
        #   "API bị deadlock khi concurrent writes"
        #
        # is DEBUG, not DESIGN.

        # ------------------------------------------------------------
        # MATHEMATICS
        # ------------------------------------------------------------

        mathematics_hits = self._count_keyword_hits(
            text,
            self.MATHEMATICS_KEYWORDS,
        )

        scores[ProblemType.MATHEMATICS] += (
            mathematics_hits * 4
        )

        equation_count = self._count_equations(problem)

        if equation_count:
            scores[ProblemType.MATHEMATICS] += 8

        if problem.unknowns and equation_count:
            scores[ProblemType.MATHEMATICS] += 5

        # ------------------------------------------------------------
        # CALCULATION
        # ------------------------------------------------------------

        calculation_hits = self._count_keyword_hits(
            text,
            self.CALCULATION_KEYWORDS,
        )

        scores[ProblemType.CALCULATION] += (
            calculation_hits * 2
        )

        if self._has_arithmetic_expression(problem):
            scores[ProblemType.CALCULATION] += 5

        # ------------------------------------------------------------
        # FACT LOOKUP
        # ------------------------------------------------------------

        fact_hits = self._count_keyword_hits(
            text,
            self.FACT_LOOKUP_KEYWORDS,
        )

        scores[ProblemType.FACT_LOOKUP] += (
            fact_hits * 2
        )

        if "?" in text:
            scores[ProblemType.FACT_LOOKUP] += 1

        # ------------------------------------------------------------
        # UNKNOWN
        # ------------------------------------------------------------

        non_unknown_scores = [
            score
            for problem_type, score in scores.items()
            if problem_type != ProblemType.UNKNOWN
        ]

        if not non_unknown_scores or max(non_unknown_scores) <= 0:
            scores[ProblemType.UNKNOWN] = 1

        return scores

    # ================================================================
    # Ranking
    # ================================================================

    def _rank_types(
        self,
        scores: Dict[ProblemType, int],
    ) -> List[ProblemType]:
        """
        Rank applicable problem types.

        Sort:
            1. score descending
            2. primary precedence
        """

        applicable = [
            problem_type
            for problem_type, score in scores.items()
            if (
                problem_type != ProblemType.UNKNOWN
                and score >= self.MIN_SCORE
            )
        ]

        precedence_index = {
            problem_type: index
            for index, problem_type in enumerate(
                self.PRIMARY_PRECEDENCE
            )
        }

        applicable.sort(
            key=lambda problem_type: (
                -scores[problem_type],
                precedence_index.get(
                    problem_type,
                    len(self.PRIMARY_PRECEDENCE),
                ),
            )
        )

        if not applicable:
            return [ProblemType.UNKNOWN]

        return applicable

    # ================================================================
    # Primary selection
    # ================================================================

    def _select_primary_type(
        self,
        scores: Dict[ProblemType, int],
        ranked_types: List[ProblemType],
    ) -> ProblemType:

        if not ranked_types:
            return ProblemType.UNKNOWN

        best_score = max(
            scores.get(problem_type, 0)
            for problem_type in ranked_types
        )

        candidates = [
            problem_type
            for problem_type in ranked_types
            if scores.get(problem_type, 0) == best_score
        ]

        # Deterministic tie-breaking.
        for preferred_type in self.PRIMARY_PRECEDENCE:
            if preferred_type in candidates:
                return preferred_type

        return candidates[0]

    # ================================================================
    # Text helpers
    # ================================================================

    def _normalized_text(
        self,
        problem: ProblemModel,
    ) -> str:

        raw_text = problem.input.raw_text or ""

        return re.sub(
            r"\s+",
            " ",
            raw_text.strip().lower(),
        )

    def _count_keyword_hits(
        self,
        text: str,
        keywords,
    ) -> int:

        count = 0

        for keyword in keywords:
            keyword = keyword.lower().strip()

            if not keyword:
                continue

            # Multi-word phrases.
            if " " in keyword:
                if keyword in text:
                    count += 1
                continue

            pattern = (
                rf"(?<![\w])"
                rf"{re.escape(keyword)}"
                rf"(?![\w])"
            )

            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            ):
                count += 1

        return count

    # ================================================================
    # Structural helpers
    # ================================================================

    def _count_equations(
        self,
        problem: ProblemModel,
    ) -> int:

        count = 0

        for relation in problem.relations:
            expression = relation.expression

            if not expression:
                continue

            if "=" in expression:
                count += 1

        equations = problem.metadata.get("equations")

        if isinstance(equations, list):
            count = max(
                count,
                len(equations),
            )

        return count

    def _has_arithmetic_expression(
        self,
        problem: ProblemModel,
    ) -> bool:

        for relation in problem.relations:
            expression = relation.expression

            if not expression:
                continue

            if re.search(
                r"\d\s*[\+\-\*/]\s*\d",
                expression,
            ):
                return True

        calculation_expression = (
            problem.metadata.get(
                "calculation_expression"
            )
        )

        if isinstance(
            calculation_expression,
            str,
        ):
            if re.search(
                r"\d\s*[\+\-\*/]\s*\d",
                calculation_expression,
            ):
                return True

        return False

    def _has_multiple_alternatives(
        self,
        text: str,
    ) -> bool:

        patterns = (
            r"\bvs\.?\b",
            r"\bversus\b",
            r"\b(?:hay|hoặc|or)\b",
        )

        return any(
            re.search(
                pattern,
                text,
                flags=re.IGNORECASE,
            )
            for pattern in patterns
        )

    def _contains_any(
        self,
        text: str,
        keywords: tuple[str, ...],
    ) -> bool:

        return any(
            keyword.lower() in text
            for keyword in keywords
        )