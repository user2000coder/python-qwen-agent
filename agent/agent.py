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
import re
import unicodedata

import log

from llm import LLM
from planner import Planner
from memory import Memory
from protocol import Action
from council import Council
from evidence_verifier import EvidenceVerifier

from tools.search import SearchTool
from tools.calculator import CalculatorTool
from tools.file import FileTool


LOGGER = log.get(
    "agent"
)


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

        # A planner fallback is a degradation, not a decision.
        # Saying so is the difference between "the agent chose to
        # answer directly" and "routing broke and nobody noticed".

        planner_error = getattr(
            call,
            "error",
            None
        )

        if planner_error:

            self.trace(
                2,
                "PLANNER FALLBACK",
                (
                    "Planner không phân loại được; "
                    "đã degrade sang ANSWER."
                ),
                {
                    "error": planner_error
                }
            )

            print(
                f"⚠️  Planner degrade: {planner_error}",
                flush=True
            )

        LOGGER.info(
            "question=%r action=%s parameters=%r "
            "planner_error=%r",
            question,
            call.action.value,
            call.parameters,
            planner_error,
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

            # A typo inside a tool reaches here too, and used to
            # be shown to the user as a transient tool failure
            # with no traceback anywhere.

            LOGGER.error(
                "tool %s raised for parameters %r",
                action.value,
                parameters,
                exc_info=True
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

        # -----------------------------------------------------
        # Retrieval health
        # -----------------------------------------------------
        #
        # SearchTool and FileTool never raise: they return
        # {"success": False, "error": ...}. Announcing success
        # unconditionally made the trace assert a tool completed
        # while it had in fact returned a 403, and the failure
        # then reached the verifier as "zero evidence" — which
        # the user read as "the claim is unsupported" rather
        # than "retrieval failed".

        tool_ok = True

        tool_error = ""

        if isinstance(
            result,
            dict
        ):

            tool_ok = bool(
                result.get(
                    "success",
                    True
                )
            )

            tool_error = str(
                result.get(
                    "error",
                    ""
                )
            ).strip()

        if not tool_ok:

            self.trace(
                4,
                "TOOL FAILURE",
                "Tool trả về success=False.",
                {
                    "action": action.value,
                    "error": tool_error
                }
            )

            print(
                f"⚠️  Tool thất bại: {tool_error}",
                flush=True
            )

            answer = self.describe_tool_failure(
                action,
                result
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
                "result": self.as_verifiable_result(
                    result
                )
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

        reasons = []

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

            reason = str(
                item.get(
                    "reason",
                    ""
                )
            ).strip()

            # The classifier's reason is the only place it says
            # HOW the evidence supports the claim. Dropping it
            # left an assertion plus a link list — no information
            # from the evidence at all.

            if reason and reason not in reasons:

                reasons.append(
                    reason
                )

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
        #
        # is_polar_question() is deliberately narrow, so a
        # non-polar question falls through to wording that does
        # not assert a yes.

        if self.is_polar_question(
            question
        ):

            answer = (
                "Có — evidence xác nhận điều này."
            )

        else:

            answer = (
                "Evidence phù hợp với câu hỏi, nhưng hệ "
                "thống không trích xuất được một thực thể "
                "trả lời cụ thể. Nội dung xác nhận được:"
            )

        parts = [
            answer
        ]

        if reasons:

            parts.append(
                "\nCĂN CỨ:\n"
                + "\n".join(
                    f"- {reason}"
                    for reason in reasons[:3]
                )
            )

        if evidence_block:

            parts.append(
                "\nBẰNG CHỨNG:\n"
                + evidence_block
            )

        return "\n".join(
            parts
        )

    # =========================================================
    # POLAR QUESTION DETECTION
    # =========================================================

    # Interrogatives that make a question NOT yes/no. Matched on
    # diacritic-folded whole tokens, so "nao"/"nào" and
    # "tai sao"/"tại sao" both hit.

    WH_TOKENS = frozenset(
        {
            "ai",
            "gi",
            "nao",
            "dau",
            "may",
            "who",
            "whom",
            "whose",
            "what",
            "which",
            "when",
            "where",
            "why",
            "how",
        }
    )


    WH_PHRASES = (
        "bao nhieu",
        "bao lau",
        "khi nao",
        "o dau",
        "tai sao",
        "vi sao",
        "the nao",
        "ra sao",
        "nhu the nao",
    )


    # Vietnamese polar particles, and the frame token a real polar
    # question pairs them with.
    #
    # The particle alone is not enough: "không" also means zero
    # ("bằng không", "hàng không" = aviation) and "chưa" collides
    # with "chua" = sour ("sữa chua" = yogurt) once diacritics are
    # folded. Requiring a có/đã/phải/được frame separates
    # "PostgreSQL có hỗ trợ row locking không?" from
    # "Thành phần của sữa chua?".

    POLAR_PARTICLES = frozenset(
        {
            "khong",
            "chua",
        }
    )


    POLAR_FRAME_TOKENS = frozenset(
        {
            "co",
            "da",
            "phai",
            "duoc",
        }
    )


    ENGLISH_AUXILIARIES = frozenset(
        {
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
        }
    )


    # "Can you list the steps…" is a request, not a yes/no question.

    ENGLISH_REQUEST_PREFIXES = (
        "can you",
        "could you",
        "would you",
        "will you",
        "do you mind",
    )


    def is_polar_question(
        self,
        question
    ):
        """
        Deterministic yes/no (polar) question detection.

        Answering "Có" to something that was never a yes/no
        question is worse than a vague answer, so every rule here
        is a narrowing one and the default is False:

            * an interrogative (ai/gì/nào/bao nhiêu/why/how…)
              disqualifies the question outright
            * a Vietnamese particle must be the final token AND be
              paired with a có/đã/phải/được frame
            * an English auxiliary counts only at the start of an
              actual question, and not in a request form
        """

        text = unicodedata.normalize(
            "NFC",
            str(
                question or ""
            ),
        ).strip()

        if not text:
            return False

        had_question_mark = "?" in text

        folded = SearchTool.fold(
            text
        )

        folded = folded.rstrip(
            "?!.,;:…\u2026 \t"
        )

        if not folded:
            return False

        tokens = re.findall(
            r"[a-z0-9]+",
            folded
        )

        if not tokens:
            return False

        # -----------------------------------------------------
        # Interrogative veto
        # -----------------------------------------------------

        if any(
            token in self.WH_TOKENS
            for token in tokens
        ):
            return False

        for phrase in self.WH_PHRASES:

            if phrase in folded:
                return False

        # -----------------------------------------------------
        # Vietnamese: final particle + frame
        # -----------------------------------------------------

        if tokens[-1] in self.POLAR_PARTICLES:

            return any(
                token in self.POLAR_FRAME_TOKENS
                for token in tokens[:-1]
            )

        if folded.startswith(
            "co phai"
        ):
            return True

        # -----------------------------------------------------
        # English: leading auxiliary in a real question
        # -----------------------------------------------------

        if not had_question_mark:
            return False

        for prefix in self.ENGLISH_REQUEST_PREFIXES:

            if folded.startswith(
                prefix
            ):
                return False

        return tokens[0] in self.ENGLISH_AUXILIARIES

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
        # Zero-evidence guard
        # -----------------------------------------------------
        #
        # Without this the Council runs on an evidence list where
        # every entry is {"success": False, "results": []} and the
        # Judge answers from model memory — an evidence-first
        # agent fabricating a confident answer. Three LLM calls
        # on a CPU 3B model are also wasted.

        usable_results = self.count_usable_results(
            evidence
        )

        if usable_results == 0:

            self.trace(
                9,
                "RETRIEVAL FAILURE",
                (
                    "Không thu được evidence nào. "
                    "Bỏ qua Council."
                ),
                {
                    "queries": len(evidence)
                }
            )

            answer = self.describe_retrieval_failure(
                evidence
            )

            yield answer

            self.memory.add(
                "assistant",
                answer
            )

            return

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
    # RETRIEVAL HEALTH
    # =========================================================

    ENVELOPE_KEYS = (
        "success",
        "source",
        "query",
        "count",
        "results",
        "error",
        "confidence",
        "data_type",
    )


    def describe_tool_failure(
        self,
        action,
        result
    ):
        """
        Deterministic message for a tool that reported failure.

        Never routed through the evidence verifier: "the tool
        could not fetch anything" and "the evidence does not
        support the claim" are different answers, and conflating
        them is what made a blocked search look like a settled
        question.
        """

        source = ""

        error = ""

        if isinstance(
            result,
            dict
        ):

            source = str(
                result.get(
                    "source",
                    ""
                )
            ).strip()

            error = str(
                result.get(
                    "error",
                    ""
                )
            ).strip()

        where = (
            f"{action.value}"
            + (
                f" ({source})"
                if source
                else ""
            )
        )

        lines = [
            "KẾT LUẬN: Chưa thể trả lời vì tool "
            "thu thập dữ liệu đã thất bại.",
            "",
            f"TOOL: {where}",
        ]

        if error:

            lines.append(
                f"LỖI: {error[:300]}"
            )

        lines.extend(
            [
                "",
                "ĐỘ TIN CẬY: Không có.",
                "",
                "GIỚI HẠN: Đây là lỗi thu thập dữ liệu, "
                "không phải kết luận về câu hỏi.",
            ]
        )

        return "\n".join(
            lines
        )



    def as_verifiable_result(
        self,
        result
    ):
        """
        Give every successful tool payload a `results` list.

        EvidenceVerifier only reads `result["results"]` and skips
        an entry whose value is not a list. Two successful shapes
        carry no such key and were therefore dropped in silence:

            FileTool  {success, file, content, confidence}
            CoinGecko {success, asset, symbol, price_usd, ...}

        So a file that was read, or a price that was fetched,
        produced zero classifications and the user was told there
        was not enough evidence. Wrapping the payload here keeps
        the verifier's contract untouched.
        """

        if not isinstance(
            result,
            dict
        ):
            return result

        if isinstance(
            result.get(
                "results"
            ),
            list
        ):
            return result

        if not result.get(
            "success",
            False
        ):
            return result

        # -----------------------------------------------------
        # Title
        # -----------------------------------------------------

        title = ""

        for key in (
            "file",
            "asset",
            "data_type",
        ):

            value = str(
                result.get(
                    key,
                    ""
                )
            ).strip()

            if value:

                title = value

                break

        if not title:

            title = str(
                result.get(
                    "source",
                    "tool result"
                )
            )

        # -----------------------------------------------------
        # Content
        # -----------------------------------------------------

        content = str(
            result.get(
                "content",
                ""
            )
        ).strip()

        if not content:

            parts = []

            for key, value in result.items():

                if key in self.ENVELOPE_KEYS:
                    continue

                parts.append(
                    f"{key}: {value}"
                )

            content = ", ".join(
                parts
            )

        if not content:
            return result

        adapted = dict(
            result
        )

        adapted[
            "results"
        ] = [
            {
                "title": title,
                "url": str(
                    result.get(
                        "url",
                        ""
                    )
                ),
                "content": content,
            }
        ]

        adapted[
            "count"
        ] = 1

        adapted[
            "adapted_from"
        ] = "structured_payload"

        return adapted


    def count_usable_results(
        self,
        evidence
    ):
        """
        Number of search results actually available to reason on.

        A failed search and a search that returned nothing are
        both zero here: neither gives the Council anything to
        ground an answer in.
        """

        total = 0

        for item in evidence or []:

            if not isinstance(
                item,
                dict
            ):
                continue

            result = item.get(
                "result"
            )

            if not isinstance(
                result,
                dict
            ):
                continue

            if not result.get(
                "success",
                False
            ):
                continue

            results = result.get(
                "results"
            )

            if isinstance(
                results,
                list
            ):
                total += len(
                    results
                )

        return total



    def describe_retrieval_failure(
        self,
        evidence
    ):
        """
        Deterministic message for "the tools returned nothing".

        Distinct from "the evidence does not support the claim":
        the user needs to know retrieval failed, not that the
        world has no answer.
        """

        lines = [
            "KẾT LUẬN: Không thu được evidence nào "
            "nên chưa thể kết luận.",
            "",
            "NGUYÊN NHÂN: Các truy vấn sau không trả về "
            "kết quả nào:",
        ]

        for item in evidence or []:

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
            ).strip()

            result = item.get(
                "result"
            )

            error = ""

            if isinstance(
                result,
                dict
            ):
                error = str(
                    result.get(
                        "error",
                        ""
                    )
                ).strip()

            if not query:
                continue

            if error:

                lines.append(
                    f"- {query[:160]} — {error[:160]}"
                )

            else:

                lines.append(
                    f"- {query[:160]} — 0 kết quả"
                )

        lines.extend(
            [
                "",
                "ĐỘ TIN CẬY: Không có.",
                "",
                "GIỚI HẠN: Đây là lỗi thu thập evidence, "
                "không phải kết luận về câu hỏi. "
                "Kiểm tra kết nối mạng hoặc search backend "
                "rồi thử lại.",
            ]
        )

        return "\n".join(
            lines
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