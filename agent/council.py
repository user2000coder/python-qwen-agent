"""
BCOS Council

Council coordinates multiple specialist agents and a final Judge.

Modes
-----
focused:
    Reasoning + Critic + Judge

full:
    Fact Checker + Critic + Reasoning +
    Evidence Evaluator + Judge

Architecture invariant
----------------------
Judge MUST receive:

    1. Original Evidence
    2. Worker Reports

Worker reports are analysis, NOT primary evidence.
"""

import json
import time

from agents.fact_agent import FactAgent
from agents.critic_agent import CriticAgent
from agents.reasoning_agent import ReasoningAgent
from agents.evidence_agent import EvidenceAgent
from agents.judge_agent import JudgeAgent


class Council:

    def __init__(self, llm):
        self.llm = llm

        self.agents = [
            FactAgent(),
            CriticAgent(),
            ReasoningAgent(),
            EvidenceAgent(),
        ]

        self.judge = JudgeAgent()

    # =========================================================
    # SELECT MODE
    # =========================================================

    def _select_agents(self, mode):
        """
        Select worker agents for the requested Council mode.

        focused:
            Reasoning + Critic

        full:
            Fact + Critic + Reasoning + Evidence
        """

        if mode == "focused":
            return [
                ReasoningAgent(),
                CriticAgent(),
            ]

        if mode == "full":
            return self.agents

        raise ValueError(
            f"Unknown Council mode: {mode}. "
            f"Expected 'focused' or 'full'."
        )

    # =========================================================
    # RUN
    # =========================================================

    def run(
        self,
        question,
        evidence,
        mode="focused",
    ):
        """
        Run the Council.

        Parameters
        ----------
        question : str
            Original user question.

        evidence : str
            Original evidence collected by the system.

        mode : str
            'focused' or 'full'.

        Returns
        -------
        str
            Final Judge answer.
        """

        selected_agents = self._select_agents(mode)

        reports = []

        print(
            f"\n========== COUNCIL DEBUG ({mode}) ==========",
            flush=True,
        )

        print(
            "Workers: "
            + ", ".join(
                agent.role
                for agent in selected_agents
            ),
            flush=True,
        )

        # =====================================================
        # WORKER AGENTS
        # =====================================================

        for agent in selected_agents:

            role = agent.role

            print(
                f"\n[{role}] START",
                flush=True,
            )

            start = time.time()

            try:

                # ---------------------------------------------
                # Build worker prompt
                # ---------------------------------------------

                prompt = agent.prompt(
                    question,
                    evidence,
                )

                print(
                    f"[{role}] prompt ready",
                    flush=True,
                )

                # ---------------------------------------------
                # LLM reasoning
                # ---------------------------------------------

                answer = self.llm.chat(
                    [
                        {
                            "role": "system",
                            "content": prompt,
                        }
                    ]
                )

                elapsed = time.time() - start

                print(
                    f"[{role}] DONE "
                    f"({elapsed:.2f}s)",
                    flush=True,
                )

                reports.append(
                    {
                        "agent": role,
                        "report": answer,
                        "success": True,
                    }
                )

            except Exception as e:

                elapsed = time.time() - start

                print(
                    f"[{role}] ERROR "
                    f"after {elapsed:.2f}s: {e}",
                    flush=True,
                )

                reports.append(
                    {
                        "agent": role,
                        "report": f"ERROR: {e}",
                        "success": False,
                    }
                )

        # =====================================================
        # PREPARE ORIGINAL EVIDENCE
        # =====================================================

        judge_evidence = self.compact_evidence(
            evidence
        )

        # =====================================================
        # PREPARE WORKER REPORTS
        # =====================================================

        judge_reports = self.compact_reports(
            reports
        )

        # =====================================================
        # IMPORTANT ARCHITECTURAL INVARIANT
        # =====================================================
        #
        # Judge receives BOTH:
        #
        #   ORIGINAL_EVIDENCE
        #   WORKER_REPORTS
        #
        # Worker reports are analysis.
        # Original evidence remains the primary source.
        # =====================================================

        judge_input = {
            "original_evidence": judge_evidence,
            "worker_reports": judge_reports,
        }

        judge_input_text = json.dumps(
            judge_input,
            ensure_ascii=False,
            indent=2,
        )

        print(
            "\n📦 Judge input: "
            f"{len(judge_input_text)} characters",
            flush=True,
        )

        # =====================================================
        # JUDGE
        # =====================================================

        print(
            "\n[JUDGE] START",
            flush=True,
        )

        start = time.time()

        try:

            judge_prompt = self.judge.prompt(
                question,
                judge_input_text,
            )

            print(
                "[JUDGE] prompt ready",
                flush=True,
            )

            final = self.llm.chat(
                [
                    {
                        "role": "system",
                        "content": judge_prompt,
                    }
                ]
            )

            elapsed = time.time() - start

            print(
                f"[JUDGE] DONE "
                f"({elapsed:.2f}s)",
                flush=True,
            )

            print(
                "\n========== COUNCIL END ==========",
                flush=True,
            )

            return final

        except Exception as e:

            elapsed = time.time() - start

            print(
                f"[JUDGE] ERROR "
                f"after {elapsed:.2f}s: {e}",
                flush=True,
            )

            return (
                "Council Judge failed: "
                f"{e}"
            )

    # =========================================================
    # EVIDENCE COMPACTION
    # =========================================================

    def compact_evidence(
        self,
        evidence,
    ):
        """
        Compact evidence deterministically.

        IMPORTANT
        ---------
        This function MUST NOT call an LLM.

        Its purpose is only to reduce context size while
        preserving source information.

        Evidence remains primary source material.
        """

        if not isinstance(
            evidence,
            str,
        ):
            evidence = str(
                evidence
            )

        # -----------------------------------------------------
        # Try parsing JSON evidence
        # -----------------------------------------------------

        try:

            parsed = json.loads(
                evidence
            )

        except Exception:

            # Evidence is not JSON.
            # Preserve raw text with a safety limit.
            return evidence[:12000]

        # -----------------------------------------------------
        # Evidence is a JSON object
        # -----------------------------------------------------

        if not isinstance(
            parsed,
            list,
        ):

            return json.dumps(
                parsed,
                ensure_ascii=False,
                indent=2,
            )[:12000]

        # -----------------------------------------------------
        # Evidence is a list
        # -----------------------------------------------------

        compact = []

        for item in parsed:

            if not isinstance(
                item,
                dict,
            ):
                continue

            # ---------------------------------------------
            # Query
            # ---------------------------------------------

            query = str(
                item.get(
                    "query",
                    "",
                )
            )[:500]

            # ---------------------------------------------
            # Result
            # ---------------------------------------------

            result = item.get(
                "result",
                {},
            )

            if not isinstance(
                result,
                dict,
            ):
                continue

            compact_item = {
                "query": query,
                "source": result.get(
                    "source",
                    "",
                ),
                "success": result.get(
                    "success",
                    False,
                ),
            }

            # ---------------------------------------------
            # Search results
            # ---------------------------------------------

            results = result.get(
                "results",
                [],
            )

            compact_results = []

            if isinstance(
                results,
                list,
            ):

                # Keep top 3 results per query.
                for search_result in results[:3]:

                    if not isinstance(
                        search_result,
                        dict,
                    ):
                        continue

                    compact_results.append(
                        {
                            "title": str(
                                search_result.get(
                                    "title",
                                    "",
                                )
                            )[:250],

                            "url": str(
                                search_result.get(
                                    "url",
                                    "",
                                )
                            )[:500],

                            "content": str(
                                search_result.get(
                                    "content",
                                    "",
                                )
                            )[:1200],
                        }
                    )

            compact_item[
                "results"
            ] = compact_results

            compact.append(
                compact_item
            )

        # -----------------------------------------------------
        # Serialize
        # -----------------------------------------------------

        return json.dumps(
            compact,
            ensure_ascii=False,
            indent=2,
        )

    # =========================================================
    # REPORT COMPACTION
    # =========================================================

    def compact_reports(
        self,
        reports,
    ):
        """
        Compact worker reports.

        Worker reports are analysis, not primary evidence.

        A worker cannot dominate the Judge context merely by
        generating a very large response.
        """

        compact = []

        for item in reports:

            if not isinstance(
                item,
                dict,
            ):
                continue

            compact.append(
                {
                    "agent": str(
                        item.get(
                            "agent",
                            "",
                        )
                    )[:100],

                    "success": item.get(
                        "success",
                        False,
                    ),

                    "report": str(
                        item.get(
                            "report",
                            "",
                        )
                    )[:5000],
                }
            )

        return compact