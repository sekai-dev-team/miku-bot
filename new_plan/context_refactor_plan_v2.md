# Miku-Bot 上下文重构方案 V2 (A/B/C 结构)

## 1. 核心理念
采用 **"Session-based Batching" (基于会话的批处理)** 模式，严格区分“待处理消息”与“已归档历史”，确保多轮对话的逻辑清晰性与互斥性。

## 2. 数据结构定义

### 2.1 结构 A: Pending Buffer (待处理区)
- **定义**: 临时存放自上一次 AI 响应以来，群内产生的所有新消息。
- **形态**: `List[str]` (或简单的对象列表)
- **生命周期**: 
  - 群友发言 -> `append` 到 A。
  - AI 触发请求 -> A 被打包发送 -> A 被清空。
- **互斥性**: A 中的内容永远是**新**的，从未被 AI "消化"过。

### 2.2 结构 B: Committed History (已归档历史)
- **定义**: 存储 AI 已经处理过的对话历史（作为 DeepSeek 缓存的前缀）。
- **形态**: `List[Dict]` (OpenAI 格式: `[{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]`)
- **生命周期**:
  - 长期驻留内存。
  - AI 响应完成后，(打包后的 A) 和 (AI 回复) 会被追加到 B。
  - 受 Token 水位线控制，执行 FIFO 淘汰。

### 2.3 结构 C: Payload (最终载荷)
- **定义**: 发送给 API 的完整请求体。
- **构造公式**: `C = System_Prompt + B + User(Merge(A))`

## 3. 模块设计

### 3.1 Token 估算器 (`src/common/token_utils.py`)
- 提供 `estimate_token` 和 `estimate_messages_token` 函数。
- 即使在 A/B 结构下，我们也需要计算 B 的大小，以决定何时进行 FIFO 清理。

### 3.2 上下文管理器 (`src/plugins/chat/msg_context.py`)

#### 类: `FullContextManager`
- **属性**:
  - `_pending_buffer`: `Dict[group_id, List[str]]`  **(对应结构 A)**
  - `_committed_history`: `Dict[group_id, List[Dict]]` **(对应结构 B)**
  - `_max_tokens`: `int` (高水位线，如 100k)
  - `_min_tokens`: `int` (低水位线，如 70k)

- **方法**:
  - `append_msg(group_id, msg)`:
    - 将消息直接存入 `_pending_buffer[group_id]`。
  
  - `get_context_and_commit(group_id) -> List[Dict]`:
    - **这是关键变更点**。为了保证状态一致性，获取上下文时通常意味着“即将发送请求”。
    - **Step 1 (Merge)**: 将 `_pending_buffer` 中的所有文本合并为一个大段落 `merged_user_content`。
    - **Step 2 (Construct)**: 构造临时请求列表 `request_msgs = System + _committed_history + [{"role": "user", "content": merged_user_content}]`。
    - **注意**: 此时**不**清空 buffer，因为 API 请求可能失败。Buffer 的清空和 History 的追加应在 API **成功响应后**进行。
  
  - `commit_transaction(group_id, merged_user_content, ai_response)`:
    - **调用时机**: API 成功返回后。
    - **动作 1**: 将 `{"role": "user", "content": merged_user_content}` 追加到 `_committed_history`。
    - **动作 2**: 将 `{"role": "assistant", "content": ai_response}` 追加到 `_committed_history`。
    - **动作 3**: 清空 `_pending_buffer`。
    - **动作 4**: 检查 `_committed_history` 的 Token 总量。如果超过高水位线，执行批量 FIFO 淘汰直至低水位线。

## 4. 业务流程图解

1.  **Idle**: 群友 A 发言 -> `PendingBuffer.append("User A: ...")`
2.  **Idle**: 群友 B 发言 -> `PendingBuffer.append("User B: ...")`
3.  **Trigger**: 触发 `@Miku`
4.  **Prepare**:
    - `merged_content` = "User A: ...\nUser B: ..."
    - `payload` = `System` + `History` + `User(merged_content)`
5.  **Request**: 发送 `payload` 给 DeepSeek。
6.  **Response**: 收到 "Miku: 大家好"。
7.  **Commit**:
    - `History.append(User(merged_content))`
    - `History.append(Assistant("Miku: 大家好"))`
    - `PendingBuffer.clear()`
    - `Prune`: 检查 History 大小并清理。

## 5. 待办事项
1.  创建 `src/common/token_utils.py`。
2.  重写 `src/plugins/chat/msg_context.py` 实现上述逻辑。
3.  更新 `src/plugins/chat/handlers/chat.py` 适配新的 `get_context` 和 `commit` 接口。
