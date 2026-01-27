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
from ..utils import get_event_info, parse_dsml_tool_calls, DSMLFilter

# Global lock
IS_CHATTING = False

# The Matcher
ai_chat = on_regex(r"^(miku,|miku，)|([,，]miku)$", flags=re.IGNORECASE, priority=1, block=False)

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
        # Simple debounce/busy response
        msg = Message(MessageSegment.at(sender_id).text(" 别急，等我先说完嘛"))
        await ai_chat.finish(msg)
    else:
        IS_CHATTING = True

    # 3. Initialize Components
    sb = SentenceBuffer()
    dsml_filter = DSMLFilter()
    
    try:
        # 4. Prepare Context & Prompts
        user_input = event.get_plaintext().strip()
        query_text = re.sub(r"^(miku,|miku，)|([,，]miku)$", "", user_input, flags=re.IGNORECASE).strip()
        
        # 4.1 Retrieve Long-term Memory
        memory_context = await _retrieve_memory_context(sender_id, query_text)
        
        # 4.2 Build System Prompt (with Memory & Voice)
        system_prompt = _build_system_prompt(group_id, memory_context)
        
        # 4.3 Build Message History
        messages = _build_message_history(group_id, system_prompt, user_input)

        # 5. Core Chat Loop
        full_ai_response = ""
        
        # Define helper for sending text
        async def _send_text(text: str):
            for char in text:
                sentence = sb.append(char)
                if sentence:
                    # Remove "Miku:" prefix if present
                    sentence = re.sub(r"^\s*Miku[:：]+\s*", "", sentence, flags=re.IGNORECASE | re.MULTILINE).strip()
                    if sentence:
                        sub_lines = [s.strip() for s in sentence.split('\n') if s.strip()]
                        for sub_line in sub_lines:
                            await ai_chat.send(sub_line)
                            # Self-correction: Add own msg to context
                            _record_assistant_msg(group_id, sub_line)
                            await asyncio.sleep(PLUGIN_CONFIG.SEND_INTERVAL)

        async def _process_stream_segment(segment: str):
            nonlocal full_ai_response
            full_ai_response += segment
            clean_text = dsml_filter.feed(segment)
            if clean_text:
                await _send_text(clean_text)

        # --- Stage 1: Intent Detection (Non-Stream) ---
        response = await AIService.chat_completion(messages, tools=tool_registry.get_tools(), stream=False)
        first_msg = response.choices[0].message
        
        # Check for DSML or Native Tools
        dsml_tool_calls = []
        if not first_msg.tool_calls and first_msg.content:
             dsml_tool_calls = parse_dsml_tool_calls(first_msg.content)
        
        has_tool_calls = bool(first_msg.tool_calls or dsml_tool_calls)

        if has_tool_calls:
            # Handle Mixed Content (Text + Tool) if any
            if dsml_tool_calls:
                 full_content = first_msg.content or ""
                 text_content = _extract_text_from_dsml(full_content)
                 if text_content:
                     await _process_stream_segment(text_content)
                 
                 messages.append({
                    "role": "assistant",
                    "content": full_content, 
                    "tool_calls": dsml_tool_calls
                 })
                 actual_tool_calls = dsml_tool_calls
            else:
                 if first_msg.content:
                     await _process_stream_segment(first_msg.content)
                 messages.append(first_msg)
                 actual_tool_calls = first_msg.tool_calls
            
            # Execute Tools
            for tool_call in actual_tool_calls:
                tool_result = await _execute_tool(tool_call)
                
                call_id = tool_call["id"] if isinstance(tool_call, dict) else tool_call.id
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": str(tool_result)
                })

            # --- Stage 2: Final Response (Stream) ---
            stream = await AIService.chat_completion(messages, stream=True)
            async for resp in stream:
                delta = resp.choices[PLUGIN_CONFIG.TOP_INDEX].delta
                if delta.content:
                    await _process_stream_segment(delta.content)
        
        else:
            # Direct Text Response
            if first_msg.content:
                # Clean DSML tags if present but not parsed as calls
                clean_content = _clean_dsml_tags(first_msg.content)
                if clean_content:
                    await _process_stream_segment(clean_content)

        # 6. Finalize Output
        remain_from_filter = dsml_filter.flush()
        if remain_from_filter:
            await _send_text(remain_from_filter)
            
        remain_text = sb.force_flush()
        if remain_text:
            remain_text = re.sub(r"^(Miku[:：])+", "", remain_text, flags=re.IGNORECASE).strip()
            if remain_text:
                full_ai_response += remain_text
                await ai_chat.send(remain_text)
                _record_assistant_msg(group_id, remain_text)

        # 7. Memory Consolidation (Background)
        if query_text and full_ai_response:
             asyncio.create_task(_save_memory(sender_id, group_id, simulated_msg.info['name'], full_ai_response))

    except Exception as e:
        logger.error(f"AI Chat Error: {e}")
        await ai_chat.send("唔...脑子有点乱，等下再聊吧。")
    finally:
        IS_CHATTING = False


# --- Helper Functions ---

def _record_assistant_msg(group_id: str, content: str):
    group_msg = SimulatedGroupMsg(group_id, PLUGIN_CONFIG.AI_NAME, PLUGIN_CONFIG.ROLE_ASSISTANT, f"{PLUGIN_CONFIG.AI_NAME}: {content}")
    LISTENER.listen(group_msg)

async def _retrieve_memory_context(sender_id: str, query_text: str) -> str:
    memories = await memory_service.search(query_text, user_id=str(sender_id))
    if isinstance(memories, dict) and "results" in memories:
        memories = memories["results"]

    if not memories:
        return ""

    memory_list = []
    for m in memories:
        if isinstance(m, dict):
            content = m.get("memory") or m.get("text")
            if content:
                memory_list.append(content)
        elif isinstance(m, str):
            memory_list.append(m)
    
    if not memory_list:
        return ""

    formatted_memories = []
    for m in memory_list:
        if not m.lower().startswith("user"):
            m = f"User {m}"
        formatted_memories.append(f"* {m}")
    
    return "\n\n## 关于该用户的记忆 (User Profile)\n" + "\n".join(formatted_memories)

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
                voice_name=voice_name,
                ref_text=voice_config.ref_text
            )
        else:
            voice_injection = (
                f"\n\n## 当前状态感知 (System Awareness)\n"
                f"*   **当前使用音色 ID**: `{voice_name}`\n"
                f"*   **音色参考台词**: \"{voice_config.ref_text}\"\n"
                f"*   **自我认知更新**: 你现在拥有上述参考台词所体现的声线和语气特点。请在对话中自然地融入这种语感。\n"
                f"*   **语音使用频度**: 请根据情境灵活判断是否使用语音（`speak_text`）。"
            )
        current_sys_prompt += voice_injection
    except Exception:
        pass

    current_date = datetime.now().strftime("%Y-%m-%d %A")
    current_sys_prompt += f"\n\n[Context]\nCurrent Date: {current_date}\nCurrent Group ID: {group_id}"
    return current_sys_prompt

def _build_message_history(group_id: str, system_prompt: str, user_input: str) -> list[dict]:
    messages = [{"role": PLUGIN_CONFIG.ROLE_SYSTEM, "content": system_prompt}]
    
    context = LISTENER.get_context(group_id)
    history_msgs = []
    current_msg_obj = None
    
    if context:
        last_msg = context[-1]
        # Simplistic assumption: last message is the current trigger
        current_msg_obj = last_msg
        history_msgs = context[:-1]
    
    messages.extend(history_msgs)
    
    if current_msg_obj:
        messages.append(current_msg_obj)
    else:
        messages.append({"role": PLUGIN_CONFIG.ROLE_USER, "content": f"User: {user_input}"})
        
    return messages

def _extract_text_from_dsml(full_content: str) -> str:
    block_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*function_calls\s*>.*?<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*function_calls\s*>"
    return re.sub(block_pattern, "", full_content, flags=re.DOTALL).strip()

def _clean_dsml_tags(content: str) -> str:
    if "<" in content and "DSML" in content:
        block_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*.*?/.*?[|｜]\s*DSML\s*[|｜]\s*.*?>"
        return re.sub(block_pattern, "", content, flags=re.DOTALL | re.IGNORECASE).strip()
    return content

async def _execute_tool(tool_call) -> str:
    try:
        if isinstance(tool_call, dict):
            func_name = tool_call["function"]["name"]
            args_str = tool_call["function"]["arguments"]
        else:
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

async def _save_memory(sender_id: str, group_id: str, user_name: str, ai_response: str):
    context = LISTENER.get_context(group_id)
    memory_messages = []
    
    if context:
        for msg in context[-20:]:
            role = msg['role']
            content = msg['content']
            if role == 'assistant':
                memory_messages.append({"role": "assistant", "content": f"{PLUGIN_CONFIG.AI_NAME}: {content}"})
            elif role == 'user':
                memory_messages.append({"role": "user", "content": content})
    
    prompts_config = config_manager.get_config("prompts")
    template = prompts_config.get("memory_instruction")
    
    instruction = ""
    if template:
        try:
            instruction = template.format(current_user_name=user_name)
        except Exception:
            pass
            
    if not instruction:
        instruction = (
            f"【记忆提取指令】\n"
            f"目标用户: [{user_name}]\n"
            f"请仅提取关于 {user_name} 的新事实、偏好或经历。如果没有则不提取。"
        )
        
    memory_messages.append({"role": "user", "content": instruction})
    memory_messages.append({"role": "assistant", "content": f"{PLUGIN_CONFIG.AI_NAME}: {ai_response}"})
    
    await memory_service.add(memory_messages, user_id=str(sender_id), metadata={"group_id": group_id})
