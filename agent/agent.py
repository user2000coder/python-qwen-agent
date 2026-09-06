"""
BCOS Agent Core

Pipeline:

User
  ↓
Planner
  ↓
  ├── ANSWER
  │      └── Direct LLM
  │
  ├── CALCULATOR
  │      └── Deterministic Tool
  │
  ├── SEARCH
  │      └── Search Tool → Evidence Synthesis
  │
  ├── FILE
  │      └── File Tool → Evidence Synthesis
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

Design goals:
- Deterministic tools remain deterministic.
- Search/File use evidence synthesis.
- Complex tasks collect targeted evidence first.
- Important claims should have an evidence path.
- Observable trace is available.
- Raw evidence can be inspected.
- Tool parameters are validated.
- Existing tool APIs remain unchanged.

Important:
The trace records observable processing states,
evidence, decisions and outputs.

It does NOT expose private model chain-of-thought.
"""

import json

from llm import LLM
from planner import Planner
from memory import Memory
from protocol import Action
from council import Council

from tools.search import SearchTool
from tools.calculator import CalculatorTool
from tools.file import FileTool


class Agent:

    def __init__(self):

        self.llm = LLM()
        self.memory = Memory()
        self.planner = Planner(self.llm)
        self.council = Council(self.llm)

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

        # =================================================
        # OBSERVABLE TRACE
        # =================================================

        self.trace_enabled = True
        self.trace_events = []

    # =====================================================
    # TRACE
    # =====================================================

    def trace(
        self,
        step,
        phase,
        message,
        data=None
    ):
        """
        Record an observable processing state.

        This is not private chain-of-thought.
        """

        event = {
            "step": step,
            "phase": phase,
            "message": message,
        }

        if data is not None:
            event["data"] = data

        self.trace_events.append(event)

        if not self.trace_enabled:
            return

        print(
            "\n"
            "┌──────────────────────────────────────────────┐",
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

        for line in str(message).splitlines():
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

                text = str(data)

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
        """
        Reset trace for a new request.
        """

        self.trace_events = []

    def get_trace(self):
        """
        Return structured trace.
        """

        return list(
            self.trace_events
        )

    # =====================================================
    # MAIN ASK
    # =====================================================

    def ask(
        self,
        question
    ):

        self.reset_trace()

        # -------------------------------------------------
        # MEMORY
        # -------------------------------------------------

        self.memory.add(
            "user",
            question
        )

        history = self.memory.messages()

        evidence = []

        # =================================================
        # 01 — UNDERSTAND
        # =================================================

        self.trace(
            1,
            "UNDERSTAND",
            "Xác định câu hỏi đầu vào.",
            {
                "question": question
            }
        )

        # =================================================
        # 02 — CLASSIFY
        # =================================================

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

        # =================================================
        # ANSWER
        # =================================================

        if call.action == Action.ANSWER:

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
                            "Nếu không chắc chắn, hãy nói rõ."
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

            return

        # =================================================
        # COMPLEX
        # =================================================

        if call.action == Action.COMPLEX:

            self.trace(
                3,
                "TASK LOCK",
                "Task được xác định là COMPLEX.",
                {
                    "reason": (
                        "Complex task requires "
                        "targeted evidence before reasoning."
                    )
                }
            )

            print(
                "\n🌐 Complex task: "
                "thu thập evidence...",
                flush=True
            )

            # -------------------------------------------------
            # BUILD QUERIES
            # -------------------------------------------------

            queries = self.build_complex_queries(
                question
            )

            self.trace(
                4,
                "EVIDENCE PLAN",
                "Các truy vấn evidence được tạo.",
                {
                    "query_count": len(queries),
                    "queries": queries
                }
            )

            print(
                f"🔎 Evidence queries: "
                f"{len(queries)}",
                flush=True
            )

            # -------------------------------------------------
            # SEARCH
            # -------------------------------------------------

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

                    evidence_item = {
                        "query": query,
                        "result": result
                    }

                    evidence.append(
                        evidence_item
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

                except Exception as e:

                    self.trace(
                        6,
                        "EVIDENCE ERROR",
                        f"Search {index} failed.",
                        {
                            "query": query,
                            "error": str(e)
                        }
                    )

                    print(
                        f"   ❌ Search failed: {e}",
                        flush=True
                    )

                    evidence.append(
                        {
                            "query": query,
                            "result": {
                                "success": False,
                                "source": "Search",
                                "query": query,
                                "error": str(e),
                                "results": []
                            }
                        }
                    )

            print(
                "\n✅ Evidence acquisition "
                "hoàn tất",
                flush=True
            )

            print(
                f"📦 Evidence sets: "
                f"{len(evidence)}",
                flush=True
            )

            # =================================================
            # 07 — EVIDENCE SUMMARY
            # =================================================

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

            # =================================================
            # RAW EVIDENCE
            # =================================================

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

            # =================================================
            # COUNCIL
            # =================================================

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

            return

        # =================================================
        # TOOL VALIDATION
        # =================================================

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

        # =================================================
        # TOOL ROUTING
        # =================================================

        self.trace(
            3,
            "TOOL ROUTING",
            "Task được route sang deterministic tool.",
            {
                "action": call.action.value,
                "parameters": call.parameters
            }
        )

        print(
            "🌐 Tool đang chạy...",
            flush=True
        )

        try:

            result = self.execute_tool(
                call.action,
                call.parameters
            )

        except Exception as e:

            answer = (
                f"Tool execution failed: {e}"
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

        # -------------------------------------------------
        # IMPORTANT DATA CONTRACT
        #
        # Search/File evidence is wrapped as:
        #
        # {
        #     "query": "...",
        #     "result": {
        #         ...
        #     }
        # }
        # -------------------------------------------------

        evidence.append(
            {
                "query": call.parameters.get(
                    "query",
                    ""
                ),
                "result": result
            }
        )

        self.trace(
            4,
            "TOOL RESULT",
            "Tool execution hoàn tất."
        )

        print(
            "✅ Tool hoàn tất",
            flush=True
        )

        # =================================================
        # CALCULATOR
        # =================================================

        if call.action == Action.CALCULATOR:

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

        # =================================================
        # SEARCH / FILE
        # =================================================

        if call.action in (
            Action.SEARCH,
            Action.FILE
        ):

            print(
                "\n🤖 Qwen đang tổng hợp "
                "evidence...",
                flush=True
            )

            self.trace(
                5,
                "EVIDENCE SYNTHESIS",
                "Evidence được gửi tới Qwen để tổng hợp."
            )

            # -------------------------------------------------
            # DEBUG RAW EVIDENCE
            # -------------------------------------------------

            self.debug_raw_evidence(
                evidence
            )

            # -------------------------------------------------
            # SYNTHESIS
            # -------------------------------------------------

            answer = self.synthesize_evidence(
                question,
                evidence
            )

            self.trace(
                6,
                "FINAL ANSWER",
                "Evidence synthesis hoàn tất."
            )

            yield answer

            self.memory.add(
                "assistant",
                answer
            )

            return

        raise ValueError(
            f"Unhandled action: "
            f"{call.action}"
        )

    # =====================================================
    # RAW EVIDENCE DEBUG
    # =====================================================

    def debug_raw_evidence(
        self,
        evidence
    ):
        """
        Print actual tool evidence.

        This function does not:
        - modify evidence
        - summarize evidence
        - call LLM
        - make decisions
        """

        print(
            "\n"
            "============================================================",
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

        if not isinstance(
            evidence,
            list
        ):

            print(
                "❌ Evidence is not a list",
                flush=True
            )

            print(
                f"TYPE: "
                f"{type(evidence).__name__}",
                flush=True
            )

            return

        for index, item in enumerate(
            evidence,
            start=1
        ):

            print(
                f"\n--- EVIDENCE {index} ---",
                flush=True
            )

            if not isinstance(
                item,
                dict
            ):

                print(
                    f"TYPE: "
                    f"{type(item).__name__}",
                    flush=True
                )

                print(
                    f"VALUE: {item}",
                    flush=True
                )

                continue

            print(
                f"EVIDENCE ID: "
                f"EVIDENCE_{index}",
                flush=True
            )

            query = item.get(
                "query",
                ""
            )

            print(
                f"QUERY: {query}",
                flush=True
            )

            result = item.get(
                "result",
                {}
            )

            if not isinstance(
                result,
                dict
            ):

                print(
                    "RESULT TYPE: "
                    f"{type(result).__name__}",
                    flush=True
                )

                print(
                    f"RESULT: {result}",
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

            if result.get(
                "error"
            ):

                print(
                    f"ERROR: "
                    f"{result.get('error')}",
                    flush=True
                )

            raw_results = result.get(
                "results",
                []
            )

            if isinstance(
                raw_results,
                list
            ):

                print(
                    f"RESULT COUNT: "
                    f"{len(raw_results)}",
                    flush=True
                )

                for result_index, search_item in enumerate(
                    raw_results[:5],
                    start=1
                ):

                    print(
                        f"\nRESULT {result_index}",
                        flush=True
                    )

                    if not isinstance(
                        search_item,
                        dict
                    ):

                        print(
                            f"TYPE: "
                            f"{type(search_item).__name__}",
                            flush=True
                        )

                        print(
                            f"VALUE: "
                            f"{search_item}",
                            flush=True
                        )

                        continue

                    print(
                        "TITLE: "
                        f"{search_item.get('title', '')}",
                        flush=True
                    )

                    print(
                        "URL: "
                        f"{search_item.get('url', '')}",
                        flush=True
                    )

                    print(
                        "CONTENT:",
                        flush=True
                    )

                    print(
                        str(
                            search_item.get(
                                "content",
                                ""
                            )
                        ),
                        flush=True
                    )

            else:

                print(
                    "STRUCTURED RESULT:",
                    flush=True
                )

                for key, value in result.items():

                    if key == "results":
                        continue

                    print(
                        f"{key}: {value}",
                        flush=True
                    )

        print(
            "\n"
            "============================================================",
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

    # =====================================================
    # COMPLEX QUERY DECOMPOSITION
    # =====================================================

    def build_complex_queries(
        self,
        question
    ):
        """
        Generate targeted evidence queries.

        Important:
        Independent factual claims should have independent
        evidence paths.
        """

        q = question.lower()

        queries = []

        # =================================================
        # DATABASE DETECTION
        # =================================================

        database_keywords = [
            "postgresql",
            "postgres",
            "sqlite",
            "mysql",
            "mariadb",
            "database",
            "transaction",
            "transactions",
            "concurrency",
            "concurrent",
            "locking",
            "lock",
            "isolation",
            "savepoint",
        ]

        is_database_question = any(
            keyword in q
            for keyword in database_keywords
        )

        if is_database_question:

            # -------------------------------------------------
            # PostgreSQL
            # -------------------------------------------------

            if (
                "postgresql" in q
                or "postgres" in q
            ):

                queries.append(
                    "PostgreSQL transaction isolation concurrency locking official documentation"
                )

            # -------------------------------------------------
            # SQLite
            # -------------------------------------------------

            if "sqlite" in q:

                queries.append(
                    "SQLite transactions isolation concurrency locking official documentation"
                )

            # -------------------------------------------------
            # SAVEPOINT
            # -------------------------------------------------

            if "savepoint" in q:

                if "sqlite" in q:

                    queries.append(
                        "SQLite SAVEPOINT official documentation"
                    )

                if (
                    "postgresql" in q
                    or "postgres" in q
                ):

                    queries.append(
                        "PostgreSQL SAVEPOINT official documentation"
                    )

            # -------------------------------------------------
            # Concurrent writes / comparison
            # -------------------------------------------------

            if (
                "concurrent" in q
                or "concurrency" in q
                or "performance" in q
                or "hiệu năng" in q
                or "warehouse" in q
                or "kho" in q
                or "vs" in q
                or "so sánh" in q
                or "nên chọn" in q
            ):

                if (
                    "postgresql" in q
                    and "sqlite" in q
                ):

                    queries.append(
                        "PostgreSQL vs SQLite concurrent writes performance workload comparison"
                    )

            # -------------------------------------------------
            # Deduplicate
            # -------------------------------------------------

            queries = list(
                dict.fromkeys(
                    queries
                )
            )

            if queries:
                return queries

        # =================================================
        # GENERIC COMPLEX FALLBACK
        # =================================================

        return [
            question
        ]

    # =====================================================
    # FORMAT COMPLEX EVIDENCE
    # =====================================================

    def format_complex_evidence(
        self,
        evidence
    ):
        """
        Normalize evidence for Council.

        Input:

            {
                "query": "...",
                "result": {
                    "success": true,
                    "source": "...",
                    "results": [...]
                }
            }

        Output contains explicit evidence IDs.
        """

        compact_evidence = []

        for index, item in enumerate(
            evidence,
            start=1
        ):

            if not isinstance(
                item,
                dict
            ):
                continue

            evidence_id = (
                f"EVIDENCE_{index}"
            )

            query = str(
                item.get(
                    "query",
                    ""
                )
            )[:500]

            result = item.get(
                "result",
                {}
            )

            if not isinstance(
                result,
                dict
            ):
                continue

            compact_result = {
                "evidence_id": evidence_id,
                "query": query,
                "success": result.get(
                    "success",
                    False
                ),
                "source": result.get(
                    "source",
                    ""
                )
            }

            # -------------------------------------------------
            # Search results
            # -------------------------------------------------

            raw_results = result.get(
                "results",
                []
            )

            if isinstance(
                raw_results,
                list
            ):

                compact_results = []

                for result_index, search_result in enumerate(
                    raw_results[:5],
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
                                f"{evidence_id}_R"
                                f"{result_index}"
                            ),
                            "title": str(
                                search_result.get(
                                    "title",
                                    ""
                                )
                            )[:300],
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
                            )[:2000]
                        }
                    )

                compact_result[
                    "results"
                ] = compact_results

            # -------------------------------------------------
            # Structured fields
            # -------------------------------------------------

            for key, value in result.items():

                if key in (
                    "success",
                    "source",
                    "results"
                ):
                    continue

                if key == "content":

                    compact_result[key] = str(
                        value
                    )[:3000]

                else:

                    compact_result[key] = value

            compact_evidence.append(
                compact_result
            )

        return json.dumps(
            compact_evidence,
            ensure_ascii=False,
            indent=2
        )

    # =====================================================
    # TOOL EXECUTION
    # =====================================================

    def execute_tool(
        self,
        action,
        parameters
    ):

        if action not in self.tools:

            raise ValueError(
                f"Unknown tool action: "
                f"{action}"
            )

        if not isinstance(
            parameters,
            dict
        ):

            raise TypeError(
                "Tool parameters must be dict, "
                f"got {type(parameters).__name__}"
            )

        required = (
            self.tool_required_parameters.get(
                action,
                []
            )
        )

        # -------------------------------------------------
        # Missing parameters
        # -------------------------------------------------

        missing = [
            key
            for key in required
            if key not in parameters
        ]

        if missing:

            raise ValueError(
                f"Invalid parameters for "
                f"{action.value}: "
                f"missing={missing}, "
                f"received={list(parameters.keys())}"
            )

        # -------------------------------------------------
        # Unknown parameters
        # -------------------------------------------------

        allowed = set(
            required
        )

        unknown = [
            key
            for key in parameters
            if key not in allowed
        ]

        if unknown:

            raise ValueError(
                f"Invalid parameters for "
                f"{action.value}: "
                f"unknown={unknown}, "
                f"allowed={required}"
            )

        # -------------------------------------------------
        # Execute
        # -------------------------------------------------

        return self.tools[
            action
        ].run(
            **parameters
        )

    # =====================================================
    # EVIDENCE SYNTHESIS
    # =====================================================

    def synthesize_evidence(
        self,
        question,
        evidence
    ):
        """
        Normalize evidence and ask Qwen to synthesize.

        Critical data contract:

            evidence
                ↓
            item["result"]
                ↓
            result["results"]

        NOT:

            item["results"]

        This fixes the previous evidence extraction bug.
        """

        compact_evidence = []

        # =================================================
        # NORMALIZE EVIDENCE
        # =================================================

        for index, item in enumerate(
            evidence,
            start=1
        ):

            if not isinstance(
                item,
                dict
            ):
                continue

            evidence_id = (
                f"EVIDENCE_{index}"
            )

            query = str(
                item.get(
                    "query",
                    ""
                )
            )[:500]

            # =================================================
            # TOOL WRAPPER
            # =================================================

            if "result" in item:

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
                    "evidence_id": evidence_id,
                    "query": query,
                    "success": result.get(
                        "success",
                        False
                    ),
                    "source": result.get(
                        "source",
                        ""
                    )
                }

                # -------------------------------------------------
                # CORRECT SEARCH RESULT EXTRACTION
                # -------------------------------------------------

                raw_results = result.get(
                    "results",
                    []
                )

                if isinstance(
                    raw_results,
                    list
                ):

                    compact_results = []

                    for result_index, search_result in enumerate(
                        raw_results[:5],
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
                                    f"{evidence_id}_R"
                                    f"{result_index}"
                                ),
                                "title": str(
                                    search_result.get(
                                        "title",
                                        ""
                                    )
                                )[:300],
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
                                )[:2000]
                            }
                        )

                    compact_item[
                        "results"
                    ] = compact_results

                # -------------------------------------------------
                # Other structured fields
                # -------------------------------------------------

                for key, value in result.items():

                    if key in (
                        "success",
                        "source",
                        "results"
                    ):
                        continue

                    if key == "content":

                        compact_item[key] = str(
                            value
                        )[:5000]

                    else:

                        compact_item[key] = value

                compact_evidence.append(
                    compact_item
                )

                continue

            # =================================================
            # FALLBACK DIRECT EVIDENCE
            # =================================================

            compact_item = {
                "evidence_id": evidence_id
            }

            for key, value in item.items():

                if key == "content":

                    compact_item[key] = str(
                        value
                    )[:5000]

                else:

                    compact_item[key] = value

            compact_evidence.append(
                compact_item
            )

        # =================================================
        # SERIALIZE
        # =================================================

        evidence_text = json.dumps(
            compact_evidence,
            ensure_ascii=False,
            indent=2
        )

        # =================================================
        # DEBUG
        # =================================================

        print(
            "\n"
            "============================================================",
            flush=True
        )

        print(
            "EVIDENCE SYNTHESIS INPUT",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        print(
            evidence_text,
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        print(
            f"Evidence gửi Qwen: "
            f"{len(evidence_text)} ký tự",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        # =================================================
        # SYNTHESIS PROMPT
        # =================================================

        system_prompt = """
Bạn là BCOS Evidence Synthesizer.

NHIỆM VỤ:

Trả lời câu hỏi của người dùng dựa trên evidence
được cung cấp.

==================================================
QUY TRÌNH
==================================================

1. Đọc câu hỏi.

2. Xác định factual claim mà câu hỏi yêu cầu.

3. Đọc từng evidence.

4. Tìm evidence thực sự liên quan tới claim.

5. Nếu câu hỏi có năm hoặc mốc thời gian,
   phải chú ý thời gian của evidence.

6. Phân biệt evidence mới và evidence cũ.

7. Nếu nhiều evidence phù hợp cùng xác nhận
   một claim, có thể kết luận.

8. Nếu một evidence cũ nói A nhưng nhiều evidence
   mới nói B cho cùng mốc thời gian, ưu tiên
   evidence phù hợp với mốc thời gian câu hỏi.

9. Không biến absence of evidence thành
   evidence of absence.

10. Không sử dụng kiến thức bên ngoài evidence.

11. Không bịa dữ liệu.

12. Không yêu cầu một kết quả tìm kiếm phải chứa
    nguyên văn toàn bộ câu trả lời.

13. Khi nhiều evidence độc lập cùng xác nhận
    một factual claim, có thể tổng hợp chúng.

==================================================
QUY TẮC THỜI GIAN
==================================================

Nếu câu hỏi hỏi một sự kiện hoặc trạng thái
ở một năm cụ thể, hãy ưu tiên evidence có:

- ngày tháng phù hợp;
- nội dung nói trực tiếp về năm đó;
- nguồn mới hơn;
- nhiều nguồn độc lập cùng xác nhận.

Ví dụ:

Câu hỏi:
"ai là tổng thống Mỹ 2026"

Nếu evidence cũ nói Joe Biden nhưng các evidence
phù hợp với năm 2026 nói Donald Trump là Tổng thống
Mỹ, không được kết luận Joe Biden chỉ vì kết quả cũ.

==================================================
QUY TẮC EPISTEMIC
==================================================

FACT:
Chỉ ghi fact được evidence hỗ trợ.

INFERENCE:
Nếu phải suy luận từ nhiều evidence,
hãy ghi rõ đó là inference.

UNKNOWN:
Chỉ dùng khi evidence thực sự không đủ.

Không được dùng UNKNOWN chỉ vì không có một
nguồn duy nhất chứa toàn bộ câu trả lời.

==================================================
FORMAT
==================================================

FACT:
- <fact>

EVIDENCE:
- <evidence_id>/<result_id>: <lý do hỗ trợ fact>

ANSWER:
<câu trả lời trực tiếp>

Nếu thực sự không đủ evidence:

UNKNOWN:
- <thông tin còn thiếu>

ANSWER:
Chưa đủ bằng chứng để kết luận.
"""

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": (
                    f"Câu hỏi:\n"
                    f"{question}\n\n"
                    f"Evidence:\n"
                    f"{evidence_text}"
                )
            }
        ]

        # =================================================
        # CALL QWEN
        # =================================================

        return self.llm.chat(
            messages
        )

    # =====================================================
    # CALCULATOR FORMAT
    # =====================================================

    def format_calculator_result(
        self,
        result
    ):

        if not isinstance(
            result,
            dict
        ):

            return str(result)

        if result.get(
            "success"
        ):

            expression = result.get(
                "expression",
                ""
            )

            value = result.get(
                "result"
            )

            return (
                f"{expression} = {value}"
            )

        error = result.get(
            "error",
            "Unknown calculator error"
        )

        return (
            f"Không thể tính biểu thức: "
            f"{error}"
        )