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

    # 1. Update Context
    LISTENER.listen(simulated_msg)

    # 2. Check Lock
    if IS_CHATTING:
        msg = Message(MessageSegment.at(sender_id).text(" 别急，等我先说完嘛"))
        await ai_chat.finish(msg)
    else:
        IS_CHATTING = True

    # 3. Initialize Buffer
    sb = SentenceBuffer()

    try:
        # 4. Prepare Context & Prompts
        user_input = event.get_plaintext().strip()
        query_text = re.sub(
            r"^(miku,|miku，)|([,，]miku)$", "", user_input, flags=re.IGNORECASE
        ).strip()

        # 4.1 Retrieve Long-term Memory
        memory_context = await memory_service.retrieve_formatted_memory(
            str(sender_id), query_text
        )

        # 4.2 Build System Prompt
        system_prompt = _build_system_prompt(group_id, memory_context)

        # 4.3 Build Message History
        messages = _build_message_history(group_id, system_prompt)

        # 5. Core Chat Loop
        full_ai_response = ""

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
                            # Self-correction: Add own msg to context
                            _record_assistant_msg(group_id, sub_line)
                            await asyncio.sleep(PLUGIN_CONFIG.SEND_INTERVAL)

        async def _process_stream_segment(segment: str):
            nonlocal full_ai_response
            full_ai_response += segment
            await _send_text(segment)

        # --- Stage 1: Intent Detection (Non-Stream) ---
        # 使用 Strict Mode 后，可以直接信任 tool_calls
        response = await AIService.chat_completion(
            messages, tools=tool_registry.get_tools(), stream=False
        )
        first_msg = response.choices[0].message
        
        if first_msg.tool_calls:
            # Case A: Tool Call Requested
            # 如果有文本伴随工具调用（Thinking Process），也可以先输出
            if first_msg.content:
                 await _process_stream_segment(first_msg.content)
            
            messages.append(first_msg)
            
            # Execute Tools
            for tool_call in first_msg.tool_calls:
                tool_result = await _execute_tool(tool_call)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(tool_result)
                })

            # --- Stage 2: Final Response (Stream) ---
            stream = await AIService.chat_completion(messages, stream=True)
            async for resp in stream:
                delta = resp.choices[PLUGIN_CONFIG.TOP_INDEX].delta
                if delta.content:
                    await _process_stream_segment(delta.content)
        
        else:
            # Case B: Direct Text Response
            if first_msg.content:
                await _process_stream_segment(first_msg.content)

        # 6. Finalize Output
        remain_text = sb.force_flush()
        if remain_text:
            remain_text = re.sub(
                r"^(Miku[:：])+", "", remain_text, flags=re.IGNORECASE
            ).strip()
            if remain_text:
                full_ai_response += remain_text
                await ai_chat.send(remain_text)
                _record_assistant_msg(group_id, remain_text)

        # 7. Memory Consolidation (Background)
        if query_text and full_ai_response:
            asyncio.create_task(
                memory_service.save_chat_memory(
                    str(sender_id),
                    group_id,
                    simulated_msg.info["name"],
                    PLUGIN_CONFIG.AI_NAME,
                    full_ai_response,
                    LISTENER.get_context(group_id),
                )
            )

    except Exception as e:
        logger.error(f"AI Chat Error: {e}")
        await ai_chat.send("唔...脑子有点乱，等下再聊吧。")
    finally:
        IS_CHATTING = False


# --- Helper Functions ---

def _record_assistant_msg(group_id: str, content: str):
    group_msg = SimulatedGroupMsg(
        group_id,
        PLUGIN_CONFIG.AI_NAME,
        PLUGIN_CONFIG.ROLE_ASSISTANT,
        f"{PLUGIN_CONFIG.AI_NAME}: {content}",
    )
    LISTENER.listen(group_msg)


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


def _build_message_history(group_id: str, system_prompt: str) -> list[dict]:
    messages = [{"role": PLUGIN_CONFIG.ROLE_SYSTEM, "content": system_prompt}]
    context = LISTENER.get_context(group_id)
    messages.extend(context)
    return messages


async def _execute_tool(tool_call) -> str:
    try:
        # Standard Tool Call Handling
        func_name = tool_call.function.name
        args_str = tool_call.function.arguments
        
        args = json.loads(args_str)
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
        return f"Error executing tool: {e}"
