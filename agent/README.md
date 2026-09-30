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
| Conversation memory | `agent/history/conversation.json` (untracked — runtime state) |
| File tool sandbox | `agent/data/` |
| Logs | `agent/logs/agent.log` (untracked) |

---

## 4. Test

Cả hai suite đều offline — không gọi Ollama, không gọi network.

```bash
python tests/test_evidence_verifier.py     # EvidenceVerifier
python tests/test_regressions.py           # routing, paths, sandbox
python tests/test_evidence_chain.py        # evidence chain end-to-end
cd agent && python test_problem.py         # planner routing
```

Ba suite trong `tests/` chạy được từ project root và tự thêm `agent/`
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
2. Deterministic: FILE → CALCULATOR → SEARCH → COMPLEX
3. LLM planner fallback

Model-based **phải** chạy trước keyword fallback, nếu không một câu
`fact_lookup` chứa keyword "complex" (locking, transaction,
concurrency…) sẽ bị route sang `COMPLEX` và trả lời bằng model memory
thay vì đi lấy evidence.

Hai guard giữ cho tool không bị gọi sai:

| Guard | Ngăn điều gì |
| --- | --- |
| `is_arithmetic_expression()` | `"dân số Việt Nam bao nhiêu"` bị classify là CALCULATION → CalculatorTool nhận tiếng Việt → `invalid syntax` |
| `extract_file_path()` allowlist extension | `sqlite.org`, `python 3.11.15`, URL bị nhận là file |

---

## 6. Retrieval health

Mọi tool trả về cùng một envelope:

```
{success, source, data_type, query, count, results, error?}
```

`results` là kênh **duy nhất** `EvidenceVerifier` đọc. Payload có cấu
trúc riêng (FileTool, CoinGecko) được `Agent.as_verifiable_result()`
bọc lại thành một `results` entry — nếu không chúng bị drop trong im
lặng và user nghe "evidence chưa đủ" về đúng dữ liệu vừa lấy được.

Ba trạng thái **không** được lẫn vào nhau:

| Trạng thái | Câu trả lời |
| --- | --- |
| tool lỗi (`success=False`) | `describe_tool_failure()` — nêu tên tool và lỗi |
| tool ok nhưng 0 kết quả | `describe_retrieval_failure()` — nêu các query |
| có evidence, không support claim | `EvidenceVerifier` → INSUFFICIENT |

COMPLEX có zero-evidence guard: 0 kết quả thì **bỏ qua Council** thay
vì tiêu 3 LLM call để Judge bịa một câu trả lời "Độ tin cậy: CAO".

---

## 7. Logging

`agent/logs/agent.log`, cấu hình trong `agent/log.py`. Mọi degradation
(planner fallback, tool exception, memory load lỗi) đều ghi traceback
vào đây. Trước đó repo không có một dòng logging nào, nên một
`TypeError` làm chết toàn bộ pipeline chỉ biểu hiện thành "không search
được".
