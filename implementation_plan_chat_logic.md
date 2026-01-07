# Miku Bot 聊天核心改造方案 (Tool Use Implementation)

## 目标
改造 `src/plugins/chat/__init__.py` 中的核心对话逻辑，使其支持 "ReAct" (Reasoning + Acting) 模式。即：AI 思考 -> 决定调用工具 -> 执行代码 -> 观察结果 -> 生成最终回复。

## 核心挑战
1. **流式兼容性**：工具调用（Tool Calls）通常在非流式（Non-Stream）模式下处理更稳定，而普通聊天需要流式（Stream）以获得“打字机效果”。
2. **上下文注入**：工具（如查询黑历史）需要 `group_id`，但 AI 模型本身不知道当前的 QQ 群号，需要通过 System Prompt 注入。

## 改造步骤

### 1. 引入必要依赖
在 `src/plugins/chat/__init__.py` 中引入我们新写的工具注册中心：
```python
from src.common.tool_registry import tool_registry
```

### 2. 重构 System Prompt 注入逻辑
在构建 `messages` 列表时，动态插入环境上下文：
```python
# 伪代码
current_prompt = PROMPT_CONTENT + f"\n[Context]\nCurrent Group ID: {group_id}"
messages = [{"role": "system", "content": current_prompt}]
messages.extend(context) # 加上历史聊天记录
```

### 3. 实现“两段式”对话循环
我们将原来的单纯流式调用改为条件判断逻辑：

#### 第一阶段：意图探测 (Non-Stream)
*   **动作**：调用 `AIService.chat_completion`，参数 `stream=False`，并传入 `tools=tool_registry.get_tools()`。
*   **判断**：
    *   **情况 A (无工具调用)**：AI 直接返回了文本内容。
        *   *处理*：直接将文本发送给用户（为了体验，可以简单模拟流式发送或直接发送）。
    *   **情况 B (触发工具)**：AI 返回 `tool_calls`。
        *   *处理*：
            1. 解析函数名和参数（JSON）。
            2. 使用 `tool_registry.dispatch(name, args)` 执行对应的 Python 函数。
            3. 获取执行结果（通常是字符串）。
            4. 将 **Tool Call Message** (AI 想调用的工具) 和 **Tool Message** (工具返回的结果) 追加到 `messages` 列表中。
            5. **进入第二阶段**。

#### 第二阶段：结果生成 (Stream)
*   **前提**：只有在第一阶段触发了工具调用后，才会进入此阶段。
*   **动作**：再次调用 `AIService.chat_completion`，传入更新后的 `messages`。
    *   **关键点**：这次 **开启流式 (stream=True)**，并且 **不传入 tools** (防止死循环，或者 AI 再次尝试调用)。
*   **处理**：像以前一样，读取流式 Delta，实时推送给用户，形成“Miku 查完资料后在说话”的感觉。

## 预期代码结构变化

```python
# 旧逻辑
stream = await AIService.chat_completion(messages)
async for resp in stream:
    ...

# 新逻辑
# 1. 尝试触发工具 (关闭流式以确保解析稳定)
response = await AIService.chat_completion(messages, tools=tool_registry.get_tools(), stream=False)
msg = response.choices[0].message

if msg.tool_calls:
    # --- 工具调用分支 ---
    messages.append(msg) # 把 AI 的调用意图加进去
    
    for tool_call in msg.tool_calls:
        # 执行工具
        res = await tool_registry.dispatch(tool_call.function.name, json.loads(tool_call.function.arguments))
        # 把结果加进去
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": str(res)
        })
    
    # 2. 带着结果再次请求 AI (开启流式)
    stream = await AIService.chat_completion(messages, stream=True)
    async for resp in stream:
        # ... 常规流式输出逻辑 ...

else:
    # --- 普通闲聊分支 ---
    # 由于第一步关了流式，这里直接拿到了完整文本
    # 可以选择直接发送，或者为了统一体验，手动把文本切片发送
    content = msg.content
    await send_chunked(content) 
```

## 注意事项
1. **错误处理**：如果工具执行报错，需要把错误信息反馈给 AI，让 AI 决定如何解释，而不是直接抛出异常导致 Bot 沉默。
2. **Token 消耗**：工具调用会增加一次往返（Round-trip），消耗双倍的 Context Token，需注意 Token 上限（目前配置较高，应无大碍）。
