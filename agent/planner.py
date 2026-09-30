import json

from protocol import Action

from problem.models import ProblemType
from problem.reconstruct import ProblemReconstructor
from problem.classifier import ProblemClassifier


class PlannerResult:

    def __init__(
        self,
        action,
        parameters=None
    ):
        self.action = action
        self.parameters = parameters or {}


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

            if expression:

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
        # 10. DETERMINISTIC CALCULATOR FALLBACK
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
        # 11. DETERMINISTIC SEARCH ROUTING
        # =========================================================

        if self.need_search(question):

            return PlannerResult(
                Action.SEARCH,
                {
                    "query": question
                }
            )

        # =========================================================
        # 12. DETERMINISTIC COMPLEX ROUTING
        # =========================================================

        if self.is_complex_reasoning(question):

            return PlannerResult(
                Action.COMPLEX,
                {}
            )

        # =========================================================
        # 13. LLM PLANNER FALLBACK
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

        except Exception:

            return PlannerResult(
                Action.ANSWER,
                {}
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

    def extract_expression(
        self,
        question
    ):

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

        return q.strip()

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

        except Exception:

            return PlannerResult(
                Action.ANSWER,
                {}
            )