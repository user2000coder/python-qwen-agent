from __future__ import annotations

import re
from typing import Any

from .models import (
    Assumption,
    Constraint,
    EvidenceRequirement,
    ProblemInput,
    ProblemModel,
    Relation,
    SuccessCriterion,
    Unknown,
    Variable,
)


class ProblemReconstructor:
    """
    Reconstruct raw user input into a structured ProblemModel.

    Pipeline:

        RAW INPUT
            ↓
        NORMALIZE
            ↓
        EXTRACT
            ↓
        ProblemModel

    This component does NOT decide the final problem type.
    ProblemClassifier is responsible for classification.

    Design principle:

        Reconstruction ≠ Classification
        Observation ≠ Conclusion
        Unknown ≠ Entity
    """

    VERSION = "1.3"

    def reconstruct(
        self,
        text_or_input: str | ProblemInput,
    ) -> ProblemModel:

        problem_input = self._normalize_input(
            text_or_input
        )

        raw_text = problem_input.raw_text.strip()

        if not raw_text:
            raise ValueError(
                "Problem input cannot be empty"
            )

        normalized_text = self._normalize_text(
            raw_text
        )

        problem_input.normalized_text = normalized_text

        problem = ProblemModel(
            input=problem_input,
        )

        problem.metadata[
            "reconstruction_version"
        ] = self.VERSION

        problem.metadata[
            "reconstruction_mode"
        ] = "deterministic"

        # --------------------------------------------------
        # GOAL
        # --------------------------------------------------

        problem.goal = self._extract_goal(
            raw_text
        )

        # --------------------------------------------------
        # NUMBERS
        # --------------------------------------------------

        numbers = self._extract_numbers(
            raw_text
        )

        for index, number in enumerate(
            numbers,
            start=1,
        ):
            problem.add_variable(
                Variable(
                    name=f"number_{index}",
                    value=number,
                    description=(
                        "Numeric value extracted "
                        "from user input"
                    ),
                    source="input",
                )
            )

        # --------------------------------------------------
        # EQUATIONS
        # --------------------------------------------------

        equations = self._extract_equations(
            raw_text
        )

        problem.metadata[
            "equations"
        ] = equations

        for equation in equations:
            problem.add_relation(
                Relation(
                    name="equation",
                    expression=equation,
                    description=(
                        "Equation extracted "
                        "from user input"
                    ),
                    source="input",
                )
            )

        # --------------------------------------------------
        # CALCULATION EXPRESSION
        # --------------------------------------------------

        calculation_expression = (
            self._extract_calculation_expression(
                raw_text
            )
        )

        if calculation_expression:

            problem.metadata[
                "calculation_expression"
            ] = calculation_expression

            if calculation_expression not in equations:
                problem.add_relation(
                    Relation(
                        name="calculation",
                        expression=calculation_expression,
                        description=(
                            "Arithmetic expression "
                            "extracted from input"
                        ),
                        source="input",
                    )
                )

        # --------------------------------------------------
        # UNKNOWNS
        # --------------------------------------------------

        unknowns = self._extract_unknowns(
            raw_text=raw_text,
            equations=equations,
        )

        for unknown in unknowns:
            problem.add_unknown(
                unknown
            )

        # --------------------------------------------------
        # CONSTRAINTS
        # --------------------------------------------------

        constraints = self._extract_constraints(
            raw_text
        )

        for constraint in constraints:
            problem.add_constraint(
                constraint
            )

        # --------------------------------------------------
        # ENTITIES
        # --------------------------------------------------

        entities = self._extract_entities(
            raw_text
        )

        for entity in entities:
            problem.add_entity(
                entity
            )

        # --------------------------------------------------
        # EVIDENCE REQUIREMENTS
        # --------------------------------------------------

        evidence_requirements = (
            self._extract_evidence_requirements(
                raw_text
            )
        )

        for requirement in evidence_requirements:
            problem.add_evidence_requirement(
                requirement
            )

        # --------------------------------------------------
        # SUCCESS CRITERIA
        # --------------------------------------------------

        success_criteria = (
            self._extract_success_criteria(
                raw_text
            )
        )

        for criterion in success_criteria:
            problem.add_success_criterion(
                criterion
            )

        # --------------------------------------------------
        # OBSERVATIONS
        # --------------------------------------------------

        observations = (
            self._extract_observations(
                raw_text
            )
        )

        problem.observations.extend(
            observations
        )

        # --------------------------------------------------
        # ASSUMPTIONS
        # --------------------------------------------------

        assumptions = (
            self._extract_assumptions(
                raw_text
            )
        )

        for assumption in assumptions:
            problem.add_assumption(
                assumption
            )

        # --------------------------------------------------
        # METADATA
        # --------------------------------------------------

        self._populate_metadata(
            problem
        )

        return problem

    # ======================================================
    # INPUT
    # ======================================================

    def _normalize_input(
        self,
        text_or_input: str | ProblemInput,
    ) -> ProblemInput:

        if isinstance(
            text_or_input,
            ProblemInput,
        ):
            if not isinstance(
                text_or_input.raw_text,
                str,
            ):
                raise TypeError(
                    "ProblemInput.raw_text must be a string"
                )

            return text_or_input

        if isinstance(
            text_or_input,
            str,
        ):
            return ProblemInput(
                raw_text=text_or_input,
                source_type="text",
            )

        raise TypeError(
            "reconstruct() expects either str or "
            f"ProblemInput, got "
            f"{type(text_or_input).__name__}"
        )

    def _normalize_text(
        self,
        text: str,
    ) -> str:

        text = text.strip()

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return text

    # ======================================================
    # GOAL
    # ======================================================

    def _extract_goal(
        self,
        text: str,
    ) -> str:

        clean = text.strip()

        patterns = (
            r"^(tính.+)$",
            r"^(giải.+)$",
            r"^(thiết kế.+)$",
            r"^(xây dựng.+)$",
            r"^(phân tích.+)$",
            r"^(so sánh.+)$",
            r"^(nên.+)$",
            r"^(why.+)$",
            r"^(how.+)$",
            r"^(what.+)$",
        )

        for pattern in patterns:

            match = re.match(
                pattern,
                clean,
                flags=re.IGNORECASE,
            )

            if match:
                return match.group(
                    1
                ).strip()

        return clean

    # ======================================================
    # NUMBERS
    # ======================================================

    def _extract_numbers(
        self,
        text: str,
    ) -> list[float | int]:

        pattern = r"""
            (?<![\w])
            [-+]?
            (?:
                \d{1,3}(?:,\d{3})+
                |
                \d+(?:\.\d+)?
                |
                \.\d+
            )
            (?![\w])
        """

        matches = re.findall(
            pattern,
            text,
            flags=re.VERBOSE,
        )

        values: list[
            float | int
        ] = []

        for raw in matches:

            raw = raw.replace(
                ",",
                "",
            )

            try:

                value = float(
                    raw
                )

                if value.is_integer():
                    value = int(value)

                values.append(
                    value
                )

            except ValueError:
                continue

        return values

    # ======================================================
    # EQUATIONS
    # ======================================================

    def _extract_equations(
        self,
        text: str,
    ) -> list[str]:
        r"""
        Extract mathematical equations from
        natural-language input.

        Example:

            Giải phương trình 2*x + 5 = 15

        becomes:

            2*x + 5 = 15

        Important:

        The regex must never start inside a
        Unicode word.

        Example of the old bug:

            trình

        could incorrectly become:

            nh

        The boundary:

            (?<![\w])

        prevents that.
        """

        equations: list[str] = []

        # --------------------------------------------------
        # Mathematical token
        # --------------------------------------------------

        token = r"""
            (?:
                [A-Za-z_][A-Za-z0-9_]*
                |
                \d+(?:\.\d+)?
                |
                [()+\-*/^]
            )
        """

        # --------------------------------------------------
        # Equation
        #
        # Important:
        #
        # (?<![\w])
        #
        # means the equation cannot start
        # in the middle of a word.
        #
        # (?![\w])
        #
        # means it cannot end in the middle
        # of a word.
        # --------------------------------------------------

        equation_pattern = rf"""
            (?<![\w])
            (?P<equation>
                {token}
                (?:
                    \s*
                    {token}
                )*
                \s*
                =
                \s*
                {token}
                (?:
                    \s*
                    {token}
                )*
            )
            (?![\w])
        """

        matches = re.finditer(
            equation_pattern,
            text,
            flags=re.VERBOSE,
        )

        for match in matches:

            equation = match.group(
                "equation"
            )

            equation = self._clean_expression(
                equation
            )

            if not equation:
                continue

            # Must contain "="
            if "=" not in equation:
                continue

            # Reject non-ASCII natural-language
            # characters.
            #
            # Example:
            #
            # "trình 2*x = 15"
            #
            # should never be accepted.
            if re.search(
                r"[^\x00-\x7F]",
                equation,
            ):
                continue

            # Must contain at least one
            # alphanumeric token.
            if not re.search(
                r"[A-Za-z0-9_]",
                equation,
            ):
                continue

            equations.append(
                equation
            )

        return self._deduplicate(
            equations
        )

    # ======================================================
    # CALCULATION
    # ======================================================

    def _extract_calculation_expression(
        self,
        text: str,
    ) -> str | None:

        candidate = re.sub(
            r"^\s*"
            r"(?:tính|calculate|compute|tính toán)"
            r"\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()

        # An equation is mathematics,
        # not a simple calculator expression.
        if "=" in candidate:
            return None

        # --------------------------------------------------
        # Entire input is arithmetic
        # --------------------------------------------------

        if re.fullmatch(
            r"[-+*/().\d\s]+",
            candidate,
        ):

            if re.search(
                r"\d\s*[\+\-\*/]\s*\d",
                candidate,
            ):
                return self._clean_expression(
                    candidate
                )

        # --------------------------------------------------
        # Arithmetic expression embedded
        # in natural language
        # --------------------------------------------------

        match = re.search(
            r"""
            (
                [-+]?
                \d+(?:\.\d+)?
                \s*
                [+\-*/]
                \s*
                [-+]?
                \d+(?:\.\d+)?
                (?:
                    \s*
                    [+\-*/]
                    \s*
                    [-+]?
                    \d+(?:\.\d+)?
                )*
            )
            """,
            text,
            flags=re.VERBOSE,
        )

        if match:

            return self._clean_expression(
                match.group(1)
            )

        return None

    # ======================================================
    # UNKNOWNS
    # ======================================================

    def _extract_unknowns(
        self,
        raw_text: str,
        equations: list[str],
    ) -> list[Unknown]:

        unknown_names: list[str] = []

        # --------------------------------------------------
        # Extract identifiers from equations
        # --------------------------------------------------

        for equation in equations:

            parts = equation.split(
                "=",
                1,
            )

            if len(parts) != 2:
                continue

            left, right = parts

            expression = (
                f"{left} {right}"
            )

            identifiers = re.findall(
                r"(?<![\wÀ-ỹ])"
                r"[A-Za-z_]"
                r"[A-Za-z0-9_]*"
                r"(?![\wÀ-ỹ])",
                expression,
            )

            for identifier in identifiers:

                normalized = (
                    identifier.strip()
                )

                if self._is_valid_unknown_identifier(
                    normalized
                ):
                    unknown_names.append(
                        normalized
                    )

        # --------------------------------------------------
        # Explicit unknown declarations
        # --------------------------------------------------

        explicit_patterns = (
            r"\bẩn\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",

            r"\bunknown\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",

            r"\bvariable\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",

            r"\bbiến\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)\b",
        )

        for pattern in explicit_patterns:

            matches = re.findall(
                pattern,
                raw_text,
                flags=re.IGNORECASE,
            )

            for match in matches:

                if self._is_valid_unknown_identifier(
                    match
                ):
                    unknown_names.append(
                        match
                    )

        unknown_names = self._deduplicate(
            [
                name
                for name in unknown_names
                if name
            ]
        )

        return [
            Unknown(
                name=name,
                description=(
                    "Unknown variable inferred "
                    "from problem structure"
                ),
                source="equation",
            )
            for name in unknown_names
        ]

    def _is_valid_unknown_identifier(
        self,
        identifier: str,
    ) -> bool:

        if not identifier:
            return False

        lowered = identifier.lower()

        excluded = {
            "sin",
            "cos",
            "tan",
            "sqrt",
            "log",
            "ln",
            "exp",
            "abs",
            "max",
            "min",
            "pi",
            "e",
        }

        if lowered in excluded:
            return False

        return bool(
            re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*",
                identifier,
            )
        )

    # ======================================================
    # CONSTRAINTS
    # ======================================================

    def _extract_constraints(
        self,
        text: str,
    ) -> list[Constraint]:

        constraints: list[
            Constraint
        ] = []

        patterns = (
            (
                r"(?:phải|must|should)\s+(.+)",
                "requirement",
            ),
            (
                r"(?:không được|must not|cannot|can't)"
                r"\s+(.+)",
                "prohibition",
            ),
            (
                r"(?:ít nhất|at least)\s+(.+)",
                "minimum",
            ),
            (
                r"(?:tối đa|at most|maximum)\s+(.+)",
                "maximum",
            ),
        )

        for pattern, kind in patterns:

            matches = re.findall(
                pattern,
                text,
                flags=re.IGNORECASE,
            )

            for match in matches:

                description = (
                    match.strip()
                )

                if description:

                    constraints.append(
                        Constraint(
                            description=description,
                            kind=kind,
                            hard=True,
                            source="input",
                        )
                    )

        return constraints

    # ======================================================
    # ENTITIES
    # ======================================================

    def _extract_entities(
        self,
        text: str,
    ) -> list[str]:

        known_entities = (
            "PostgreSQL",
            "MySQL",
            "SQLite",
            "Redis",
            "MongoDB",
            "Python",
            "Flask",
            "FastAPI",
            "Django",
            "Docker",
            "Kubernetes",
            "Nginx",
            "API",
            "HTTP",
            "SQL",
            "database",
            "warehouse",
            "lock",
            "row locking",
            "deadlock",
            "concurrency",
            "concurrent writes",
        )

        entities: list[str] = []

        lowered = text.lower()

        for entity in known_entities:

            if entity.lower() in lowered:
                entities.append(
                    entity
                )

        return self._deduplicate(
            entities
        )

    # ======================================================
    # EVIDENCE REQUIREMENTS
    # ======================================================

    def _extract_evidence_requirements(
        self,
        text: str,
    ) -> list[EvidenceRequirement]:

        requirements: list[
            EvidenceRequirement
        ] = []

        lowered = text.lower()

        # --------------------------------------------------
        # Question
        #
        # A question mark alone is a weak signal:
        # "Python là gì?" can be answered from stable
        # knowledge. Record it, but not as required.
        # --------------------------------------------------

        if "?" in text:

            requirements.append(
                EvidenceRequirement(
                    description=(
                        "Verify factual claims "
                        "relevant to the question."
                    ),
                    source_type="external",
                    required=False,
                    reason=(
                        "Input is phrased as a question."
                    ),
                )
            )

        # --------------------------------------------------
        # Time-sensitive information
        # --------------------------------------------------

        if self._contains_any(
            lowered,
            (
                "hiện nay",
                "hiện tại",
                "mới nhất",
                "gần đây",
                "hôm nay",
                "bây giờ",
            ),
        ) or re.search(
            r"\b(?:latest|current|currently|today|recent|recently)\b"
            r"|\b20\d{2}\b",
            lowered,
        ):

            requirements.append(
                EvidenceRequirement(
                    description=(
                        "Retrieve up-to-date external "
                        "information."
                    ),
                    source_type="external",
                    required=True,
                    reason=(
                        "Input refers to time-sensitive "
                        "information."
                    ),
                )
            )

        # --------------------------------------------------
        # Decision
        # --------------------------------------------------

        if any(
            keyword in lowered
            for keyword in (
                "nên dùng",
                "nên chọn",
                "compare",
                "versus",
                "vs",
                "so với",
            )
        ):

            requirements.append(
                EvidenceRequirement(
                    description=(
                        "Compare alternatives using "
                        "relevant technical evidence "
                        "and constraints."
                    ),
                    source_type="technical",
                    required=True,
                    reason=(
                        "Decision between alternatives."
                    ),
                )
            )

        return requirements

    # ======================================================
    # SUCCESS CRITERIA
    # ======================================================

    def _extract_success_criteria(
        self,
        text: str,
    ) -> list[SuccessCriterion]:

        criteria: list[
            SuccessCriterion
        ] = []

        lowered = text.lower()

        if any(
            keyword in lowered
            for keyword in (
                "tối ưu",
                "optimize",
                "performance",
                "hiệu năng",
                "faster",
                "nhanh hơn",
            )
        ):

            criteria.append(
                SuccessCriterion(
                    description=(
                        "Improve the requested "
                        "performance-related outcome."
                    ),
                    measurable=True,
                    metric="performance",
                )
            )

        return criteria

    # ======================================================
    # OBSERVATIONS
    # ======================================================

    def _extract_observations(
        self,
        text: str,
    ) -> list[str]:

        observations: list[str] = []

        lowered = text.lower()

        if any(
            keyword in lowered
            for keyword in (
                "deadlock",
                "error",
                "exception",
                "timeout",
                "crash",
                "lỗi",
                "bị treo",
            )
        ):

            observations.append(
                "User reports a failure, error, "
                "timeout, crash, or related "
                "abnormal behavior."
            )

        return observations

    # ======================================================
    # ASSUMPTIONS
    # ======================================================

    def _extract_assumptions(
        self,
        text: str,
    ) -> list[Assumption]:

        assumptions: list[
            Assumption
        ] = []

        lowered = text.lower()

        patterns = (
            "giả sử",
            "assume",
            "assuming",
            "giả định",
        )

        if any(
            pattern in lowered
            for pattern in patterns
        ):

            assumptions.append(
                Assumption(
                    description=(
                        "The input contains an "
                        "explicit assumption that "
                        "should be validated."
                    ),
                    confidence=0.8,
                    source="input",
                )
            )

        return assumptions

    # ======================================================
    # METADATA
    # ======================================================

    def _populate_metadata(
        self,
        problem: ProblemModel,
    ) -> None:

        raw_text = (
            problem.input.raw_text.lower()
        )

        problem.metadata[
            "has_numeric_structure"
        ] = bool(
            problem.variables
        )

        problem.metadata[
            "has_equations"
        ] = bool(
            problem.metadata.get(
                "equations"
            )
        )

        problem.metadata[
            "has_unknown_variables"
        ] = bool(
            problem.unknowns
        )

        problem.metadata[
            "multiple_unknowns"
        ] = (
            len(problem.unknowns) > 1
        )

        problem.metadata[
            "has_constraints"
        ] = bool(
            problem.constraints
        )

        problem.metadata[
            "has_entities"
        ] = bool(
            problem.entities
        )

        problem.metadata[
            "has_evidence_requirements"
        ] = bool(
            problem.evidence_requirements
        )

        problem.metadata[
            "requires_decision_context"
        ] = self._contains_any(
            raw_text,
            (
                "nên dùng",
                "nên chọn",
                "should i",
                "should we",
                "vs",
                "versus",
                "so với",
            ),
        )

        problem.metadata[
            "failure_detected"
        ] = self._contains_any(
            raw_text,
            (
                "deadlock",
                "error",
                "exception",
                "timeout",
                "crash",
                "failed",
                "failure",
                "bug",
                "lỗi",
                "bị treo",
                "không hoạt động",
                "không chạy",
            ),
        )

        problem.metadata[
            "reconstruction_complete"
        ] = True

    # ======================================================
    # HELPERS
    # ======================================================

    def _clean_expression(
        self,
        expression: str,
    ) -> str:

        expression = expression.strip()

        expression = re.sub(
            r"\s+",
            " ",
            expression,
        )

        expression = expression.strip(
            " ,.;:!?"
        )

        return expression

    def _deduplicate(
        self,
        values: list[Any],
    ) -> list[Any]:

        seen = set()

        result = []

        for value in values:

            key = (
                value.lower()
                if isinstance(
                    value,
                    str,
                )
                else value
            )

            if key in seen:
                continue

            seen.add(
                key
            )

            result.append(
                value
            )

        return result

    def _contains_any(
        self,
        text: str,
        keywords: tuple[str, ...],
    ) -> bool:

        return any(
            keyword.lower() in text
            for keyword in keywords
        )