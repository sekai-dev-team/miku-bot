# Miku-Bot 全量上下文与 DeepSeek 缓存实施方案 (Phase 1)

## 1. 目标 (Objectives)
构建基于 **DeepSeek 硬盘缓存 (Prefix Caching)** 的全量上下文记忆系统。
- **短期目标**：移除固定条数限制，利用 128k 长窗口保留完整对话语境。
- **核心机制**：客户端存储全量历史，服务端利用缓存进行增量计算。
- **限制**：暂不引入“摘要压缩”或“智能去噪”，仅依靠 Token 上限作为安全阀。

## 2. 核心概念澄清
DeepSeek 的 **Prefix Caching** 允许系统在两次请求前缀相同时，跳过前缀部分的计算。
- **Request 1**: `[System, A, B]` -> 计算 A, B -> 存入缓存
- **Request 2**: `[System, A, B, C]` -> 发现 `[System, A, B]` 已缓存 -> 直接读取 -> **仅计算 C**
- **效果**: 虽然仅计算 C，但模型**依然“看得到”且“理解” A 和 B**。

## 3. 模块变更详情

### 3.1 新增：Token 估算器 (`src/common/token_utils.py`)
由于没有本地模型文件，采用保守的启发式估算策略。

- **`estimate_token(text: str) -> int`**:
  - 算法：`len(text) * (0.7 if is_cjk else 0.4)`
  - 目的：提供低成本的 Token 计数。
- **`estimate_messages_token(messages: list) -> int`**:
  - 算法：`sum(estimate_token(msg['content']) for msg in messages) + len(messages) * 4`
  - 目的：估算整个 Payload 的大小，包含 JSON 结构开销。

### 3.2 重构：消息上下文管理器 (`src/plugins/chat/msg_context.py`)
将定长队列 `deque` 改造为受 Token 限制的动态列表。

- **类名**: `FullContextManager` (替代 `SimulatedGroupMsgListener`)
- **数据结构**: 
  - `_storage`: `Dict[group_id, List[Dict]]` (存储完整的 `{"role":.., "content":..}` 列表)
  - `_max_tokens`: `int` (默认设定安全阈值，如 60k 或 100k)
- **核心方法**:
  - `append(group_id, msg)`: 
    - 追加消息。
    - 触发 Token 检查：若总 Token > `_max_tokens`，执行 **FIFO (先进先出)** 移除最早的 User/Assistant 消息，直到合规。
  - `get_context(group_id)`:
    - 返回用于 API 调用的完整列表。

### 3.3 逻辑流：确保缓存命中 (Cache Hit Strategy)
为了最大化利用 DeepSeek 缓存，必须严格保证 `messages` 列表头部的稳定性。

- **Payload 结构**:
  1.  **System Prompt** (静态，永不改变，确保 100% 缓存基底)
  2.  **Historical Messages** (只追加，不修改。A, B, C...)
  3.  **New Message** (当前输入)

*注意*：避免在 System Prompt 中插入动态时间戳。若需要时间感知，将时间戳放入每一轮 User 消息的末尾或开头，而非 System Prompt。

## 4. 实施步骤
1.  **创建** `src/common/token_utils.py`。
2.  **备份** 原 `src/plugins/chat/msg_context.py`。
3.  **重写** `src/plugins/chat/msg_context.py` 实现 `FullContextManager`。
4.  **测试**：模拟长文本输入，验证 Token 计算与 FIFO 丢弃逻辑。
5.  **集成**：确保 API 调用端正确传入全量列表。
