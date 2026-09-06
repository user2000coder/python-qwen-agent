
# BCOS Architecture v1.0

## 1. Mục tiêu

BCOS (Behavioral Cognitive Operating System) là một Agent Framework được thiết kế để:

* Hiểu mục tiêu của người dùng.
* Lập kế hoạch giải quyết.
* Thực thi từng bước.
* Gọi công cụ (Tool).
* Quan sát kết quả.
* Điều chỉnh kế hoạch khi cần.
* Sinh câu trả lời cuối cùng.
* Học từ kinh nghiệm thông qua Memory và Reflection.

BCOS không chỉ là một chatbot mà là một hệ thống điều phối (orchestrator) cho quá trình suy luận và thực thi.

---

# 2. Kiến trúc tổng thể

```
                  User
                    │
                    ▼
            Input Processing
                    │
                    ▼
             Intent Analysis
                    │
                    ▼
                Planner
                    │
                    ▼
              Execution Plan
                    │
                    ▼
               Executor Loop
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
     Tool Manager          Reasoner
         │                     │
         └──────────┬──────────┘
                    ▼
               Observation
                    │
                    ▼
               Reflection
                    │
                    ▼
                 Memory
                    │
                    ▼
          Response Generator
                    │
                    ▼
                 User
```

---

# 3. Core Principles

## Principle 1

Planner không thực thi.

Planner chỉ tạo kế hoạch.

---

## Principle 2

Executor không suy luận.

Executor chỉ thực hiện Task.

---

## Principle 3

Reasoner không gọi Tool trực tiếp.

Reasoner chỉ quyết định cần làm gì tiếp theo.

---

## Principle 4

Tool không biết gì về LLM.

Tool chỉ nhận Input và trả Output.

---

## Principle 5

Memory không điều khiển Agent.

Memory chỉ lưu và truy xuất tri thức.

---

## Principle 6

Mọi thành phần giao tiếp bằng Protocol thống nhất.

Không module nào phụ thuộc trực tiếp vào implementation của module khác.

---

# 4. Module Responsibilities

## Input Layer

Nhiệm vụ

* nhận yêu cầu
* chuẩn hóa
* tạo UserMessage

Output

```
UserMessage
```

---

## Planner

Input

```
Goal
```

Output

```
Plan
```

Bao gồm

* Goal
* Tasks
* Priority
* Dependency

Planner KHÔNG được:

* gọi Tool
* đọc File
* chạy Python

---

## Executor

Input

```
Plan
```

Output

```
Observation
```

Executor

* lấy Task tiếp theo
* giao cho Tool Manager
* nhận kết quả
* cập nhật trạng thái

Executor không tự lập kế hoạch.

---

## Tool Manager

Quản lý toàn bộ Tool.

Ví dụ

* Search
* Python
* File
* Browser
* Database
* API

Tool Manager quyết định Tool nào sẽ được gọi.

---

## Reasoner

Đánh giá

Quan sát hiện tại có đủ để tiếp tục không?

Nếu không

↓

đề xuất

* sửa kế hoạch
* thêm Task
* kết thúc

---

## Reflection

Sau mỗi Task

đánh giá

* thành công?
* thất bại?
* nguyên nhân?

Reflection không sinh câu trả lời.

---

## Memory

Gồm

### Short-term

Context của phiên làm việc.

### Episodic

Lưu trải nghiệm.

### Semantic

Lưu tri thức.

### Long-term

Lưu thông tin lâu dài.

---

## Response Generator

Sinh câu trả lời cuối cùng.

Không được phép

* gọi Tool
* sửa Memory

---

# 5. Protocol

Mọi module giao tiếp qua các object chuẩn.

```
UserMessage

Goal

Plan

Task

Action

ToolCall

ToolResult

Observation

Reflection

FinalResponse
```

Không sử dụng dict tự do giữa các module.

---

# 6. Agent State Machine

```
START

↓

UNDERSTAND

↓

PLAN

↓

EXECUTE

↓

OBSERVE

↓

REFLECT

↓

Need More?

├── YES → PLAN

└── NO

↓

RESPOND

↓

END
```

Mọi phiên làm việc đều đi qua các trạng thái này.

---

# 7. Execution Loop

```
while not finished:

    plan()

    execute()

    observe()

    reflect()

    update memory()
```

Không được

```
LLM

↓

Tool

↓

LLM

↓

Tool

↓

LLM

↓

Tool
```

một cách không kiểm soát.

---

# 8. Tool Calling Flow

```
Task

↓

Tool Manager

↓

Tool

↓

Result

↓

Observation

↓

Executor
```

Tool chỉ biết

Input

↓

Output

Không biết Planner hay Memory.

---

# 9. Memory Flow

```
Conversation

↓

Short Memory

↓

Reflection

↓

Long-term Memory
```

Không phải mọi thông tin đều được lưu.

Reflection quyết định điều gì đáng nhớ.

---

# 10. Failure Recovery

Nếu Tool lỗi

↓

Retry

↓

Fallback Tool

↓

Re-plan

↓

Fail Gracefully

Không để Agent dừng ngay khi Tool đầu tiên thất bại.

---

# 11. Design Constraints

* Single Responsibility cho từng module.
* Module giao tiếp qua Protocol.
* Không import vòng.
* Tool độc lập với LLM.
* Planner độc lập với Tool.
* Memory độc lập với Executor.
* State Machine là nguồn chân lý cho vòng đời Agent.
* Mọi quyết định quan trọng phải dựa trên Observation thay vì giả định.

---

# 12. Mục tiêu mở rộng

Kiến trúc phải cho phép bổ sung mà không cần sửa lõi:

* Multi-Agent.
* Song song nhiều Task.
* Tool động (plugin).
* Nhiều LLM backend.
* Memory backend khác nhau.
* Workflow tùy biến.
* Human-in-the-loop.
* Distributed Execution.
