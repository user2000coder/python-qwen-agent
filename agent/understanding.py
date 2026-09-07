"""
BCOS Problem Understanding Layer.

Responsibilities:
- Understand the user's actual task.
- Separate goal, problem, context, constraints, decision and success criteria.
- Explicitly track known facts, unknowns, assumptions and ambiguities.
- Decide whether understanding is sufficient for planning.

This layer MUST NOT:
- select tools
- execute tools
- generate the execution plan
- make the final decision for the user
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import json
from typing import Any, Dict, List, Optional


class UnderstandingStatus(str, Enum):
    UNDERSTOOD = "understood"
    NEEDS_CLARIFICATION = "needs_clarification"
    AMBIGUOUS = "ambiguous"
    INSUFFICIENT_CONTEXT = "insufficient_context"


@dataclass
class ProblemUnderstanding:
    """
    Structured representation of the user's problem.

    This object is the contract between the Understanding layer
    and the Planner layer.
    """

    original_input: str

    task: str = "UNKNOWN"
    goal: str = ""
    problem: str = ""

    context: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)

    decision: str = ""
    success_criteria: List[str] = field(default_factory=list)

    known_facts: List[str] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)
    assumptions: List[str] = field(default_factory=list)
    ambiguities: List[str] = field(default_factory=list)

    confidence: float = 0.0

    status: UnderstandingStatus = (
        UnderstandingStatus.INSUFFICIENT_CONTEXT
    )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
        )


class UnderstandingValidator:
    """
    Deterministic validation gate.

    The validator prevents the LLM from claiming that a problem
    is understood when important ambiguity or missing information
    remains unresolved.
    """

    VALID_STATUSES = {
        status.value for status in UnderstandingStatus
    }

    def validate(
        self,
        understanding: ProblemUnderstanding,
    ) -> List[str]:
        errors: List[str] = []

        if not isinstance(
            understanding,
            ProblemUnderstanding,
        ):
            return ["result must be ProblemUnderstanding"]

        if not understanding.original_input.strip():
            errors.append("original_input is empty")

        if not understanding.task.strip():
            errors.append("task is empty")

        if not understanding.goal.strip():
            errors.append("goal is empty")

        if not understanding.problem.strip():
            errors.append("problem is empty")

        if understanding.status.value not in self.VALID_STATUSES:
            errors.append("invalid status")

        try:
            confidence = float(understanding.confidence)
        except (TypeError, ValueError):
            errors.append("confidence must be numeric")
            confidence = 0.0

        if not 0.0 <= confidence <= 1.0:
            errors.append(
                "confidence must be between 0 and 1"
            )

        if (
            understanding.status
            == UnderstandingStatus.UNDERSTOOD
        ):
            if understanding.ambiguities:
                errors.append(
                    "UNDERSTOOD cannot contain unresolved "
                    "ambiguities"
                )

            if understanding.unknowns:
                errors.append(
                    "UNDERSTOOD cannot contain unresolved "
                    "unknowns"
                )

        if understanding.status in {
            UnderstandingStatus.AMBIGUOUS,
            UnderstandingStatus.NEEDS_CLARIFICATION,
            UnderstandingStatus.INSUFFICIENT_CONTEXT,
        }:
            if not (
                understanding.unknowns
                or understanding.ambiguities
            ):
                errors.append(
                    "non-understood status requires "
                    "unknowns or ambiguities"
                )

        return errors


class ProblemUnderstandingEngine:
    """
    LLM-backed problem understanding engine.

    Input:
        conversation history

    Output:
        ProblemUnderstanding

    Important:
        This engine does not select tools and does not execute
        anything.
    """

    def __init__(self, llm: Any):
        self.llm = llm
        self.validator = UnderstandingValidator()

    def understand(
        self,
        history: List[Dict[str, str]],
    ) -> ProblemUnderstanding:
        """
        Convert conversation history into structured understanding.
        """

        if not history:
            return ProblemUnderstanding(
                original_input="",
                task="UNKNOWN",
                goal="",
                problem="",
                unknowns=[
                    "No user input is available."
                ],
                confidence=0.0,
                status=(
                    UnderstandingStatus.INSUFFICIENT_CONTEXT
                ),
            )

        original_input = self._get_last_user_input(history)

        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            }
        ]

        messages.extend(history)

        try:
            response = self._call_llm(messages)

            understanding = self.parse(
                response=response,
                original_input=original_input,
            )

        except Exception as exc:
            return self._fallback(
                question=original_input,
                reason=str(exc),
            )

        errors = self.validator.validate(understanding)

        if errors:
            return self._fallback(
                question=original_input,
                reason="; ".join(errors),
            )

        return understanding

    def _call_llm(
        self,
        messages: List[Dict[str, str]],
    ) -> str:
        """
        Adapter around the existing LLM interface.

        Supports the common interfaces already used by BCOS.
        """

        if hasattr(self.llm, "chat"):
            response = self.llm.chat(messages)

        elif hasattr(self.llm, "generate"):
            response = self.llm.generate(messages)

        elif callable(self.llm):
            response = self.llm(messages)

        else:
            raise TypeError(
                "Unsupported LLM interface"
            )

        if isinstance(response, str):
            return response

        if isinstance(response, dict):
            if "content" in response:
                return str(response["content"])

            if "response" in response:
                return str(response["response"])

            if "text" in response:
                return str(response["text"])

        raise TypeError(
            "LLM response must be string or supported dict"
        )

    def parse(
        self,
        response: str,
        original_input: str,
    ) -> ProblemUnderstanding:
        """
        Parse strict JSON returned by the LLM.
        """

        cleaned = self._clean_json(response)

        data = json.loads(cleaned)

        if not isinstance(data, dict):
            raise ValueError(
                "Understanding response must be a JSON object"
            )

        status_raw = str(
            data.get(
                "status",
                UnderstandingStatus.INSUFFICIENT_CONTEXT.value,
            )
        ).strip().lower()

        try:
            status = UnderstandingStatus(status_raw)
        except ValueError:
            status = UnderstandingStatus.INSUFFICIENT_CONTEXT

        confidence = self._confidence(
            data.get("confidence", 0.0)
        )

        return ProblemUnderstanding(
            original_input=original_input,

            task=self._string(
                data.get("task", "UNKNOWN")
            ),

            goal=self._string(
                data.get("goal", "")
            ),

            problem=self._string(
                data.get("problem", "")
            ),

            context=self._list(
                data.get("context")
            ),

            constraints=self._list(
                data.get("constraints")
            ),

            decision=self._string(
                data.get("decision", "")
            ),

            success_criteria=self._list(
                data.get("success_criteria")
            ),

            known_facts=self._list(
                data.get("known_facts")
            ),

            unknowns=self._list(
                data.get("unknowns")
            ),

            assumptions=self._list(
                data.get("assumptions")
            ),

            ambiguities=self._list(
                data.get("ambiguities")
            ),

            confidence=confidence,
            status=status,
        )

    @staticmethod
    def _clean_json(response: str) -> str:
        """
        Remove markdown code fences if the LLM accidentally
        returns them.
        """

        text = response.strip()

        if text.startswith("```"):
            lines = text.splitlines()

            if lines and lines[0].startswith("```"):
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        return text

    @staticmethod
    def _string(value: Any) -> str:
        if value is None:
            return ""

        return str(value).strip()

    @staticmethod
    def _list(value: Any) -> List[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [
                str(item).strip()
                for item in value
                if str(item).strip()
            ]

        value = str(value).strip()

        if not value:
            return []

        return [value]

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(
            0.0,
            min(1.0, confidence),
        )

    @staticmethod
    def _get_last_user_input(
        history: List[Dict[str, str]],
    ) -> str:
        for message in reversed(history):
            if message.get("role") == "user":
                return str(
                    message.get("content", "")
                ).strip()

        return ""

    @staticmethod
    def _fallback(
        question: str,
        reason: Optional[str] = None,
    ) -> ProblemUnderstanding:
        """
        Fail closed.

        If the understanding model fails, we deliberately DO NOT
        invent the user's goal or pretend that the problem is
        understood.
        """

        unknowns = [
            "Chưa xác định đầy đủ mục tiêu của người dùng.",
            "Chưa xác định đầy đủ yêu cầu để lập kế hoạch an toàn.",
        ]

        if reason:
            unknowns.append(
                "Understanding engine hoặc validation thất bại."
            )

        return ProblemUnderstanding(
            original_input=question,
            task="UNKNOWN",
            goal="",
            problem=question,
            unknowns=unknowns,
            assumptions=[],
            ambiguities=[],
            confidence=0.0,
            status=(
                UnderstandingStatus.INSUFFICIENT_CONTEXT
            ),
        )

    @staticmethod
    def _system_prompt() -> str:
        return """
You are the BCOS Problem Understanding Engine.

Your ONLY responsibility is to understand and structure
the user's problem before planning or execution.

DO NOT:
- select tools
- execute tools
- create an execution plan
- answer the user's problem
- make recommendations
- invent facts
- invent constraints
- invent context
- convert assumptions into facts
- treat missing evidence as contradiction

You MUST separate:

1. task
   The type of work the user is asking for.

   Examples:
   EXPLAIN
   EVALUATE
   DEBUG
   DESIGN
   PLAN
   RESEARCH
   COMPARE
   IMPLEMENT

   Use UNKNOWN if the task cannot be determined reliably.

2. goal
   What outcome the user actually wants.

3. problem
   The concrete problem that must be addressed.

4. context
   Relevant context explicitly available in the conversation.

5. constraints
   Explicit limitations or requirements.

6. decision
   What decision must eventually be made, if any.

7. success_criteria
   What would count as a successful result.

8. known_facts
   Facts explicitly provided or directly established
   by the conversation.

9. unknowns
   Information that is missing and could affect the result.

10. assumptions
    Things that would have to be assumed but are not confirmed.

11. ambiguities
    Multiple plausible interpretations that could lead
    to different answers or actions.

IMPORTANT EPISTEMIC RULES:

known_facts != assumptions
assumptions != conclusions
unknowns != contradictions
lack_of_information != evidence_against_a_claim

STATUS:

understood
    Use only when the task, goal and problem are sufficiently
    clear for the Planner to continue without making important
    assumptions.

needs_clarification
    Use when a specific missing answer from the user is needed.

ambiguous
    Use when multiple plausible interpretations could materially
    change the answer.

insufficient_context
    Use when important context is missing.

FAIL CLOSED.

If you are uncertain, do NOT guess.
Record the uncertainty in unknowns or ambiguities.

Return ONLY valid JSON.

Required schema:

{
  "task": "EXPLAIN | EVALUATE | DEBUG | DESIGN | PLAN | RESEARCH | COMPARE | IMPLEMENT | UNKNOWN",
  "goal": "",
  "problem": "",
  "context": [],
  "constraints": [],
  "decision": "",
  "success_criteria": [],
  "known_facts": [],
  "unknowns": [],
  "assumptions": [],
  "ambiguities": [],
  "confidence": 0.0,
  "status": "understood | needs_clarification | ambiguous | insufficient_context"
}
"""