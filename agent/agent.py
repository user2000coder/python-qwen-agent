"""
BCOS Agent Core

Architecture
------------

User
  ↓
Understand
  ↓
Planner
  ↓
Task Lock
  │
  ├── ANSWER
  │      └── Direct LLM
  │
  ├── CALCULATOR
  │      └── Deterministic Tool
  │
  ├── SEARCH
  │      └── Search
  │             ↓
  │        Evidence Verifier
  │             ↓
  │        Deterministic Decision
  │             ↓
  │        Final Answer
  │
  ├── FILE
  │      └── File
  │             ↓
  │        Evidence Verifier
  │             ↓
  │        Deterministic Decision
  │             ↓
  │        Final Answer
  │
  └── COMPLEX
         └── Evidence Decomposition
                ↓
            Multiple Searches
                ↓
          Evidence Inspection
                ↓
          Focused Council
                ↓
               Judge

Important design rule
---------------------

EvidenceVerifier is authoritative about whether retrieved
evidence supports or contradicts a claim.

Qwen is NOT allowed to override:

    SUPPORTED
    CONTRADICTED

Qwen is only used for:

    - direct ANSWER tasks
    - ambiguous evidence classification
    - conflict synthesis
    - insufficient-evidence wording

Observable trace records:

    - task classification
    - tool routing
    - evidence acquisition
    - verification result
    - final decision

It does NOT expose private model chain-of-thought.
"""

import json

from llm import LLM
from planner import Planner
from memory import Memory
from protocol import Action
from council import Council
from evidence_verifier import EvidenceVerifier

from tools.search import SearchTool
from tools.calculator import CalculatorTool
from tools.file import FileTool


class Agent:

    # =========================================================
    # INIT
    # =========================================================

    def __init__(self):

        self.llm = LLM()

        self.memory = Memory()

        self.planner = Planner(
            self.llm
        )

        self.council = Council(
            self.llm
        )

        # -----------------------------------------------------
        # Evidence verifier
        # -----------------------------------------------------

        self.evidence_verifier = EvidenceVerifier(
            self.llm
        )

        # -----------------------------------------------------
        # Tools
        # -----------------------------------------------------

        self.tools = {
            Action.SEARCH: SearchTool(),
            Action.CALCULATOR: CalculatorTool(),
            Action.FILE: FileTool(),
        }

        self.tool_required_parameters = {
            Action.SEARCH: ["query"],
            Action.CALCULATOR: ["expression"],
            Action.FILE: ["path"],
        }

        # -----------------------------------------------------
        # Observable trace
        # -----------------------------------------------------

        self.trace_enabled = True

        self.trace_events = []

    # =========================================================
    # TRACE
    # =========================================================

    def trace(
        self,
        step,
        phase,
        message,
        data=None
    ):
        """
        Record observable processing state.

        This is not private chain-of-thought.
        """

        event = {
            "step": step,
            "phase": phase,
            "message": message,
        }

        if data is not None:
            event["data"] = data

        self.trace_events.append(
            event
        )

        if not self.trace_enabled:
            return

        print(
            "\n┌──────────────────────────────────────────────┐",
            flush=True
        )

        print(
            f"│ [{step:02d}] {phase}",
            flush=True
        )

        print(
            "├──────────────────────────────────────────────┤",
            flush=True
        )

        for line in str(
            message
        ).splitlines():

            print(
                f"│ {line}",
                flush=True
            )

        if data is not None:

            print(
                "│",
                flush=True
            )

            if isinstance(
                data,
                (dict, list)
            ):

                text = json.dumps(
                    data,
                    ensure_ascii=False,
                    indent=2
                )

            else:

                text = str(
                    data
                )

            for line in text.splitlines():

                print(
                    f"│ {line}",
                    flush=True
                )

        print(
            "└──────────────────────────────────────────────┘",
            flush=True
        )

    def reset_trace(self):

        self.trace_events = []

    def get_trace(self):

        return list(
            self.trace_events
        )

    # =========================================================
    # ASK
    # =========================================================

    def ask(
        self,
        question
    ):
        """
        Main BCOS request pipeline.
        """

        self.reset_trace()

        # -----------------------------------------------------
        # MEMORY
        # -----------------------------------------------------

        self.memory.add(
            "user",
            question
        )

        history = self.memory.messages()

        evidence = []

        # =====================================================
        # 01 — UNDERSTAND
        # =====================================================

        self.trace(
            1,
            "UNDERSTAND",
            "Xác định câu hỏi đầu vào.",
            {
                "question": question
            }
        )

        # =====================================================
        # 02 — CLASSIFY
        # =====================================================

        print(
            "\n🧠 Planner: phân tích...",
            flush=True
        )

        call = self.planner.plan(
            history
        )

        self.trace(
            2,
            "CLASSIFY",
            "Planner đã phân loại task.",
            {
                "action": call.action.value,
                "parameters": call.parameters
            }
        )

        print(
            "🧠 Action:",
            call.action.value,
            flush=True
        )

        # =====================================================
        # ANSWER
        # =====================================================

        if call.action == Action.ANSWER:

            return self._handle_direct_answer(
                question
            )

        # =====================================================
        # COMPLEX
        # =====================================================

        if call.action == Action.COMPLEX:

            return self._handle_complex(
                question
            )

        # =====================================================
        # TOOL
        # =====================================================

        if call.action not in self.tools:

            self.trace(
                3,
                "ERROR",
                "Unsupported action.",
                {
                    "action": str(
                        call.action
                    )
                }
            )

            raise ValueError(
                f"Unsupported action: "
                f"{call.action}"
            )

        return self._handle_tool(
            question,
            call.action,
            call.parameters
        )

    # =========================================================
    # DIRECT ANSWER
    # =========================================================

    def _handle_direct_answer(
        self,
        question
    ):

        self.trace(
            3,
            "TASK LOCK",
            "Task được route sang ANSWER → Direct LLM."
        )

        print(
            "💬 Direct answer...",
            flush=True
        )

        answer = self.llm.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Trả lời câu hỏi của người dùng "
                        "một cách chính xác và trực tiếp. "
                        "Nếu không chắc chắn, hãy nói rõ. "
                        "Không bịa dữ liệu."
                    )
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
        )

        self.trace(
            4,
            "FINAL ANSWER",
            "Direct LLM đã tạo câu trả lời."
        )

        yield answer

        self.memory.add(
            "assistant",
            answer
        )

    # =========================================================
    # TOOL HANDLER
    # =========================================================

    def _handle_tool(
        self,
        question,
        action,
        parameters
    ):

        self.trace(
            3,
            "TOOL ROUTING",
            "Task được route sang deterministic tool.",
            {
                "action": action.value,
                "parameters": parameters
            }
        )

        print(
            "🌐 Tool đang chạy...",
            flush=True
        )

        try:

            result = self.execute_tool(
                action,
                parameters
            )

        except Exception as exc:

            answer = (
                f"Tool execution failed: {exc}"
            )

            self.trace(
                4,
                "TOOL ERROR",
                answer
            )

            print(
                f"❌ {answer}",
                flush=True
            )

            yield answer

            self.memory.add(
                "assistant",
                answer
            )

            return

        self.trace(
            4,
            "TOOL RESULT",
            "Tool execution hoàn tất."
        )

        print(
            "✅ Tool hoàn tất",
            flush=True
        )

        # -----------------------------------------------------
        # CALCULATOR
        # -----------------------------------------------------

        if action == Action.CALCULATOR:

            answer = (
                self.format_calculator_result(
                    result
                )
            )

            self.trace(
                5,
                "FINAL ANSWER",
                "Calculator result được trả trực tiếp."
            )

            yield answer

            self.memory.add(
                "assistant",
                answer
            )

            return

        # -----------------------------------------------------
        # SEARCH / FILE
        # -----------------------------------------------------

        evidence = [
            {
                "query": parameters.get(
                    "query",
                    question
                ),
                "result": result
            }
        ]

        answer = self.synthesize_evidence(
            question,
            evidence
        )

        self.trace(
            7,
            "FINAL ANSWER",
            "Evidence synthesis hoàn tất."
        )

        yield answer

        self.memory.add(
            "assistant",
            answer
        )

    # =========================================================
    # EVIDENCE SYNTHESIS
    # =========================================================

    def synthesize_evidence(
        self,
        question,
        evidence
    ):
        """
        Evidence boundary.

        IMPORTANT:

        SUPPORTED
            → deterministic answer whenever possible

        CONTRADICTED
            → deterministic contradiction answer

        CONFLICTED
            → Qwen may summarize conflict

        INSUFFICIENT
            → Qwen may explain insufficiency

        Qwen must NEVER turn:

            SUPPORTED → INSUFFICIENT

        or:

            CONTRADICTED → SUPPORTED
        """

        print(
            "\n🤖 Qwen đang tổng hợp evidence...",
            flush=True
        )

        self.trace(
            5,
            "EVIDENCE SYNTHESIS",
            "Evidence được chuyển vào EvidenceVerifier."
        )

        # =====================================================
        # VERIFY
        # =====================================================

        verification = (
            self.evidence_verifier.verify(
                question,
                evidence
            )
        )

        status = verification.get(
            "status",
            self.evidence_verifier.INSUFFICIENT
        )

        classifications = verification.get(
            "classifications",
            []
        )

        # =====================================================
        # PRINT VERIFICATION
        # =====================================================

        if hasattr(
            self.evidence_verifier,
            "print_verification"
        ):

            self.evidence_verifier.print_verification(
                verification
            )

        # =====================================================
        # TRACE VERIFICATION
        # =====================================================

        self.trace(
            6,
            "EVIDENCE VERIFICATION",
            "EvidenceVerifier đã xác định trạng thái evidence.",
            {
                "claim": verification.get(
                    "claim",
                    ""
                ),
                "status": status,
                "support_count": verification.get(
                    "support_count",
                    0
                ),
                "contradiction_count": verification.get(
                    "contradiction_count",
                    0
                ),
                "supporting_evidence": verification.get(
                    "supporting_evidence",
                    []
                ),
                "contradicting_evidence": verification.get(
                    "contradicting_evidence",
                    []
                )
            }
        )

        print(
            "\n============================================================",
            flush=True
        )

        print(
            "VERIFICATION RESULT",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        print(
            json.dumps(
                verification,
                ensure_ascii=False,
                indent=2
            ),
            flush=True
        )

        # =====================================================
        # SUPPORTED
        # =====================================================

        if status == self.evidence_verifier.SUPPORTED:

            answer = (
                self._answer_supported(
                    question,
                    verification
                )
            )

            self.trace(
                7,
                "ANSWER GENERATION",
                (
                    "Verification = SUPPORTED → "
                    "deterministic answer. "
                    "Qwen không được phép phủ định verification."
                ),
                {
                    "status": status
                }
            )

            return answer

        # =====================================================
        # CONTRADICTED
        # =====================================================

        if status == self.evidence_verifier.CONTRADICTED:

            answer = (
                self._answer_contradicted(
                    question,
                    verification
                )
            )

            self.trace(
                7,
                "ANSWER GENERATION",
                (
                    "Verification = CONTRADICTED → "
                    "trả kết quả theo evidence."
                ),
                {
                    "status": status
                }
            )

            return answer

        # =====================================================
        # CONFLICTED
        # =====================================================

        if status == self.evidence_verifier.CONFLICTED:

            answer = (
                self._answer_conflicted(
                    question,
                    verification
                )
            )

            self.trace(
                7,
                "ANSWER GENERATION",
                (
                    "Verification = CONFLICTED → "
                    "Qwen tổng hợp mâu thuẫn."
                ),
                {
                    "status": status
                }
            )

            return answer

        # =====================================================
        # INSUFFICIENT
        # =====================================================

        answer = (
            self._answer_insufficient(
                question,
                verification
            )
        )

        self.trace(
            7,
            "ANSWER GENERATION",
            (
                "Verification = INSUFFICIENT → "
                "không bịa; Qwen chỉ diễn đạt "
                "giới hạn evidence."
            ),
            {
                "status": status
            }
        )

        return answer

    # =========================================================
    # SUPPORTED ANSWER
    # =========================================================

    def _answer_supported(
        self,
        question,
        verification
    ):
        """
        Produce answer from verified evidence.

        No Qwen call is made for a straightforward verified
        entity answer.
        """

        classifications = verification.get(
            "classifications",
            []
        )

        supporting = []

        for item in classifications:

            if not isinstance(
                item,
                dict
            ):
                continue

            if (
                item.get("label")
                != self.evidence_verifier.SUPPORTS
            ):
                continue

            supporting.append(
                item
            )

        # -----------------------------------------------------
        # Extract verified candidate names
        # -----------------------------------------------------

        candidates = []

        for item in supporting:

            names = item.get(
                "candidate_names",
                []
            )

            if not isinstance(
                names,
                list
            ):
                continue

            for name in names:

                name = str(
                    name
                ).strip()

                if not name:
                    continue

                # Reject obvious garbage candidates.
                if len(name) > 100:
                    continue

                if name not in candidates:

                    candidates.append(
                        name
                    )

        # -----------------------------------------------------
        # President question
        # -----------------------------------------------------

        signals = {}

        if hasattr(
            self.evidence_verifier,
            "_question_signals"
        ):

            signals = (
                self.evidence_verifier
                ._question_signals(
                    question
                )
            )

        if (
            signals.get(
                "asks_president",
                False
            )
            and candidates
        ):

            if len(candidates) == 1:

                return (
                    "Tổng thống Mỹ năm 2026 là "
                    f"{candidates[0]}."
                )

            return (
                "Evidence được xác nhận cho thấy "
                "các tên sau liên quan đến chức "
                "Tổng thống Mỹ: "
                + ", ".join(candidates)
                + "."
            )

        # -----------------------------------------------------
        # Generic verified answer
        # -----------------------------------------------------

        if candidates:

            if len(candidates) == 1:

                return (
                    f"Evidence xác nhận: "
                    f"{candidates[0]}."
                )

            return (
                "Evidence xác nhận các thực thể sau: "
                + ", ".join(candidates)
                + "."
            )

        # -----------------------------------------------------
        # Verified evidence but no entity extraction
        #
        # Do NOT let Qwen reverse SUPPORTED.
        #
        # The verifier already concluded SUPPORTED, so the
        # answer is built deterministically from the supporting
        # evidence instead of being handed back to the model.
        # -----------------------------------------------------

        sources = []

        for item in supporting:

            title = str(
                item.get(
                    "title",
                    ""
                )
            ).strip()

            url = str(
                item.get(
                    "url",
                    ""
                )
            ).strip()

            if not title and not url:
                continue

            line = title or url

            if title and url:
                line = f"{title} — {url}"

            if line not in sources:
                sources.append(
                    line
                )

        evidence_block = "\n".join(
            f"- {line}"
            for line in sources[:5]
        )

        # A polar question ("X có hỗ trợ Y không?") is answered
        # affirmatively: SUPPORTED means the evidence confirms
        # the claim the question asks about.
        if self.is_polar_question(
            question
        ):

            answer = (
                "Có — evidence xác nhận điều này."
            )

        else:

            answer = (
                "Evidence xác nhận nội dung câu hỏi."
            )

        if not evidence_block:
            return answer

        return (
            answer
            + "\n\nBẰNG CHỨNG:\n"
            + evidence_block
        )

    # =========================================================
    # POLAR QUESTION DETECTION
    # =========================================================

    def is_polar_question(
        self,
        question
    ):
        """
        Deterministic yes/no (polar) question detection.

        Vietnamese polar questions are marked by trailing
        particles ("... không?", "... chưa?", "có phải ...").
        English ones by a leading auxiliary verb.

        Conservative on purpose: a false negative only costs a
        slightly weaker wording, a false positive would assert
        "Có" for a question that was never yes/no.
        """

        text = str(
            question or ""
        ).strip().lower()

        if not text:
            return False

        text = text.rstrip(
            "?!. "
        )

        if not text:
            return False

        vietnamese_markers = [
            "khong",
            "không",
            "chưa",
            "chua",
            "phải không",
            "phai khong",
        ]

        for marker in vietnamese_markers:

            if text.endswith(
                marker
            ):
                return True

        if text.startswith(
            "có phải"
        ) or text.startswith(
            "co phai"
        ):
            return True

        english_auxiliaries = [
            "does",
            "do",
            "did",
            "is",
            "are",
            "was",
            "were",
            "can",
            "could",
            "will",
            "would",
            "has",
            "have",
            "should",
        ]

        first_word = text.split()[0]

        return first_word in english_auxiliaries

    # =========================================================
    # CONTRADICTED ANSWER
    # =========================================================

    def _answer_contradicted(
        self,
        question,
        verification
    ):
        """
        Deterministic contradiction response.
        """

        classifications = verification.get(
            "classifications",
            []
        )

        contradictions = []

        for item in classifications:

            if not isinstance(
                item,
                dict
            ):
                continue

            if (
                item.get("label")
                != self.evidence_verifier.CONTRADICTS
            ):
                continue

            contradictions.append(
                item
            )

        if not contradictions:

            return (
                "Evidence hiện có phản bác câu hỏi, "
                "nhưng chưa có đủ thông tin để mô tả "
                "chi tiết."
            )

        reasons = []

        for item in contradictions:

            reason = str(
                item.get(
                    "reason",
                    ""
                )
            ).strip()

            if reason and reason not in reasons:

                reasons.append(
                    reason
                )

        if reasons:

            return (
                "Evidence hiện có phản bác câu hỏi. "
                + " ".join(
                    reasons[:2]
                )
            )

        return (
            "Evidence hiện có phản bác câu hỏi."
        )

    # =========================================================
    # CONFLICTED ANSWER
    # =========================================================

    def _answer_conflicted(
        self,
        question,
        verification
    ):
        """
        Qwen may summarize conflicting evidence.

        However, the verification status itself remains
        authoritative.
        """

        verified_items = []

        for item in verification.get(
            "classifications",
            []
        ):

            if not isinstance(
                item,
                dict
            ):
                continue

            label = item.get(
                "label"
            )

            if label not in (
                self.evidence_verifier.SUPPORTS,
                self.evidence_verifier.CONTRADICTS
            ):
                continue

            verified_items.append(
                {
                    "result_id": item.get(
                        "result_id",
                        ""
                    ),
                    "label": label,
                    "title": item.get(
                        "title",
                        ""
                    ),
                    "reason": item.get(
                        "reason",
                        ""
                    ),
                    "confidence": item.get(
                        "confidence",
                        0.0
                    ),
                    "method": item.get(
                        "method",
                        ""
                    )
                }
            )

        prompt = f"""
Bạn là BCOS Evidence Conflict Summarizer.

CÂU HỎI:
{question}

VERIFICATION STATUS:
CONFLICTED

Các evidence đã được phân loại:

{json.dumps(
    verified_items,
    ensure_ascii=False,
    indent=2
)}

QUY TẮC:

1. Trạng thái CONFLICTED là kết luận cố định.
2. Không được biến CONFLICTED thành SUPPORTED.
3. Không được biến CONFLICTED thành INSUFFICIENT.
4. Không được tự chọn một nguồn nếu không có căn cứ.
5. Không dùng kiến thức riêng của model để giải quyết mâu thuẫn.
6. Nêu rõ có evidence ủng hộ và evidence phản bác.
7. Trả lời bằng tiếng Việt.
8. Không bịa.

Chỉ tạo câu trả lời cuối cùng.
"""

        return self.llm.chat(
            [
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )

    # =========================================================
    # INSUFFICIENT ANSWER
    # =========================================================

    def _answer_insufficient(
        self,
        question,
        verification
    ):
        """
        Qwen may only explain the insufficiency.

        It must NOT introduce external facts.
        """

        prompt = f"""
Bạn là BCOS Evidence Answer Generator.

CÂU HỎI:
{question}

VERIFICATION STATUS:
INSUFFICIENT

Verification đã kết luận rằng evidence hiện có
chưa đủ để xác nhận hoặc phản bác câu hỏi.

QUY TẮC:

1. Không bịa.
2. Không dùng kiến thức riêng của model.
3. Không tự đưa ra một câu trả lời factual mới.
4. Không biến INSUFFICIENT thành SUPPORTED.
5. Không biến INSUFFICIENT thành CONTRADICTED.
6. Chỉ nói rằng evidence hiện có chưa đủ.
7. Trả lời ngắn gọn bằng tiếng Việt.

Chỉ tạo câu trả lời cuối cùng.
"""

        return self.llm.chat(
            [
                {
                    "role": "system",
                    "content": prompt
                }
            ]
        )

    # =========================================================
    # COMPLEX
    # =========================================================

    def _handle_complex(
        self,
        question
    ):

        self.trace(
            3,
            "TASK LOCK",
            "Task được xác định là COMPLEX.",
            {
                "reason": (
                    "Complex task requires targeted "
                    "evidence before reasoning."
                )
            }
        )

        print(
            "\n🌐 Complex task: "
            "thu thập evidence...",
            flush=True
        )

        # -----------------------------------------------------
        # Build queries
        # -----------------------------------------------------

        queries = self.build_complex_queries(
            question
        )

        self.trace(
            4,
            "EVIDENCE PLAN",
            "Các truy vấn evidence được tạo.",
            {
                "query_count": len(
                    queries
                ),
                "queries": queries
            }
        )

        print(
            f"🔎 Evidence queries: "
            f"{len(queries)}",
            flush=True
        )

        evidence = []

        # -----------------------------------------------------
        # Search
        # -----------------------------------------------------

        for index, query in enumerate(
            queries,
            start=1
        ):

            self.trace(
                5,
                "SEARCH PLAN",
                f"Search {index}/{len(queries)}",
                {
                    "query": query
                }
            )

            print(
                f"\n🔎 Search "
                f"{index}/{len(queries)}",
                flush=True
            )

            print(
                f"   {query}",
                flush=True
            )

            try:

                result = self.tools[
                    Action.SEARCH
                ].run(
                    query
                )

                evidence.append(
                    {
                        "query": query,
                        "result": result
                    }
                )

                if (
                    isinstance(
                        result,
                        dict
                    )
                    and result.get(
                        "success",
                        False
                    )
                ):

                    raw_results = result.get(
                        "results",
                        []
                    )

                    result_count = (
                        len(raw_results)
                        if isinstance(
                            raw_results,
                            list
                        )
                        else 0
                    )

                    self.trace(
                        6,
                        "EVIDENCE ACQUISITION",
                        f"Search {index} thành công.",
                        {
                            "query": query,
                            "success": True,
                            "result_count": result_count
                        }
                    )

                    print(
                        "   ✅ Evidence collected",
                        flush=True
                    )

                else:

                    self.trace(
                        6,
                        "EVIDENCE ACQUISITION",
                        (
                            f"Search {index} "
                            "không thu được evidence hợp lệ."
                        ),
                        {
                            "query": query,
                            "success": False
                        }
                    )

                    print(
                        "   ⚠️ Search returned "
                        "failure or no evidence",
                        flush=True
                    )

            except Exception as exc:

                self.trace(
                    6,
                    "EVIDENCE ERROR",
                    f"Search {index} failed.",
                    {
                        "query": query,
                        "error": str(exc)
                    }
                )

                print(
                    f"   ❌ Search failed: {exc}",
                    flush=True
                )

                evidence.append(
                    {
                        "query": query,
                        "result": {
                            "success": False,
                            "source": "Search",
                            "query": query,
                            "error": str(exc),
                            "results": []
                        }
                    }
                )

        # -----------------------------------------------------
        # Evidence summary
        # -----------------------------------------------------

        evidence_summary = []

        for index, item in enumerate(
            evidence,
            start=1
        ):

            if not isinstance(
                item,
                dict
            ):
                continue

            result = item.get(
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

            result_count = (
                len(results)
                if isinstance(
                    results,
                    list
                )
                else 0
            )

            evidence_summary.append(
                {
                    "evidence_id": (
                        f"EVIDENCE_{index}"
                    ),
                    "query": item.get(
                        "query",
                        ""
                    ),
                    "success": result.get(
                        "success",
                        False
                    ),
                    "source": result.get(
                        "source",
                        ""
                    ),
                    "result_count": result_count
                }
            )

        self.trace(
            7,
            "EVIDENCE SUMMARY",
            "Tổng hợp trạng thái evidence.",
            evidence_summary
        )

        # -----------------------------------------------------
        # Raw evidence
        # -----------------------------------------------------

        self.debug_raw_evidence(
            evidence
        )

        self.trace(
            8,
            "EVIDENCE INSPECTION",
            (
                "Raw evidence đã được kiểm tra. "
                "Council chỉ được phép sử dụng "
                "evidence được cung cấp."
            )
        )

        # -----------------------------------------------------
        # Council
        # -----------------------------------------------------

        print(
            "\n🤖 Focused Council: "
            "Reasoning + Critic + Judge...",
            flush=True
        )

        council_evidence = (
            self.format_complex_evidence(
                evidence
            )
        )

        self.trace(
            9,
            "COUNCIL INPUT",
            "Evidence được compact trước Council.",
            {
                "characters": len(
                    council_evidence
                )
            }
        )

        result = self.council.run(
            question,
            council_evidence,
            mode="focused"
        )

        self.trace(
            10,
            "COUNCIL RESULT",
            "Council + Judge đã hoàn tất."
        )

        answer = result

        self.trace(
            11,
            "FINAL ANSWER",
            "Trả kết quả từ Judge."
        )

        yield answer

        self.memory.add(
            "assistant",
            answer
        )

    # =========================================================
    # EXECUTE TOOL
    # =========================================================

    def execute_tool(
        self,
        action,
        parameters
    ):

        required = (
            self.tool_required_parameters.get(
                action,
                []
            )
        )

        parameters = (
            parameters
            if isinstance(
                parameters,
                dict
            )
            else {}
        )

        missing = []

        for parameter in required:

            value = parameters.get(
                parameter
            )

            if value is None:

                missing.append(
                    parameter
                )

            elif (
                isinstance(
                    value,
                    str
                )
                and not value.strip()
            ):

                missing.append(
                    parameter
                )

        if missing:

            raise ValueError(
                "Missing required parameters: "
                + ", ".join(
                    missing
                )
            )

        tool = self.tools.get(
            action
        )

        if tool is None:

            raise ValueError(
                f"Unsupported tool action: "
                f"{action}"
            )

        if action == Action.SEARCH:

            return tool.run(
                parameters["query"]
            )

        if action == Action.CALCULATOR:

            return tool.run(
                parameters["expression"]
            )

        if action == Action.FILE:

            return tool.run(
                parameters["path"]
            )

        raise ValueError(
            f"Unsupported action: "
            f"{action}"
        )

    # =========================================================
    # COMPLEX QUERY BUILDER
    # =========================================================

    def build_complex_queries(
        self,
        question
    ):

        q = str(
            question
        ).lower()

        queries = []

        # -----------------------------------------------------
        # SAVEPOINT
        # -----------------------------------------------------

        if "savepoint" in q:

            queries.extend(
                [
                    (
                        "SQLite official documentation "
                        "SAVEPOINT"
                    ),
                    (
                        "PostgreSQL official documentation "
                        "SAVEPOINT"
                    ),
                    (
                        "SQLite transaction savepoint "
                        "official documentation"
                    ),
                    (
                        "PostgreSQL transaction savepoint "
                        "official documentation"
                    ),
                ]
            )

        # -----------------------------------------------------
        # DATABASE / CONCURRENCY
        # -----------------------------------------------------

        if any(
            token in q
            for token in [
                "sqlite",
                "postgresql",
                "postgres",
                "database",
                "concurrent",
                "concurrency",
                "warehouse",
                "inventory",
                "transaction",
                "locking",
                "lock",
            ]
        ):

            queries.extend(
                [
                    (
                        f"{question} "
                        "database concurrency transactions"
                    ),
                    (
                        f"{question} "
                        "SQLite locking concurrency"
                    ),
                    (
                        f"{question} "
                        "PostgreSQL concurrency transactions"
                    ),
                ]
            )

        # -----------------------------------------------------
        # Generic complex
        # -----------------------------------------------------

        if not queries:

            queries.extend(
                [
                    question,
                    f"{question} evidence",
                    (
                        f"{question} "
                        "official documentation"
                    ),
                ]
            )

        # -----------------------------------------------------
        # Deduplicate
        # -----------------------------------------------------

        result = []

        seen = set()

        for query in queries:

            query = str(
                query
            ).strip()

            if not query:
                continue

            normalized = query.lower()

            if normalized in seen:
                continue

            seen.add(
                normalized
            )

            result.append(
                query
            )

        return result

    # =========================================================
    # FORMAT COMPLEX EVIDENCE
    # =========================================================

    def format_complex_evidence(
        self,
        evidence
    ):

        compact = []

        for evidence_index, item in enumerate(
            evidence,
            start=1
        ):

            if not isinstance(
                item,
                dict
            ):
                continue

            query = str(
                item.get(
                    "query",
                    ""
                )
            )

            result = item.get(
                "result",
                {}
            )

            if not isinstance(
                result,
                dict
            ):
                continue

            compact_item = {
                "evidence_id": (
                    f"EVIDENCE_{evidence_index}"
                ),
                "query": query[:500],
                "source": result.get(
                    "source",
                    ""
                ),
                "success": result.get(
                    "success",
                    False
                ),
            }

            results = result.get(
                "results",
                []
            )

            compact_results = []

            if isinstance(
                results,
                list
            ):

                for result_index, search_result in enumerate(
                    results[:5],
                    start=1
                ):

                    if not isinstance(
                        search_result,
                        dict
                    ):
                        continue

                    compact_results.append(
                        {
                            "result_id": (
                                f"EVIDENCE_"
                                f"{evidence_index}"
                                f"_R{result_index}"
                            ),
                            "title": str(
                                search_result.get(
                                    "title",
                                    ""
                                )
                            )[:250],
                            "url": str(
                                search_result.get(
                                    "url",
                                    ""
                                )
                            )[:500],
                            "content": str(
                                search_result.get(
                                    "content",
                                    ""
                                )
                            )[:1800],
                        }
                    )

            compact_item[
                "results"
            ] = compact_results

            compact.append(
                compact_item
            )

        return json.dumps(
            compact,
            ensure_ascii=False,
            indent=2
        )

    # =========================================================
    # RAW EVIDENCE DEBUG
    # =========================================================

    def debug_raw_evidence(
        self,
        evidence
    ):

        print(
            "\n============================================================",
            flush=True
        )

        print(
            "RAW EVIDENCE DEBUG",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        for evidence_index, item in enumerate(
            evidence,
            start=1
        ):

            print(
                f"\n--- EVIDENCE {evidence_index} ---",
                flush=True
            )

            if not isinstance(
                item,
                dict
            ):

                print(
                    "INVALID EVIDENCE ITEM",
                    flush=True
                )

                continue

            evidence_id = (
                f"EVIDENCE_{evidence_index}"
            )

            query = item.get(
                "query",
                ""
            )

            result = item.get(
                "result",
                {}
            )

            print(
                f"EVIDENCE ID: "
                f"{evidence_id}",
                flush=True
            )

            print(
                f"QUERY: {query}",
                flush=True
            )

            if not isinstance(
                result,
                dict
            ):

                print(
                    "RESULT: INVALID",
                    flush=True
                )

                continue

            print(
                f"SOURCE: "
                f"{result.get('source', '')}",
                flush=True
            )

            print(
                f"SUCCESS: "
                f"{result.get('success', False)}",
                flush=True
            )

            results = result.get(
                "results",
                []
            )

            if not isinstance(
                results,
                list
            ):

                print(
                    "RESULT COUNT: 0",
                    flush=True
                )

                continue

            print(
                f"RESULT COUNT: "
                f"{len(results)}",
                flush=True
            )

            for result_index, search_result in enumerate(
                results,
                start=1
            ):

                if not isinstance(
                    search_result,
                    dict
                ):
                    continue

                result_id = (
                    f"EVIDENCE_"
                    f"{evidence_index}"
                    f"_R{result_index}"
                )

                print(
                    f"\n{result_id}",
                    flush=True
                )

                print(
                    "TITLE:",
                    search_result.get(
                        "title",
                        ""
                    ),
                    flush=True
                )

                print(
                    "URL:",
                    search_result.get(
                        "url",
                        ""
                    ),
                    flush=True
                )

                print(
                    "CONTENT:",
                    search_result.get(
                        "content",
                        ""
                    ),
                    flush=True
                )

        print(
            "\n============================================================",
            flush=True
        )

        print(
            "END RAW EVIDENCE DEBUG",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

    # =========================================================
    # CALCULATOR RESULT
    # =========================================================

    def format_calculator_result(
        self,
        result
    ):

        if isinstance(
            result,
            dict
        ):

            if result.get(
                "success",
                False
            ):

                if "result" in result:

                    return str(
                        result["result"]
                    )

                if "value" in result:

                    return str(
                        result["value"]
                    )

            error = result.get(
                "error"
            )

            if error:

                return (
                    f"Calculator error: "
                    f"{error}"
                )

        return str(
            result
        )