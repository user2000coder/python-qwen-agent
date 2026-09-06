"""
BCOS Evidence Verifier
=======================

Evidence verification layer for the BCOS Agent.

Design principle
----------------

    NOT PROVEN != PROVEN FALSE

Evidence can be:

    SUPPORTS
    CONTRADICTS
    IRRELEVANT

Aggregated verification status:

    SUPPORTED
    CONTRADICTED
    CONFLICTED
    INSUFFICIENT

Architecture
------------

Question
   |
   v
Question Signals
   |
   +-----------------------------+
   |                             |
   v                             v
Deterministic Rules          LLM Fallback
   |                             |
   +-------------+---------------+
                 |
                 v
        Contradiction Safety Gate
                 |
                 v
        Final Classification
                 |
                 v
             Aggregate

Important
---------

The LLM is NOT authoritative.

The LLM may classify an ambiguous result, but Python
enforces epistemic safety rules afterward.

Especially:

    lack of support
        !=
    contradiction

Historical evidence that does not cover the requested
time period is IRRELEVANT, not CONTRADICTS.
"""

import json
import re
import unicodedata


class EvidenceVerifier:

    # =========================================================
    # INDIVIDUAL EVIDENCE LABELS
    # =========================================================

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    IRRELEVANT = "IRRELEVANT"

    # =========================================================
    # AGGREGATED VERIFICATION STATUS
    # =========================================================

    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    CONFLICTED = "CONFLICTED"
    INSUFFICIENT = "INSUFFICIENT"

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(self, llm):
        self.llm = llm

    # =========================================================
    # TEXT NORMALIZATION
    # =========================================================

    def normalize(self, text):
        """
        Normalize text for deterministic matching.

        Example:

            "Tổng thống Mỹ"
                ->
            "tong thong my"
        """

        if text is None:
            return ""

        text = str(text).lower()

        text = unicodedata.normalize(
            "NFD",
            text
        )

        text = "".join(
            char
            for char in text
            if unicodedata.category(char) != "Mn"
        )

        text = text.replace(
            "đ",
            "d"
        )

        text = re.sub(
            r"\s+",
            " ",
            text
        )

        return text.strip()

    # =========================================================
    # JSON EXTRACTION
    # =========================================================

    def _extract_json(self, text):
        """
        Extract a JSON object from an LLM response.
        """

        if not text:
            return None

        text = str(text).strip()

        # -----------------------------------------------------
        # Direct JSON
        # -----------------------------------------------------

        try:
            data = json.loads(text)

            if isinstance(data, dict):
                return data

        except Exception:
            pass

        # -----------------------------------------------------
        # JSON embedded in prose / markdown
        # -----------------------------------------------------

        start = text.find("{")
        end = text.rfind("}")

        if (
            start == -1
            or end == -1
            or end <= start
        ):
            return None

        candidate = text[
            start:end + 1
        ]

        try:
            data = json.loads(candidate)

            if isinstance(data, dict):
                return data

        except Exception:
            pass

        return None

    # =========================================================
    # QUESTION SIGNAL EXTRACTION
    # =========================================================

    def _question_signals(self, question):
        """
        Extract deterministic semantic signals.

        This is intentionally conservative.
        """

        text = self.normalize(question)

        years = [
            int(value)
            for value in re.findall(
                r"\b(19\d{2}|20\d{2}|21\d{2})\b",
                text
            )
        ]

        asks_president = any(
            token in text
            for token in [
                "tong thong my",
                "tong thong hoa ky",
                "us president",
                "president of the united states",
                "president usa",
                "president us",
            ]
        )

        asks_savepoint = (
            "savepoint"
            in text
        )

        asks_sqlite = (
            "sqlite"
            in text
        )

        asks_postgresql = (
            "postgresql"
            in text
            or "postgres"
            in text
        )

        return {
            "text": text,

            "years": years,

            "year": (
                years[-1]
                if years
                else None
            ),

            "asks_president": asks_president,

            "asks_savepoint": asks_savepoint,

            "asks_sqlite": asks_sqlite,

            "asks_postgresql": asks_postgresql,
        }

    # =========================================================
    # CLAIM EXTRACTION
    # =========================================================

    def extract_claim(self, question):
        """
        Preserve the original user question.

        Do not ask the LLM to reinterpret the claim before
        verification.

        This prevents:

            "ai là tổng thống mỹ 2026"

        from being transformed into:

            "ai sẽ trở thành tổng thống Mỹ trong tương lai?"
        """

        if question is None:
            return ""

        return str(question).strip()

    # =========================================================
    # KNOWN PERSON EXTRACTION
    # =========================================================

    def extract_candidate_names(
        self,
        title,
        content
    ):
        """
        Conservative candidate extraction.

        This is not a general-purpose NER system.

        It only provides deterministic guardrails for
        high-value known entities.
        """

        text = (
            f"{title} {content}"
        )

        candidates = []

        known_people = [
            "Donald Trump",
            "Joe Biden",
            "Barack Obama",
            "George W. Bush",
            "Bill Clinton",
            "George H. W. Bush",
            "Ronald Reagan",
            "Jimmy Carter",
            "Gerald Ford",
            "Richard Nixon",
            "Lyndon B. Johnson",
            "John F. Kennedy",
            "Dwight D. Eisenhower",
            "Harry S. Truman",
            "Franklin D. Roosevelt",
        ]

        lower_text = text.lower()

        for name in known_people:

            if name.lower() in lower_text:

                if name not in candidates:
                    candidates.append(name)

        return candidates

    # =========================================================
    # PRESIDENT TENURE EXTRACTION
    # =========================================================

    def extract_president_tenure(self, text):
        """
        Extract explicit presidential tenure ranges.

        Supported examples:

            2017 to 2021
            2017-2021
            2017 – 2021
            from 2017 to 2021

        Returns:

            (start_year, end_year)

        or:

            None
        """

        normalized = self.normalize(text)

        patterns = [
            r"\b(19\d{2}|20\d{2})\s*(?:-|–|—|to|den)\s*(19\d{2}|20\d{2})\b",

            r"\bfrom\s+(19\d{2}|20\d{2})\s+to\s+(19\d{2}|20\d{2})\b",

            r"\btu\s+nam\s+(19\d{2}|20\d{2})\s+den\s+nam\s+(19\d{2}|20\d{2})\b",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                normalized
            )

            if not match:
                continue

            try:

                start_year = int(
                    match.group(1)
                )

                end_year = int(
                    match.group(2)
                )

                if (
                    1900 <= start_year <= 2100
                    and 1900 <= end_year <= 2100
                    and start_year <= end_year
                ):

                    return (
                        start_year,
                        end_year
                    )

            except Exception:
                continue

        return None

    # =========================================================
    # EXPLICIT PRESIDENT NEGATION
    # =========================================================

    def _has_explicit_president_negation(
        self,
        text,
        candidate_names,
        requested_year
    ):
        """
        Detect explicit contradiction.

        IMPORTANT:

        Historical evidence is NOT contradiction.

        Only explicit evidence that the candidate is NOT
        President in the requested year qualifies.
        """

        normalized = self.normalize(text)

        year = str(
            requested_year
        )

        # -----------------------------------------------------
        # Generic explicit negation
        # -----------------------------------------------------

        negative_patterns = [
            rf"not.*president.*{year}",
            rf"not.*president.*in.*{year}",
            rf"was not.*president.*{year}",
            rf"wasnt.*president.*{year}",
            rf"not.*the president.*{year}",

            rf"not.*president.*in {year}",

            rf"khong.*la.*tong thong.*{year}",
            rf"khong.*phai.*tong thong.*{year}",
            rf"khong.*lam.*tong thong.*{year}",
            rf"khong.*giu.*chuc.*tong thong.*{year}",
        ]

        for pattern in negative_patterns:

            if re.search(
                pattern,
                normalized
            ):
                return True

        # -----------------------------------------------------
        # Candidate-specific negation
        # -----------------------------------------------------

        for candidate in candidate_names:

            candidate_normalized = (
                self.normalize(candidate)
            )

            if candidate_normalized not in normalized:
                continue

            candidate_patterns = [
                (
                    rf"{re.escape(candidate_normalized)}"
                    rf".*not.*president.*{year}"
                ),

                (
                    rf"{re.escape(candidate_normalized)}"
                    rf".*was not.*president.*{year}"
                ),

                (
                    rf"{re.escape(candidate_normalized)}"
                    rf".*khong.*la.*tong thong.*{year}"
                ),

                (
                    rf"{re.escape(candidate_normalized)}"
                    rf".*khong.*phai.*tong thong.*{year}"
                ),
            ]

            for pattern in candidate_patterns:

                if re.search(
                    pattern,
                    normalized
                ):
                    return True

        return False

    # =========================================================
    # PRESIDENT EVIDENCE
    # =========================================================

    def _president_evidence(
        self,
        question,
        title,
        content,
        result_id,
        url
    ):
        """
        Deterministic verification for US President questions.
        """

        signals = self._question_signals(
            question
        )

        if not signals.get(
            "asks_president",
            False
        ):
            return None

        requested_year = signals.get(
            "year"
        )

        if requested_year is None:
            return None

        text = (
            f"{title} {content}"
        )

        normalized = self.normalize(
            text
        )

        candidate_names = (
            self.extract_candidate_names(
                title,
                content
            )
        )

        if not candidate_names:
            return None

        # =====================================================
        # 1. EXPLICIT NEGATION
        # =====================================================

        if self._has_explicit_president_negation(
            text,
            candidate_names,
            requested_year
        ):

            return {
                "label": self.CONTRADICTS,

                "reason": (
                    "Evidence explicitly states that "
                    "the candidate was not President "
                    f"in {requested_year}."
                ),

                "candidate_names": candidate_names,

                "confidence": 0.95,

                "method": (
                    "deterministic-president-negation"
                ),

                "result_id": result_id,

                "title": title,

                "url": url,
            }

        # =====================================================
        # 2. EXPLICIT YEAR + PRESIDENT
        # =====================================================

        positive_patterns = [
            rf"president.*{requested_year}",
            rf"president.*in.*{requested_year}",
            rf"president.*during.*{requested_year}",

            rf"tong thong.*{requested_year}",
            rf"tong thong.*nam.*{requested_year}",

            rf"duong nhiem.*{requested_year}",
            rf"incumbent.*{requested_year}",
            rf"current.*president.*{requested_year}",
        ]

        for pattern in positive_patterns:

            if re.search(
                pattern,
                normalized
            ):

                return {
                    "label": self.SUPPORTS,

                    "reason": (
                        "Evidence identifies the US "
                        "president and contains the "
                        "requested year."
                    ),

                    "candidate_names": candidate_names,

                    "confidence": 0.95,

                    "method": (
                        "deterministic-president-temporal"
                    ),

                    "result_id": result_id,

                    "title": title,

                    "url": url,
                }

        # =====================================================
        # 3. EXPLICIT TENURE
        # =====================================================

        tenure = self.extract_president_tenure(
            text
        )

        if tenure:

            start_year, end_year = tenure

            # -------------------------------------------------
            # Requested year is covered
            # -------------------------------------------------

            if (
                start_year
                <= requested_year
                <= end_year
            ):

                return {
                    "label": self.SUPPORTS,

                    "reason": (
                        "Evidence states a presidential "
                        "tenure covering the requested year."
                    ),

                    "candidate_names": candidate_names,

                    "confidence": 0.95,

                    "method": (
                        "deterministic-president-tenure"
                    ),

                    "result_id": result_id,

                    "title": title,

                    "url": url,
                }

            # -------------------------------------------------
            # Historical tenure does NOT cover requested year
            #
            # This is IRRELEVANT.
            #
            # It is NOT CONTRADICTS.
            # -------------------------------------------------

            return {
                "label": self.IRRELEVANT,

                "reason": (
                    "Evidence describes a historical "
                    "presidential tenure that does not "
                    "cover the requested year. This does "
                    "not constitute evidence against the "
                    "claim."
                ),

                "candidate_names": candidate_names,

                "confidence": 0.95,

                "method": (
                    "deterministic-president-temporal"
                ),

                "result_id": result_id,

                "title": title,

                "url": url,
            }

        # =====================================================
        # 4. INCUMBENT PRESIDENT
        # =====================================================

        if (
            "incumbent president"
            in normalized
            or "duong nhiem tong thong"
            in normalized
        ):

            if str(
                requested_year
            ) in normalized:

                return {
                    "label": self.SUPPORTS,

                    "reason": (
                        "Evidence identifies an incumbent "
                        "President in the requested year."
                    ),

                    "candidate_names": candidate_names,

                    "confidence": 0.95,

                    "method": (
                        "deterministic-president-incumbent"
                    ),

                    "result_id": result_id,

                    "title": title,

                    "url": url,
                }

        return None

    # =========================================================
    # SAVEPOINT EVIDENCE
    # =========================================================

    def _savepoint_evidence(
        self,
        question,
        title,
        content,
        result_id,
        url
    ):
        """
        Deterministic SAVEPOINT verification.
        """

        signals = self._question_signals(
            question
        )

        if not signals.get(
            "asks_savepoint",
            False
        ):
            return None

        text = (
            f"{title} {content}"
        )

        normalized = self.normalize(
            text
        )

        asks_sqlite = signals.get(
            "asks_sqlite",
            False
        )

        asks_postgresql = signals.get(
            "asks_postgresql",
            False
        )

        # =====================================================
        # SQLITE
        # =====================================================

        if asks_sqlite:

            if "sqlite" not in normalized:
                return None

            if "savepoint" not in normalized:
                return None

            # -------------------------------------------------
            # Explicit negation
            # -------------------------------------------------

            if any(
                token in normalized
                for token in [
                    "does not support",
                    "doesnt support",
                    "not support",
                    "not supported",
                    "khong ho tro",
                    "khong ho tro savepoint",
                ]
            ):

                return {
                    "label": self.CONTRADICTS,

                    "reason": (
                        "Evidence explicitly states "
                        "that SQLite does not support "
                        "SAVEPOINT."
                    ),

                    "confidence": 0.95,

                    "method": (
                        "deterministic-savepoint-negation"
                    ),

                    "result_id": result_id,

                    "title": title,

                    "url": url,
                }

            # -------------------------------------------------
            # Positive evidence
            # -------------------------------------------------

            positive_tokens = [
                "supports",
                "support",
                "command",
                "transaction",
                "starts a new",
                "begin",
                "create",
                "savepoint",
            ]

            if any(
                token in normalized
                for token in positive_tokens
            ):

                return {
                    "label": self.SUPPORTS,

                    "reason": (
                        "Evidence explicitly describes "
                        "SQLite SAVEPOINT functionality."
                    ),

                    "confidence": 0.95,

                    "method": (
                        "deterministic-savepoint"
                    ),

                    "result_id": result_id,

                    "title": title,

                    "url": url,
                }

        # =====================================================
        # POSTGRESQL
        # =====================================================

        if asks_postgresql:

            database_match = (
                "postgresql"
                in normalized
                or "postgres"
                in normalized
            )

            if not database_match:
                return None

            if "savepoint" not in normalized:
                return None

            # -------------------------------------------------
            # Explicit negation
            # -------------------------------------------------

            if any(
                token in normalized
                for token in [
                    "does not support",
                    "doesnt support",
                    "not support",
                    "not supported",
                    "khong ho tro",
                    "khong ho tro savepoint",
                ]
            ):

                return {
                    "label": self.CONTRADICTS,

                    "reason": (
                        "Evidence explicitly states "
                        "that PostgreSQL does not support "
                        "SAVEPOINT."
                    ),

                    "confidence": 0.95,

                    "method": (
                        "deterministic-savepoint-negation"
                    ),

                    "result_id": result_id,

                    "title": title,

                    "url": url,
                }

            return {
                "label": self.SUPPORTS,

                "reason": (
                    "Evidence explicitly describes "
                    "PostgreSQL SAVEPOINT functionality."
                ),

                "confidence": 0.95,

                "method": (
                    "deterministic-savepoint"
                ),

                "result_id": result_id,

                "title": title,

                "url": url,
            }

        return None

    # =========================================================
    # ENTITY MISMATCH
    # =========================================================

    def _entity_mismatch(
        self,
        question,
        title,
        content
    ):
        """
        Detect obvious entity mismatch.
        """

        signals = self._question_signals(
            question
        )

        normalized = self.normalize(
            f"{title} {content}"
        )

        # =====================================================
        # SQLITE QUESTION vs POSTGRESQL EVIDENCE
        # =====================================================

        if (
            signals.get(
                "asks_sqlite",
                False
            )
            and (
                "postgresql"
                in normalized
                or "postgres"
                in normalized
            )
            and "sqlite"
            not in normalized
        ):

            return True

        # =====================================================
        # POSTGRESQL QUESTION vs SQLITE EVIDENCE
        # =====================================================

        if (
            signals.get(
                "asks_postgresql",
                False
            )
            and "sqlite"
            in normalized
            and (
                "postgresql"
                not in normalized
                and "postgres"
                not in normalized
            )
        ):

            return True

        # =====================================================
        # US PRESIDENT vs FOREIGN PRESIDENT
        # =====================================================

        if signals.get(
            "asks_president",
            False
        ):

            foreign_entities = [
                "france",
                "germany",
                "united kingdom",
                "uk",
                "japan",
                "china",
                "russia",
                "vietnam",
                "india",
                "canada",
                "australia",
            ]

            has_us = any(
                token in normalized
                for token in [
                    "united states",
                    "united states of america",
                    "us president",
                    "u.s. president",
                    "tong thong my",
                    "tong thong hoa ky",
                ]
            )

            if (
                any(
                    token in normalized
                    for token in foreign_entities
                )
                and not has_us
            ):

                return True

        return False

    # =========================================================
    # CLASSIFY EVIDENCE
    # =========================================================

    def classify_evidence(
        self,
        question,
        item,
        result_id
    ):
        """
        Classify one evidence result.

        Priority:

            1. Invalid evidence
            2. Entity mismatch
            3. President deterministic rules
            4. SAVEPOINT deterministic rules
            5. Conservative LLM fallback
        """

        if not isinstance(
            item,
            dict
        ):

            return {
                "label": self.IRRELEVANT,

                "reason": (
                    "Invalid evidence item."
                ),

                "confidence": 1.0,

                "method": (
                    "deterministic-invalid"
                ),

                "result_id": result_id,

                "title": "",

                "url": "",
            }

        title = str(
            item.get(
                "title",
                ""
            )
        )

        content = str(
            item.get(
                "content",
                ""
            )
        )

        url = str(
            item.get(
                "url",
                ""
            )
        )

        # =====================================================
        # ENTITY MISMATCH
        # =====================================================

        if self._entity_mismatch(
            question,
            title,
            content
        ):

            return {
                "label": self.IRRELEVANT,

                "reason": (
                    "Evidence refers to a different "
                    "entity or database than the one "
                    "asked about."
                ),

                "confidence": 0.98,

                "method": (
                    "deterministic-entity-mismatch"
                ),

                "result_id": result_id,

                "title": title,

                "url": url,
            }

        # =====================================================
        # PRESIDENT
        # =====================================================

        president_result = (
            self._president_evidence(
                question,
                title,
                content,
                result_id,
                url
            )
        )

        if president_result is not None:
            return president_result

        # =====================================================
        # SAVEPOINT
        # =====================================================

        savepoint_result = (
            self._savepoint_evidence(
                question,
                title,
                content,
                result_id,
                url
            )
        )

        if savepoint_result is not None:
            return savepoint_result

        # =====================================================
        # LLM FALLBACK
        # =====================================================

        return self._llm_classify(
            question,
            title,
            content,
            result_id,
            url
        )

    # =========================================================
    # EXPLICIT CONTRADICTION SAFETY GATE
    # =========================================================

    def _has_explicit_contradiction(
        self,
        normalized_question,
        normalized_evidence
    ):
        """
        Safety gate for LLM-generated CONTRADICTS.

        The LLM is NOT allowed to turn:

            "I don't know"

        into:

            "FALSE"

        A contradiction must be explicitly observable
        in the evidence.

        This function is deliberately conservative.
        """

        question_signals = (
            self._question_signals(
                normalized_question
            )
        )

        # =====================================================
        # PRESIDENT
        # =====================================================

        if question_signals.get(
            "asks_president",
            False
        ):

            requested_year = (
                question_signals.get(
                    "year"
                )
            )

            if requested_year is not None:

                candidate_names = (
                    self.extract_candidate_names(
                        "",
                        normalized_evidence
                    )
                )

                if self._has_explicit_president_negation(
                    normalized_evidence,
                    candidate_names,
                    requested_year
                ):

                    return True

                # -------------------------------------------------
                # IMPORTANT
                #
                # A historical president, unrelated article,
                # ranking, opinion, or absence of information
                # does NOT contradict an open "who is president?"
                # question.
                # -------------------------------------------------

                return False

        # =====================================================
        # SAVEPOINT
        # =====================================================

        if question_signals.get(
            "asks_savepoint",
            False
        ):

            database_terms = []

            if question_signals.get(
                "asks_sqlite",
                False
            ):

                database_terms.append(
                    "sqlite"
                )

            if question_signals.get(
                "asks_postgresql",
                False
            ):

                database_terms.extend(
                    [
                        "postgresql",
                        "postgres",
                    ]
                )

            database_present = any(
                term in normalized_evidence
                for term in database_terms
            )

            if database_present:

                negative_patterns = [
                    "does not support savepoint",
                    "doesnt support savepoint",
                    "not support savepoint",
                    "not supported",
                    "khong ho tro savepoint",
                    "khong ho tro",
                ]

                for pattern in negative_patterns:

                    if pattern in normalized_evidence:
                        return True

                return False

        # =====================================================
        # GENERIC EXPLICIT NEGATION
        # =====================================================

        generic_patterns = [
            "is false",
            "is incorrect",
            "is wrong",
            "is not true",
            "not the case",
            "does not support",
            "doesnt support",
            "is not supported",
            "khong dung",
            "khong phai",
            "khong phai la",
            "khong ho tro",
            "khong duoc ho tro",
        ]

        for pattern in generic_patterns:

            if pattern in normalized_evidence:
                return True

        return False

    # =========================================================
    # LLM FALLBACK
    # =========================================================

    def _llm_classify(
        self,
        question,
        title,
        content,
        result_id,
        url
    ):
        """
        Conservative LLM fallback.

        IMPORTANT:

        LLM classification is advisory.

        Python applies the contradiction safety gate
        afterward.
        """

        prompt = f"""
Bạn là Evidence Classifier của BCOS.

CÂU HỎI:
{question}

EVIDENCE:

TITLE:
{title}

CONTENT:
{content}

Phân loại evidence thành đúng một:

SUPPORTS
CONTRADICTS
IRRELEVANT

QUY TẮC EPISTEMIC:

1. SUPPORTS

Evidence trực tiếp hỗ trợ claim trong câu hỏi.

2. CONTRADICTS

Chỉ chọn CONTRADICTS khi evidence trực tiếp chứng minh
điều ngược lại với claim.

3. IRRELEVANT

Chọn IRRELEVANT khi evidence:

- không liên quan,
- không đủ thông tin,
- chỉ nói về lịch sử khác,
- không bao phủ năm được hỏi,
- chỉ nói về chủ đề liên quan nhưng không trả lời claim.

4. CỰC KỲ QUAN TRỌNG:

"Không hỗ trợ claim"
KHÔNG đồng nghĩa với
"phản bác claim".

Ví dụ:

Question:
Ai là tổng thống Mỹ năm 2026?

Evidence:
Donald Trump was President from 2017 to 2021.

Classification:
IRRELEVANT

Không phải:
CONTRADICTS

5. Nếu evidence chỉ nói về Joe Biden trong giai đoạn
2021-2025 và câu hỏi hỏi năm 2026:

IRRELEVANT

6. Nếu evidence chỉ là bảng xếp hạng tổng thống:

IRRELEVANT

7. Nếu evidence nói:

"Donald Trump was NOT President in 2026"

thì:

CONTRADICTS

8. Không dùng kiến thức bên ngoài evidence.

9. Không suy luận:

lack of evidence = false

10. Confidence thấp thì ưu tiên IRRELEVANT.

Trả về JSON duy nhất:

{{
    "label": "SUPPORTS | CONTRADICTS | IRRELEVANT",
    "reason": "...",
    "confidence": 0.0
}}
"""

        try:

            response = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": prompt,
                    }
                ]
            )

            data = self._extract_json(
                response
            )

            if not isinstance(
                data,
                dict
            ):

                raise ValueError(
                    "LLM returned invalid JSON"
                )

            label = str(
                data.get(
                    "label",
                    self.IRRELEVANT
                )
            ).upper().strip()

            if label not in (
                self.SUPPORTS,
                self.CONTRADICTS,
                self.IRRELEVANT,
            ):

                label = self.IRRELEVANT

            confidence = data.get(
                "confidence",
                0.5
            )

            try:

                confidence = float(
                    confidence
                )

            except Exception:

                confidence = 0.5

            confidence = max(
                0.0,
                min(
                    1.0,
                    confidence
                )
            )

            reason = str(
                data.get(
                    "reason",
                    "LLM classification."
                )
            )

            # =================================================
            # CONTRADICTION SAFETY GATE
            # =================================================

            if label == self.CONTRADICTS:

                normalized_question = (
                    self.normalize(
                        question
                    )
                )

                normalized_evidence = (
                    self.normalize(
                        f"{title} {content}"
                    )
                )

                explicit_contradiction = (
                    self._has_explicit_contradiction(
                        normalized_question,
                        normalized_evidence
                    )
                )

                if not explicit_contradiction:

                    label = self.IRRELEVANT

                    reason = (
                        "LLM suggested CONTRADICTS, "
                        "but the evidence does not contain "
                        "an explicit contradiction. "
                        "Downgraded to IRRELEVANT because "
                        "lack of support is not contradiction."
                    )

            return {
                "label": label,

                "reason": reason,

                "confidence": confidence,

                "method": "llm-fallback",

                "result_id": result_id,

                "title": title,

                "url": url,
            }

        except Exception as exc:

            return {
                "label": self.IRRELEVANT,

                "reason": (
                    "LLM fallback failed; evidence "
                    "was conservatively treated as "
                    "irrelevant."
                ),

                "confidence": 0.0,

                "method": (
                    "llm-fallback-error"
                ),

                "error": str(exc),

                "result_id": result_id,

                "title": title,

                "url": url,
            }

    # =========================================================
    # AGGREGATION
    # =========================================================

    def aggregate(
        self,
        classifications
    ):
        """
        Aggregate evidence classifications.

        Rules:

            SUPPORTS > 0
            CONTRADICTS = 0
                -> SUPPORTED

            SUPPORTS = 0
            CONTRADICTS > 0
                -> CONTRADICTED

            SUPPORTS > 0
            CONTRADICTS > 0
                -> CONFLICTED

            SUPPORTS = 0
            CONTRADICTS = 0
                -> INSUFFICIENT
        """

        support = [
            item
            for item in classifications
            if item.get("label")
            == self.SUPPORTS
        ]

        contradiction = [
            item
            for item in classifications
            if item.get("label")
            == self.CONTRADICTS
        ]

        irrelevant = [
            item
            for item in classifications
            if item.get("label")
            == self.IRRELEVANT
        ]

        # =====================================================
        # STATUS
        # =====================================================

        if (
            len(support) > 0
            and len(contradiction) > 0
        ):

            status = self.CONFLICTED

        elif len(support) > 0:

            status = self.SUPPORTED

        elif len(contradiction) > 0:

            status = self.CONTRADICTED

        else:

            status = self.INSUFFICIENT

        return {
            "status": status,

            "supporting_evidence": [
                item.get(
                    "result_id"
                )
                for item in support
            ],

            "contradicting_evidence": [
                item.get(
                    "result_id"
                )
                for item in contradiction
            ],

            "irrelevant_evidence": [
                item.get(
                    "result_id"
                )
                for item in irrelevant
            ],

            "support_count": len(
                support
            ),

            "contradiction_count": len(
                contradiction
            ),

            "irrelevant_count": len(
                irrelevant
            ),
        }

    # =========================================================
    # MAIN VERIFY
    # =========================================================

    def verify(
        self,
        question,
        evidence
    ):
        """
        Main verification entry point.

        Expected evidence structure:

        [
            {
                "query": "...",
                "result": {
                    "success": True,
                    "source": "...",
                    "results": [
                        {
                            "title": "...",
                            "url": "...",
                            "content": "..."
                        }
                    ]
                }
            }
        ]
        """

        claim = self.extract_claim(
            question
        )

        classifications = []

        # =====================================================
        # EVIDENCE SET
        # =====================================================

        for evidence_index, evidence_item in enumerate(
            evidence or [],
            start=1
        ):

            if not isinstance(
                evidence_item,
                dict
            ):
                continue

            result = evidence_item.get(
                "result",
                {}
            )

            if not isinstance(
                result,
                dict
            ):
                continue

            results = result.get(
                "results",
                []
            )

            if not isinstance(
                results,
                list
            ):
                continue

            # =================================================
            # STABLE RESULT ID
            #
            # EVIDENCE_1_R1
            # EVIDENCE_1_R2
            #
            # EVIDENCE_2_R1
            # EVIDENCE_2_R2
            # =================================================

            for result_index, item in enumerate(
                results,
                start=1
            ):

                result_id = (
                    f"EVIDENCE_"
                    f"{evidence_index}"
                    f"_R{result_index}"
                )

                classification = (
                    self.classify_evidence(
                        question,
                        item,
                        result_id
                    )
                )

                classifications.append(
                    classification
                )

        # =====================================================
        # AGGREGATE
        # =====================================================

        aggregate = self.aggregate(
            classifications
        )

        verification = {
            "question": question,

            "status": aggregate[
                "status"
            ],

            "supporting_evidence": aggregate[
                "supporting_evidence"
            ],

            "contradicting_evidence": aggregate[
                "contradicting_evidence"
            ],

            "irrelevant_evidence": aggregate[
                "irrelevant_evidence"
            ],

            "support_count": aggregate[
                "support_count"
            ],

            "contradiction_count": aggregate[
                "contradiction_count"
            ],

            "irrelevant_count": aggregate[
                "irrelevant_count"
            ],

            "classification_count": len(
                classifications
            ),

            "classifications": classifications,

            "claim": claim,
        }

        return verification

    # =========================================================
    # DEBUG PRINT
    # =========================================================

    def print_verification(
        self,
        verification
    ):
        """
        Human-readable verification trace.
        """

        print(
            "\n============================================================"
        )

        print(
            "EVIDENCE VERIFICATION"
        )

        print(
            "============================================================"
        )

        print(
            f"CLAIM: "
            f"{verification.get('claim', '')}"
        )

        print(
            f"STATUS: "
            f"{verification.get('status', '')}"
        )

        print(
            f"SUPPORT: "
            f"{verification.get('support_count', 0)}"
        )

        print(
            f"CONTRADICTION: "
            f"{verification.get('contradiction_count', 0)}"
        )

        print(
            f"IRRELEVANT: "
            f"{verification.get('irrelevant_count', 0)}"
        )

        print()

        print(
            "SUPPORTING:"
        )

        for item in verification.get(
            "classifications",
            []
        ):

            if item.get(
                "label"
            ) != self.SUPPORTS:
                continue

            print(
                f"- {item.get('result_id')}: "
                f"{item.get('reason')}"
            )

        print()

        print(
            "CONTRADICTING:"
        )

        for item in verification.get(
            "classifications",
            []
        ):

            if item.get(
                "label"
            ) != self.CONTRADICTS:
                continue

            print(
                f"- {item.get('result_id')}: "
                f"{item.get('reason')}"
            )

        print(
            "============================================================"
        )