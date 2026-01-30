import asyncio
import re
import json
import base64
from pathlib import Path
from datetime import datetime

from nonebot import on_regex, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment

from src.common.ai_service import AIService
from src.common.tool_registry import tool_registry
from src.common.config_manager import config_manager
from src.common.memory_service import memory_service

from ..config import plugin_config as PLUGIN_CONFIG
from ..msg_context import LISTENER, SimulatedGroupMsg
from ..sentence_handler import SentenceBuffer
from ..utils import get_event_info

# Global lock
IS_CHATTING = False

# The Matcher
ai_chat = on_regex(
    r"^(miku,|miku，)|([,，]miku)$", flags=re.IGNORECASE, priority=1, block=False
)


@ai_chat.handle()
async def handle_chat(event: GroupMessageEvent):
    global IS_CHATTING

    splited_info, simulated_msg = get_event_info(event)
    sender_id = splited_info["sender_id"]
    group_id = splited_info["group_id"]

    # 1. Update Context (Append to Buffer A)
    LISTENER.listen(simulated_msg)

    # 2. Check Lock
    if IS_CHATTING:
        msg = Message(MessageSegment.at(sender_id).text(" 别急，等我先说完嘛"))
        await ai_chat.finish(msg)
    else:
        IS_CHATTING = True

    # 3. Initialize Buffer
    sb = SentenceBuffer()
    # 记录完整的 AI 回复，用于后续 Commit
    full_ai_response_for_commit = ""

    try:
        # 4. Prepare Context & Prompts
        user_input = event.get_plaintext().strip()
        logger.info(f"[ChatFlow] New User Input from {sender_id} in {group_id}: {user_input}")

        query_text = re.sub(
            r"^(miku,|miku，)|([,，]miku)$", "", user_input, flags=re.IGNORECASE
        ).strip()

        # 4.1 Retrieve Long-term Memory
        memory_context = await memory_service.retrieve_formatted_memory(
            str(sender_id), query_text
        )
        logger.info(f"[ChatFlow] Memory Retrieved: {len(memory_context) if memory_context else 0} chars")

        # 4.2 Build System Prompt
        system_prompt = _build_system_prompt(group_id, memory_context)

        # 4.3 Build Message History (Wait, this is now System + Committed History + Pending Buffer)
        # Note: We do NOT append System Prompt inside LISTENER, so we do it here.
        context_msgs = LISTENER.get_context_and_prepare_commit(group_id)
        
        # Check if there is anything to say (Buffer might be empty if just triggered?)
        # But even if buffer is empty, maybe previous context is enough? 
        # Usually buffer has at least the current triggering msg.
        
        messages = [{"role": PLUGIN_CONFIG.ROLE_SYSTEM, "content": system_prompt}]
        messages.extend(context_msgs)

        # Log the full payload structure summary
        payload_summary = [{"role": m.get("role"), "len": len(str(m.get("content", "")))} for m in messages]
        logger.info(f"[ChatFlow] Sending to AI. Payload structure: {payload_summary}")

        # 5. Core Chat Loop

        async def _send_text(text: str):
            for char in text:
                sentence = sb.append(char)
                if sentence:
                    # Remove "Miku:" prefix
                    sentence = re.sub(
                        r"^\s*Miku[:：]+\s*",
                        "",
                        sentence,
                        flags=re.IGNORECASE | re.MULTILINE,
                    ).strip()
                    if sentence:
                        sub_lines = [
                            s.strip() for s in sentence.split("\n") if s.strip()
                        ]
                        for sub_line in sub_lines:
                            await ai_chat.send(sub_line)
                            await asyncio.sleep(PLUGIN_CONFIG.SEND_INTERVAL)

        async def _process_stream_segment(segment: str):
            nonlocal full_ai_response_for_commit
            full_ai_response_for_commit += segment
            await _send_text(segment)

        # --- Stage 1: Intent Detection (Non-Stream) ---
        tools = tool_registry.get_tools()
        _log_payload({"messages": messages, "tools": tools}) # Log Full Payload
        
        response = await AIService.chat_completion(
            messages, tools=tools, stream=False
        )
        first_resp = response.choices[0].message
        logger.info(f"[ChatFlow] AI Initial Response: {first_resp}")

        if first_resp.tool_calls:
            # Case A: Tool Call Requested
            messages.append(first_resp)
            for tool_call in first_resp.tool_calls:
                logger.info(f"[ChatFlow] Executing Tool: {tool_call.function.name} with args {tool_call.function.arguments}")
                tool_result = await _execute_tool(tool_call)
                logger.info(f"[ChatFlow] Tool Result: {tool_result}")
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(tool_result),
                    }
                )
                print(str(tool_result))

            # --- Stage 2: Final Response (Stream) ---
            _log_payload({"messages": messages, "tools": tools, "stage": "after_tools"}) # Log Full Payload
            stream = await AIService.chat_completion(
                messages, tools=tools, stream=True
            )
            async for resp in stream:
                delta = resp.choices[PLUGIN_CONFIG.TOP_INDEX].delta
                if delta.content:
                    await _process_stream_segment(delta.content)

        else:
            # Case B: Direct Text Response
            if first_resp.content:
                await _process_stream_segment(first_resp.content)

        # 6. Finalize Output
        remain_text = sb.force_flush()
        if remain_text:
            remain_text = re.sub(
                r"^(Miku[:：])+", "", remain_text, flags=re.IGNORECASE
            ).strip()
            if remain_text:
                full_ai_response_for_commit += remain_text
                await ai_chat.send(remain_text)

        # 7. COMMIT TRANSACTION (The most important step for new context manager)
        # 必须确保 AI 回复不为空才提交，否则可能会丢失 User 消息但不记录 AI 回复？
        # 不，即使 AI 回复为空（罕见），User 的消息也应该被 Commit 进历史，否则就永久丢失了。
        # 但如果出错（Exception），则不 Commit，这样下次重试时 Buffer 还在。
        # 这里已经在 try 块的最后，说明没有 Exception。
        
        # Format the AI response properly for storage (Miku: content)
        # Note: The ContextManager expects just the content, it will format or store as Assistant role.
        # But wait, our previous logic for `_record_assistant_msg` was:
        # "Miku: content" -> Listener.listen -> which treats it as user msg? No. 
        
        # Old logic: `_record_assistant_msg` called `LISTENER.listen`.
        # New logic: We call `commit_transaction`.
        
        # However, we need to be careful: `full_ai_response_for_commit` is just the text content.
        # DeepSeek expects "Assistant: content".
        # The `commit_transaction` method takes `ai_response_content`.
        # We should probably format it as "Miku: ..." inside the content?
        # NO. DeepSeek sees Assistant Role. The content should be the raw text "大家好".
        # But wait, in `SimulatedGroupMsgListener.get_context`, we used to just return msg['content'].
        # And user msgs were formatted as "Name: Content".
        # Assistant msgs were just "Content".
        # So here we should pass just the content.
        
        # Clean up the "Miku:" prefix from the response if it exists (model sometimes hallucinates it)
        clean_response = re.sub(r"^Miku:\s*", "", full_ai_response_for_commit, flags=re.IGNORECASE).strip()
        
        LISTENER.commit_transaction(group_id, clean_response)

        # 8. Memory Consolidation (Background)
        # Note: We use the `messages` list which contains the context used for THIS generation.
        if query_text and clean_response:
            asyncio.create_task(
                memory_service.save_chat_memory(
                    str(sender_id),
                    group_id,
                    simulated_msg.info["name"],
                    PLUGIN_CONFIG.AI_NAME,
                    clean_response,
                    # We need to pass the conversation used. `messages` includes System Prompt.
                    # save_chat_memory filters for user/assistant roles.
                    messages, 
                )
            )

    except Exception as e:
        logger.error(f"AI Chat Error: {e}")
        import traceback
        traceback.print_exc()
        await ai_chat.send("唔...脑子有点乱，等下再聊吧。")
    finally:
        IS_CHATTING = False


# --- Helper Functions ---



def _default_json_serializer(obj):
    """Custom JSON serializer for objects not serializable by default json code"""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    return str(obj)


def _log_payload(payload: dict):
    """记录完整的 Payload 到 JSONL 文件"""
    try:
        log_dir = Path("/app/logs")
        if not log_dir.exists():
            log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "payloads.jsonl"
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "payload": payload
        }
        
        # 使用 append 模式写入
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False, default=_default_json_serializer) + "\n")
    except Exception as e:
        logger.error(f"Failed to log payload: {e}")


# _record_assistant_msg Removed. No longer needed as we commit transaction directly.


def _build_system_prompt(group_id: str, memory_context: str) -> str:
    prompts_config = config_manager.get_config("prompts")
    current_sys_prompt = prompts_config.get("chat_system", "You are Miku.")

    if memory_context:
        current_sys_prompt += memory_context

    # Voice Injection
    try:
        from src.plugins.voice_module.config import config as voice_config

        voice_name = Path(voice_config.ref_audio_path).stem
        voice_template = prompts_config.get("voice_injection_template")

        if voice_template:
            voice_injection = voice_template.format(
                voice_name=voice_name, ref_text=voice_config.ref_text
            )
        else:
            voice_injection = (
                f"\n\n## 当前状态感知 (System Awareness)\n"
                f"*   **当前使用音色 ID**: `{voice_name}`\n"
                f'*   **音色参考台词**: "{voice_config.ref_text}"\n'
                f"*   **自我认知更新**: 你现在拥有上述参考台词所体现的声线和语气特点。请在对话中自然地融入这种语感。\n"
                f"*   **语音使用频度**: 请根据情境灵活判断是否使用语音（`speak_text`）。"
            )
        current_sys_prompt += voice_injection
    except Exception:
        pass

    current_date = datetime.now().strftime("%Y-%m-%d %A")
    current_sys_prompt += (
        f"\n\n[Context]\n当前日期: {current_date}\n当前QQ群号: {group_id}"
    )
    return current_sys_prompt


async def _execute_tool(tool_call) -> str:
    args_str = tool_call.function.arguments
    try:
        # Standard Tool Call Handling
        func_name = tool_call.function.name
        
        args = None
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Tool arguments JSON parse failed: {e}. Raw args: {repr(args_str)}")
            
            # Enhanced Repair Strategy
            args_str_repaired = _repair_json(args_str)
            if args_str_repaired != args_str:
                try:
                    logger.info(f"Attempting JSON repair with: {args_str_repaired}")
                    args = json.loads(args_str_repaired)
                    logger.info("JSON repair successful.")
                except json.JSONDecodeError as e2:
                    logger.error(f"JSON repair failed: {e2}")
                    return f"Error executing tool (JSON Error): {e}. The arguments provided were invalid JSON."
            else:
                 return f"Error executing tool (JSON Error): {e}. The arguments provided were invalid JSON."

        if args is None:
             return "Error executing tool: Invalid JSON arguments."

        tool_res = await tool_registry.dispatch(func_name, args)


        # Handle generator (Voice)
        import inspect

        history_content = ""

        async def _handle_voice_tag(tag: str) -> str:
            voice_path = tag[7:-1]
            try:
                path_obj = Path(voice_path)
                if path_obj.exists():
                    with open(path_obj, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                    await ai_chat.send(MessageSegment.record(file=f"base64://{b64}"))
                    return "已发送语音。"
                return "语音文件生成失败 (文件不存在)。"
            except Exception as e:
                logger.error(f"Voice Error: {e}")
                return f"语音发送失败: {e}"

        if inspect.isasyncgen(tool_res):
            async for chunk in tool_res:
                chunk_str = str(chunk)
                if chunk_str.startswith("[VOICE:"):
                    msg = await _handle_voice_tag(chunk_str)
                    history_content += msg + "\n"
                else:
                    history_content += chunk_str
        else:
            tool_res_str = str(tool_res)
            if tool_res_str.startswith("[VOICE:"):
                history_content = await _handle_voice_tag(tool_res_str)
            else:
                history_content = tool_res_str

        return history_content.strip()

    except Exception as e:
        logger.error(f"Error executing tool '{tool_call.function.name}': {e}")
        return f"Error executing tool: {e}"


def _repair_json(json_str: str) -> str:
    """
    Attempts to repair common malformed JSON strings generated by LLMs.
    Handles:
    1. Unquoted keys: {key: "value"} -> {"key": "value"}
    2. Missing closing quotes on keys: {"key: "value"} -> {"key": "value"}
    3. Trailing commas: {"key": "value",} -> {"key": "value"}
    4. Unbalanced braces/brackets
    """
    fixed_str = json_str.strip()

    # 1. Fix missing closing quote for key (e.g., {"limit: 5})
    # Matches: { or , followed by whitespace, then "key, then :
    fixed_str = re.sub(r'([{,]\s*)"([a-zA-Z0-9_]+)\s*:', r'\1"\2":', fixed_str)

    # 2. Fix unquoted keys (e.g., {limit: 5})
    # Matches: { or , followed by whitespace, then key (no quote), then :
    fixed_str = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', fixed_str)
    
    # 3. Remove trailing commas (e.g., {"a": 1,})
    fixed_str = re.sub(r',\s*([}\]])', r'\1', fixed_str)

    # 4. Balance braces/brackets
    open_braces = fixed_str.count('{') - fixed_str.count('}')
    if open_braces > 0:
        fixed_str += '}' * open_braces
    
    open_brackets = fixed_str.count('[') - fixed_str.count(']')
    if open_brackets > 0:
        fixed_str += ']' * open_brackets
        
    # 5. Try closing unclosed strings at the very end (if truncating)
    # This is risky but helps with cutoff outputs.
    # Check if we have an odd number of quotes
    if fixed_str.count('"') % 2 != 0:
         fixed_str += '"'
         # Re-balance if adding quote messed up structure? 
         # Usually if it ends with ", we just need to close the object.
         open_braces = fixed_str.count('{') - fixed_str.count('}')
         if open_braces > 0:
            fixed_str += '}' * open_braces

    return fixed_str