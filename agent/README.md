# BCOS Agent

Evidence-first agent trên Ollama (`qwen2.5:3b`).

Kiến trúc: xem [`../Architecture.md`](../Architecture.md).

---

## 1. Yêu cầu

| Thành phần | Ghi chú |
| --- | --- |
| Python | ≥ 3.10 (dùng `str \| ProblemInput` syntax) |
| Ollama | chạy tại `http://127.0.0.1:11434` |
| Model | `ollama pull qwen2.5:3b` |
| Network | DuckDuckGo + CoinGecko cho `SearchTool` |

```bash
pip install -r agent/requirements.txt
```

---

## 2. Chạy

```bash
python agent/main.py
```

Chạy được từ bất kỳ working directory nào. Các module BCOS import
phẳng (`from llm import LLM`), nên `main.py` tự thêm thư mục nguồn
vào `sys.path`.

`python -m agent.main` **không** dùng được: `agent` khi đó phân giải
thành namespace package của thư mục, không phải `agent/agent.py`.

---

## 3. Runtime paths

Mọi resource được phân giải theo thư mục nguồn (`agent/paths.py`),
**không** theo working directory:

| Resource | Đường dẫn |
| --- | --- |
| System prompt | `agent/prompts/bcos.txt` |
| Conversation memory | `agent/history/conversation.json` |
| File tool sandbox | `agent/data/` |
| Logs | `agent/logs/` |

---

## 4. Test

Cả hai suite đều offline — không gọi Ollama, không gọi network.

```bash
python tests/test_evidence_verifier.py     # EvidenceVerifier
python tests/test_regressions.py           # routing, paths, sandbox
cd agent && python test_problem.py         # planner routing
```

Hai suite trong `tests/` chạy được từ project root và tự thêm `agent/`
vào `sys.path`.

`agent/test_search.py` **cần network** (không phải unit test).

---

## 5. Pipeline

```
question
   │
   ▼
Planner ── ProblemReconstructor → ProblemClassifier
   │
   ├── CALCULATOR ─────────────► CalculatorTool
   ├── FILE ───────────────────► FileTool (sandbox: agent/data)
   ├── SEARCH ─────────────────► SearchTool → EvidenceVerifier
   │                                              │
   │                             SUPPORTED / CONTRADICTED /
   │                             CONFLICTED / INSUFFICIENT
   │                                              │
   │                                    deterministic answer
   │
   └── COMPLEX ────────────────► Council
                                 (Reasoning + Critic + Judge)
```

Thứ tự routing trong `Planner.plan()`:

1. Model-based (theo `ProblemType`) — gồm `FACT_LOOKUP → SEARCH`
2. Deterministic keyword fallback
3. LLM planner fallback

Model-based **phải** chạy trước keyword fallback, nếu không một câu
`fact_lookup` chứa keyword "complex" (locking, transaction,
concurrency…) sẽ bị route sang `COMPLEX` và trả lời bằng model memory
thay vì đi lấy evidence.
