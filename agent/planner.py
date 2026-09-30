import json
import re

import log

from protocol import Action

from problem.models import ProblemType
from problem.reconstruct import ProblemReconstructor
from problem.classifier import ProblemClassifier


LOGGER = log.get(
    "planner"
)


class PlannerResult:

    def __init__(
        self,
        action,
        parameters=None,
        error=None
    ):
        self.action = action
        self.parameters = parameters or {}

        # Set when this result is a degradation rather than a
        # classification, so the caller can say so instead of
        # presenting a fallback as a decision.
        self.error = error


class Planner:

    def __init__(self, llm):

        self.llm = llm

        # =========================================================
        # PROBLEM MODELING LAYER
        # =========================================================

        self.reconstructor = ProblemReconstructor()
        self.classifier = ProblemClassifier()

    # =============================================================
    # MAIN PLANNER
    # =============================================================

    def plan(self, history):

        if not history:
            return PlannerResult(
                Action.ANSWER,
                {}
            )

        question = history[-1]["content"]

        # =========================================================
        # 0. PROBLEM RECONSTRUCTION
        # =========================================================
        #
        # Raw question
        #       ↓
        # ProblemModel
        #
        # Planner không chỉ nhìn raw text nữa.
        # =========================================================

        problem = self.reconstructor.reconstruct(
            question,
            source_type="text"
        )

        # =========================================================
        # 1. PROBLEM CLASSIFICATION
        # =========================================================

        problem = self.classifier.classify(
            problem
        )

        problem_type = (
            problem.primary_problem_type
        )

        # =========================================================
        # 2. MODEL-BASED CALCULATION ROUTING
        # =========================================================

        if problem_type == ProblemType.CALCULATION:

            expression = self.extract_expression(
                question
            )

            # Nếu model đã phát hiện expression,
            # ưu tiên expression từ model.
            calculation_expression = (
                self._get_calculation_expression(
                    problem
                )
            )

            if calculation_expression:

                expression = calculation_expression

            # The classifier types any "... bao nhiêu?" question
            # as CALCULATION, and extract_expression() only strips
            # a few Vietnamese words — so "dân số Việt Nam bao
            # nhiêu" arrived here as the expression
            # 'dân số việt nam', went to CalculatorTool, and the
            # user was shown
            #
            #     Calculator error: invalid syntax (<unknown>, line 1)
            #
            # for a question that should have been searched.
            # Only route to the calculator when what we extracted
            # is actually arithmetic; otherwise fall through.

            if self.is_arithmetic_expression(
                expression
            ):

                return PlannerResult(
                    Action.CALCULATOR,
                    {
                        "expression": expression
                    }
                )

        # =========================================================
        # 3. MODEL-BASED MATHEMATICS
        # =========================================================
        #
        # Hiện tại Action chưa có MATH/SOLVER.
        #
        # Vì vậy KHÔNG giả mạo Mathematics thành Calculator.
        #
        # Mathematics sẽ đi vào COMPLEX để xử lý ở tầng sau.
        # =========================================================

        if problem_type == ProblemType.MATHEMATICS:

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 4. MODEL-BASED DEBUG
        # =========================================================

        if problem_type == ProblemType.DEBUG:

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 5. MODEL-BASED CAUSAL REASONING
        # =========================================================

        if problem_type == ProblemType.CAUSAL:

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 6. MODEL-BASED OPTIMIZATION
        # =========================================================

        if problem_type == ProblemType.OPTIMIZATION:

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 7. MODEL-BASED DECISION
        # =========================================================

        if problem_type == ProblemType.DECISION:

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 8. MODEL-BASED DESIGN
        # =========================================================

        if problem_type == ProblemType.DESIGN:

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 9. MODEL-BASED FACT LOOKUP
        # =========================================================
        #
        # Chỉ route FACT_LOOKUP sang SEARCH khi ProblemModel
        # thực sự yêu cầu external evidence.
        #
        # Phải chạy TRƯỚC các fallback theo keyword bên dưới:
        # một câu fact_lookup có chứa keyword "complex"
        # (locking, transaction, concurrency, ...) nếu không
        # sẽ bị is_complex_reasoning() chiếm và trả lời bằng
        # model memory thay vì đi lấy evidence.
        # =========================================================

        if problem_type == ProblemType.FACT_LOOKUP:

            if problem.evidence_requirements:

                return PlannerResult(
                    Action.SEARCH,
                    {
                        "query": question
                    }
                )

        # =========================================================
        # 10. DETERMINISTIC FILE ROUTING
        # =========================================================
        #
        # Action.FILE previously appeared nowhere in plan() — it
        # could only be produced if the LLM fallback happened to
        # emit {"action": "file"}. Every file-shaped question
        # ("đọc data/example.txt") classified as UNKNOWN, matched
        # no deterministic rule, and fell through to ANSWER, so
        # FileTool was never called and the model answered from
        # memory about a file it had not opened.
        # =========================================================

        file_path = self.extract_file_path(
            question
        )

        if file_path:

            return PlannerResult(
                Action.FILE,
                {
                    "path": file_path
                }
            )

        # =========================================================
        # 11. DETERMINISTIC CALCULATOR FALLBACK
        # =========================================================
        #
        # Giữ compatibility với routing cũ.
        # =========================================================

        if self.is_calculation(question):

            expression = self.extract_expression(
                question
            )

            return PlannerResult(
                Action.CALCULATOR,
                {
                    "expression": expression
                }
            )

        # =========================================================
        # 12. DETERMINISTIC SEARCH ROUTING
        # =========================================================

        if self.need_search(question):

            return PlannerResult(
                Action.SEARCH,
                {
                    "query": question
                }
            )

        # =========================================================
        # 13. DETERMINISTIC COMPLEX ROUTING
        # =========================================================

        if self.is_complex_reasoning(question):

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 14. LLM PLANNER FALLBACK
        # =========================================================

        messages = [
            {
                "role": "system",
                "content": """
Bạn là BCOS Planner.

Nhiệm vụ:
Chọn đúng một action phù hợp nhất với câu hỏi.

==================================================
ACTION
==================================================

1. calculator

Dùng cho phép tính số học đơn giản.

Schema:

{
  "action": "calculator",
  "parameters": {
    "expression": "1 + 1"
  }
}


2. search

Dùng khi cần:

- thông tin bên ngoài
- dữ liệu mới
- thông tin hiện tại
- thông tin thay đổi theo thời gian
- giá
- tin tức
- sự kiện
- kiểm chứng thông tin

Schema:

{
  "action": "search",
  "parameters": {
    "query": "..."
  }
}


3. file

Dùng khi cần đọc file trong thư mục data.

Schema:

{
  "action": "file",
  "parameters": {
    "path": "data/example.txt"
  }
}


4. complex

Dùng khi câu hỏi yêu cầu:

- phân tích sâu
- so sánh nhiều phương án
- đánh giá trade-off
- phân tích nguyên nhân
- phân tích root cause
- đánh giá rủi ro
- thiết kế kiến trúc
- thiết kế hệ thống
- chiến lược
- ra quyết định
- lựa chọn giữa nhiều phương án
- reasoning nhiều bước
- concurrent systems
- transaction
- database concurrency
- locking
- performance analysis
- technical architecture
- debugging
- mathematics nhiều bước
- optimization

Schema:

{
  "action": "complex",
  "parameters": {}
}


5. answer

Dùng cho câu hỏi đơn giản có thể trả lời
bằng kiến thức ổn định.

Schema:

{
  "action": "answer",
  "parameters": {}
}


==================================================
QUY TẮC
==================================================

- Không trả lời câu hỏi.
- Chỉ output JSON.
- calculator CHỈ dùng parameter "expression".
- search CHỈ dùng parameter "query".
- file CHỈ dùng parameter "path".
- complex dùng parameters {}.
- answer dùng parameters {}.
- Không thêm markdown.
- Không thêm giải thích.
"""
            }
        ]

        messages.extend(history)

        try:

            response = self.llm.chat(
                messages
            )

            return self.parse(
                response
            )

        except Exception as exc:

            # Previously silent: no print, no trace, no log. A
            # fault in llm.chat() or parse() degraded every
            # question to ANSWER — the model answering a live-fact
            # question from memory — and nothing said so. Same
            # defect class as the reconstruct() TypeError that
            # surfaced only as "Qwen cannot search".

            LOGGER.warning(
                "LLM planner call failed; "
                "falling back to ANSWER",
                exc_info=True
            )

            return PlannerResult(
                Action.ANSWER,
                {},
                error=(
                    "LLM planner không dùng được: "
                    f"{exc}"
                )
            )

    # =============================================================
    # PROBLEM MODEL HELPERS
    # =============================================================

    def _get_calculation_expression(
        self,
        problem
    ):
        """
        Extract calculation expression from ProblemModel.

        reconstruct.py currently creates a relation named:
            calculation_expression

        with expression stored in relation.expression.
        """

        for relation in problem.relations:

            if relation.name == "calculation_expression":

                if relation.expression:

                    return str(
                        relation.expression
                    ).strip()

        return ""

    # =============================================================
    # CALCULATOR
    # =============================================================

    # Data files FileTool can serve. An allowlist, not a
    # blocklist: "sqlite.org", "python 3.11.15" and a bare URL
    # must not look like a file, or web questions get stolen.

    FILE_EXTENSIONS = (
        "txt",
        "json",
        "md",
        "csv",
        "tsv",
        "log",
        "yaml",
        "yml",
        "ini",
        "xml",
    )


    FILE_PATH_PATTERN = re.compile(
        r"(?<![\w./-])"
        r"([\w.\-/]+\.(?:"
        + "|".join(FILE_EXTENSIONS)
        + r"))"
        r"(?![\w/])",
        re.IGNORECASE,
    )


    def extract_file_path(
        self,
        question
    ):
        """
        Path of a data file the user is asking BCOS to read.

        Returns None when the question names no such file, so the
        caller falls through to the remaining routing.
        """

        text = str(
            question or ""
        )

        if not text:
            return None

        # A URL is a web question, not a file request.
        lowered = text.lower()

        for marker in (
            "http://",
            "https://",
            "www.",
        ):

            if marker in lowered:
                return None

        match = self.FILE_PATH_PATTERN.search(
            text
        )

        if not match:
            return None

        return match.group(
            1
        )



    # Characters a pure arithmetic expression may contain.

    ARITHMETIC_CHARS = set(
        "0123456789+-*/().%, \t"
    )


    def is_arithmetic_expression(
        self,
        expression
    ):
        """
        True only for something CalculatorTool can evaluate.

        Requires at least one digit, at least one operator, and
        nothing outside ARITHMETIC_CHARS — so a leftover
        Vietnamese phrase is rejected instead of being handed to
        the AST evaluator.
        """

        text = str(
            expression or ""
        ).strip()

        if not text:
            return False

        if not any(
            char.isdigit()
            for char in text
        ):
            return False

        if any(
            char not in self.ARITHMETIC_CHARS
            for char in text
        ):
            return False

        return any(
            operator in text
            for operator in "+-*/%"
        )



    def is_calculation(
        self,
        question
    ):

        q = question.lower()

        math_chars = set(
            "0123456789+-*/().% "
        )

        # Phải có ít nhất một chữ số
        if not any(
            c.isdigit()
            for c in q
        ):
            return False

        # Loại bỏ các từ thường gặp
        # trong câu hỏi tính toán.
        for word in [
            "bằng bao nhiêu",
            "tính",
            "kết quả là",
            "kết quả",
            "bao nhiêu"
        ]:

            q = q.replace(
                word,
                ""
            )

        q = q.strip()

        if not q:
            return False

        return all(
            c in math_chars
            for c in q
        )

    # =============================================================

    # Longest run of arithmetic characters in a sentence.

    ARITHMETIC_RUN_PATTERN = re.compile(
        r"[0-9][0-9+\-*/().%,\s]*[0-9)]"
    )


    def extract_expression(
        self,
        question
    ):
        """
        Arithmetic expression contained in the question.

        Stripping a fixed word list left Vietnamese fragments
        behind ("kết quả của 25 * 4 là bao nhiêu" -> 'của 25 * 4
        là'), which the caller then had to reject. Pull the
        arithmetic substring out instead, and keep the stripped
        text as a fallback for inputs the pattern misses.
        """

        q = question.lower()

        for word in [
            "bằng bao nhiêu",
            "tính",
            "kết quả là",
            "kết quả",
            "bao nhiêu"
        ]:

            q = q.replace(
                word,
                ""
            )

        stripped = q.strip()

        if self.is_arithmetic_expression(
            stripped
        ):
            return stripped

        # Longest arithmetic run wins: "25 * 4" beats "25".
        best = ""

        for match in self.ARITHMETIC_RUN_PATTERN.finditer(
            question
        ):

            candidate = match.group(
                0
            ).strip()

            if not self.is_arithmetic_expression(
                candidate
            ):
                continue

            if len(candidate) > len(best):
                best = candidate

        if best:
            return best

        return stripped

    # =============================================================
    # SEARCH
    # =============================================================

    def need_search(
        self,
        question
    ):

        q = question.lower()

        keywords = [

            # -----------------------------------------------------
            # Years / current information
            # -----------------------------------------------------

            "2024",
            "2025",
            "2026",
            "2027",
            "2028",

            "hiện tại",
            "hien tai",

            "hôm nay",
            "hom nay",

            "mới nhất",
            "moi nhat",

            "latest",
            "update",
            "updated",

            # -----------------------------------------------------
            # Politics / public affairs
            # -----------------------------------------------------

            "tổng thống",
            "tong thong",

            "thủ tướng",
            "thu tuong",

            "bầu cử",
            "bau cu",

            "chính phủ",
            "chinh phu",

            # -----------------------------------------------------
            # Market / price
            # -----------------------------------------------------

            "giá",
            "gia",

            "cổ phiếu",
            "co phieu",

            "bitcoin",

            "vàng",
            "vang",

            # -----------------------------------------------------
            # News / events
            # -----------------------------------------------------

            "tin tức",
            "tin tuc",

            "sự kiện",
            "su kien",

            "news",

            # -----------------------------------------------------
            # Explicit web lookup
            # -----------------------------------------------------

            "tìm trên mạng",
            "tim tren mang",

            "tra cứu",
            "tra cuu",

            "search web",
            "web search"
        ]

        return any(
            word in q
            for word in keywords
        )

    # =============================================================
    # COMPLEX REASONING
    # =============================================================

    def is_complex_reasoning(
        self,
        question
    ):

        q = question.lower()

        # =========================================================
        # 1. EXPLICIT REASONING SIGNALS
        # =========================================================

        reasoning_keywords = [

            # Analysis
            "phân tích",
            "phan tich",

            # Comparison
            "so sánh",
            "so sanh",

            "versus",

            # Pros / cons
            "ưu nhược điểm",
            "uu nhuoc diem",

            "ưu điểm và nhược điểm",
            "uu diem va nhuoc diem",

            "ưu điểm",
            "uu diem",

            "nhược điểm",
            "nhuoc diem",

            # Evaluation
            "đánh giá",
            "danh gia",

            "đánh giá xem",
            "danh gia xem",

            # Trade-off
            "trade-off",
            "tradeoff",

            # Architecture / design
            "kiến trúc",
            "kien truc",

            "thiết kế",
            "thiet ke",

            # Strategy
            "chiến lược",
            "chien luoc",

            # Cause / root cause
            "tại sao",
            "tai sao",

            "nguyên nhân",
            "nguyen nhan",

            "root cause",

            # Risk
            "rủi ro",
            "rui ro",

            # Decision
            "quyết định",
            "quyet dinh",

            "nên chọn",
            "nen chon",

            "nên dùng",
            "nen dung",

            "chọn cái nào",
            "chon cai nao",

            "cái nào phù hợp",
            "cai nao phu hop",

            "phù hợp hơn",
            "phu hop hon",

            "nên sử dụng",
            "nen su dung",

            # Planning
            "kế hoạch",
            "ke hoach",

            # Deep reasoning
            "phân tích sâu",
            "phan tich sau",

            "phân tích chi tiết",
            "phan tich chi tiet",

            # System reasoning
            "đồng thời",
            "dong thoi",

            "nhiều bước",
            "nhieu buoc",

            "concurrent",
            "concurrency",

            "concurrent writes",
            "concurrent write",

            # Optimization
            "tối ưu",
            "toi uu",

            "tối ưu hóa",
            "toi uu hoa",

            # Alternatives
            "phương án",
            "phuong an",

            "lựa chọn",
            "lua chon",

            "alternative",
            "alternatives"
        ]

        if any(
            keyword in q
            for keyword in reasoning_keywords
        ):
            return True

        # =========================================================
        # 2. COMPARISON SIGNAL
        # =========================================================

        words = (
            q
            .replace(",", " ")
            .replace("?", " ")
            .replace("!", " ")
            .split()
        )

        has_vs = (
            "vs" in words
            or "versus" in words
        )

        has_comparison_phrase = (
            "so sánh" in q
            or "so sanh" in q
        )

        # =========================================================
        # 3. TECHNICAL CONTEXT
        # =========================================================

        technical_keywords = [

            # Database
            "database",
            "db",
            "postgresql",
            "postgres",
            "sqlite",
            "mysql",
            "mariadb",

            # Transactions
            "transaction",
            "transactions",

            "giao dịch",
            "giao dich",

            # Concurrency
            "concurrent",
            "concurrency",

            "concurrent writes",
            "concurrent write",

            # Locking
            "locking",
            "lock",

            "row lock",
            "table lock",

            # Isolation
            "isolation",
            "isolation level",

            "transaction isolation",

            # Savepoint
            "savepoint",

            # Reliability
            "deadlock",
            "race condition",

            # Performance
            "throughput",
            "latency",
            "tps",
            "performance",

            "hiệu năng",
            "hieu nang",

            "benchmark",

            # Domain
            "warehouse",
            "inventory",
            "stock",

            # Architecture
            "backend",
            "api",
            "microservice",
            "distributed",
            "system architecture"
        ]

        has_technical_context = any(
            keyword in q
            for keyword in technical_keywords
        )

        # =========================================================
        # 4. TECHNICAL COMPARISON
        # =========================================================

        if (
            (has_vs or has_comparison_phrase)
            and has_technical_context
        ):
            return True

        # =========================================================
        # 5. DATABASE / TECHNICAL FACT QUESTION
        # =========================================================

        database_context_keywords = [

            "postgresql",
            "postgres",

            "sqlite",

            "database",
            "db",

            "transaction",
            "transactions",

            "savepoint",

            "locking",
            "lock",

            "concurrency",
            "concurrent"
        ]

        has_database_context = any(
            keyword in q
            for keyword in database_context_keywords
        )

        technical_question_keywords = [

            "có hỗ trợ",
            "co ho tro",

            "hỗ trợ",
            "ho tro",

            "support",

            "có dùng được",
            "co dung duoc",

            "có thể",
            "co the",

            "có hoạt động",
            "co hoat dong",

            "có cho phép",
            "co cho phep",

            "có khả năng",
            "co kha nang",

            "có tương thích",
            "co tuong thich",

            "có đáp ứng",
            "co dap ung",

            "có chịu được",
            "co chiu duoc"
        ]

        has_technical_question = any(
            keyword in q
            for keyword in technical_question_keywords
        )

        if (
            has_database_context
            and has_technical_question
        ):
            return True

        # =========================================================
        # 6. PERFORMANCE / CONCURRENCY QUESTIONS
        # =========================================================

        performance_keywords = [

            "nhanh hơn",
            "nhanh hon",

            "chậm hơn",
            "cham hon",

            "tốc độ",
            "toc do",

            "hiệu năng",
            "hieu nang",

            "performance",

            "throughput",
            "latency",

            "tps",

            "chịu tải",
            "chiu tai",

            "load",

            "scale",
            "scalability",

            "khả năng mở rộng",
            "kha nang mo rong",

            "concurrent",

            "concurrency",

            "concurrent writes",

            "nhiều người dùng",
            "nhieu nguoi dung",

            "nhiều request",
            "nhieu request"
        ]

        has_performance_signal = any(
            keyword in q
            for keyword in performance_keywords
        )

        if has_performance_signal:
            return True

        # =========================================================
        # 7. MULTI-OPTION DECISION
        # =========================================================

        decision_keywords = [

            "nên chọn",
            "nen chon",

            "nên dùng",
            "nen dung",

            "chọn cái nào",
            "chon cai nao",

            "cái nào tốt hơn",
            "cai nao tot hon",

            "cái nào phù hợp",
            "cai nao phu hop",

            "phương án nào",
            "phuong an nao",

            "lựa chọn nào",
            "lua chon nao",

            "nên sử dụng",
            "nen su dung"
        ]

        has_decision_signal = any(
            keyword in q
            for keyword in decision_keywords
        )

        if has_decision_signal:
            return True

        return False

    # =============================================================
    # PARSE LLM PLANNER OUTPUT
    # =============================================================

    def parse(
        self,
        text
    ):

        try:

            if not isinstance(
                text,
                str
            ):
                raise ValueError(
                    "Planner response is not text"
                )

            start = text.find("{")
            end = text.rfind("}") + 1

            if (
                start < 0
                or end <= start
            ):
                raise ValueError(
                    "Planner did not return JSON"
                )

            data = json.loads(
                text[start:end]
            )

            if not isinstance(
                data,
                dict
            ):
                raise ValueError(
                    "Planner JSON is not an object"
                )

            action_value = data.get(
                "action",
                "answer"
            )

            action = Action(
                action_value
            )

            parameters = data.get(
                "parameters",
                {}
            )

            if not isinstance(
                parameters,
                dict
            ):
                parameters = {}

            # =====================================================
            # Normalize parameters
            # =====================================================

            if action == Action.CALCULATOR:

                parameters = {
                    "expression": str(
                        parameters.get(
                            "expression",
                            ""
                        )
                    )
                }

            elif action == Action.SEARCH:

                parameters = {
                    "query": str(
                        parameters.get(
                            "query",
                            ""
                        )
                    )
                }

            elif action == Action.FILE:

                parameters = {
                    "path": str(
                        parameters.get(
                            "path",
                            ""
                        )
                    )
                }

            elif action == Action.COMPLEX:

                parameters = {}

            elif action == Action.ANSWER:

                parameters = {}

            return PlannerResult(
                action,
                parameters
            )

        except Exception as exc:

            LOGGER.warning(
                "could not parse planner response; "
                "falling back to ANSWER",
                exc_info=True
            )

            return PlannerResult(
                Action.ANSWER,
                {},
                error=(
                    "Không đọc được kế hoạch từ LLM: "
                    f"{exc}"
                )
            )