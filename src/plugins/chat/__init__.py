# nonebot
import nonebot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, GroupRequestEvent, Bot, Message, MessageSegment, FriendRequestEvent
from nonebot import logger, on_command, on_regex, on_request, get_plugin_config, get_driver, on_message
from nonebot.matcher import Matcher
from nonebot.exception import FinishedException
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.permission import SUPERUSER
from nonebot.params import ArgPlainText, CommandArg
from nonebot_plugin_htmlrender import md_to_pic
# plugin
import asyncio, re, json, base64
from pathlib import Path
from datetime import datetime
from .config import plugin_config as PLUGIN_CONFIG
# from .ai import AI  <-- Removed
from src.common.ai_service import AIService # <-- Added
from src.common.tool_registry import tool_registry
from .msg_context import SimulatedGroupMsg
from .sentence_handler import SentenceBuffer
from .sys_monitor import SystemMonitor
from .utils import get_event_info, is_friend, parse_dsml_tool_calls
from .msg_context import SimulatedGroupMsgListener
from .help_menu import get_main_menu_text, get_plugin_help_text
from src.common.config_manager import config_manager
from src.common.memory_service import memory_service
# constant
LISTENER = SimulatedGroupMsgListener()

# hook
driver = get_driver()

# Load Resources
def load_resource(filename: str) -> str:
    try:
        # src/plugins/chat/__init__.py -> src/common/resources/filename
        current_dir = Path(__file__).parent
        resource_path = current_dir.parent.parent / "common" / "resources" / filename
        if resource_path.exists():
            return resource_path.read_text(encoding="utf-8")
        else:
            logger.error(f"Resource file not found: {resource_path}")
            return f"Error: {filename} not found."
    except Exception as e:
        logger.error(f"Failed to load resource {filename}: {e}")
        return f"Error loading {filename}."

def get_resource_path(filename: str) -> Path:
    current_dir = Path(__file__).parent
    return current_dir.parent.parent / "common" / "resources" / filename

MANUAL_CONTENT = load_resource("manual.md")

# --- Resource Management Commands ---

# 2. Manual Management
cmd_manual = on_command("mymanual", aliases={"manual", "guide"}, permission=SUPERUSER, priority=5, block=True)

@cmd_manual.handle()
async def _(matcher: Matcher):
    msg = (
        "Miku 使用手册管理\n"
        "------------------\n"
        "当前文件: manual.md\n"
        "1. 修改手册\n"
        "2. 查看当前手册\n"
        "0. 退出交互"
    )
    await matcher.send(msg)

@cmd_manual.got("action")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action")):
    if action == "0":
        await matcher.finish("操作已取消。")
    elif action == "2":
        path = get_resource_path("manual.md")
        if path.exists():
            content = path.read_text(encoding="utf-8")
            await matcher.finish(content)
        else:
            await matcher.finish("文件不存在！")
    elif action == "1":
        await matcher.send("请输入新的手册内容 (输入 -1 退出)：")
    else:
        await matcher.reject("指令无法识别，请重新输入（0/1/2）：")

@cmd_manual.got("content")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action"), content: str = ArgPlainText("content")):
    if content.strip() == "-1":
        await matcher.finish("已退出修改")

    if action == "1":
        path = get_resource_path("manual.md")
        try:
            path.write_text(content, encoding="utf-8")
            global MANUAL_CONTENT
            MANUAL_CONTENT = content
            await matcher.finish("使用手册更新成功！")
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"Failed to write manual: {e}")
            await matcher.finish(f"写入失败：{e}")


# 3. AI Prompt Management
cmd_aiprompt = on_command("aiprompt", aliases={"prompt", "human_set"}, permission=SUPERUSER, priority=5, block=True)

@cmd_aiprompt.handle()
async def _(matcher: Matcher):
    msg = (
        "Miku 提示词管理\n"
        "-------------------\n"
        "当前配置: plugin_configs.yaml (prompts.chat_system)\n"
        "1. 修改提示词\n"
        "2. 查看当前提示词\n"
        "0. 退出交互"
    )
    await matcher.send(msg)

@cmd_aiprompt.got("action")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action")):
    if action == "0":
        await matcher.finish("操作已取消。")
    elif action == "2":
        prompts = config_manager.get_config("prompts")
        current_prompt = prompts.get("chat_system", "未找到配置")
        await matcher.finish(f"当前 Prompt:\n\n{current_prompt}")
    elif action == "1":
        await matcher.send("请输入新的提示词 (输入 -1 退出)：")
    else:
        await matcher.reject("指令无法识别，请重新输入（0/1/2）：")

@cmd_aiprompt.got("content")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action"), content: str = ArgPlainText("content")):
    if content.strip() == "-1":
        await matcher.finish("已退出修改")

    if action == "1":
        try:
            prompts = config_manager.get_config("prompts")
            prompts["chat_system"] = content
            config_manager.save_config("prompts", prompts)
            await matcher.finish("AI 提示词更新成功！(已保存至 plugin_configs.yaml)")
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"Failed to update prompt: {e}")
            await matcher.finish(f"更新失败：{e}")


# 3.5. User Profile Management (Memory)
cmd_profile = on_command("profile", aliases={"记忆", "用户画像"}, priority=5, block=True)

@cmd_profile.handle()
async def _(matcher: Matcher, event: MessageEvent, args: Message = CommandArg()):
    sender_id = event.get_user_id()
    
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split(maxsplit=1)
    
    sub_cmd = parts[0].lower() if parts else "ls"
    payload = parts[1] if len(parts) > 1 else ""
    
    try:
        if sub_cmd in ["ls", "list", "show", "查看"]:
            memories = await memory_service.get_all(user_id=sender_id)
            
            # Fix: mem0 v1.1 returns {'results': [...]}
            if isinstance(memories, dict) and "results" in memories:
                memories = memories["results"]
            
            if not memories:
                await matcher.finish("我好像还没记住关于你的什么特别的事情呢... 多和我聊聊天吧！")
            
            # Format list
            msg_lines = ["📋 你的个人档案 (Memory Profile):", "-------------------"]
            for mem in memories:
                # mem0 structure: {'id': '...', 'memory': '...', ...}
                if isinstance(mem, str):
                    m_id = "N/A"
                    m_text = mem
                elif isinstance(mem, dict):
                    m_id = mem.get("id", "N/A")
                    # Support both 'memory' (v1.0) and 'text' (v1.1) keys
                    m_text = mem.get("memory") or mem.get("text") or ""
                else:
                    m_id = "Unknown"
                    m_text = str(mem)

                msg_lines.append(f"🆔 {m_id}\n   {m_text}")
                
            await matcher.finish("\n".join(msg_lines))
            
        elif sub_cmd in ["add", "new", "新增"]:
            if not payload:
                await matcher.finish("要在你的档案里加什么呢？请使用 /profile add <内容>")
                
            await matcher.send("正在写入记忆...")
            # Add memory
            await memory_service.add(payload, user_id=sender_id, metadata={"source": "manual_add"})
            await matcher.finish("已添加到记忆库！")

        elif sub_cmd in ["rm", "del", "delete", "remove", "删除"]:
            if not payload:
                 await matcher.finish("请指定要删除的记忆 ID。你可以先用 /profile ls 查看。")
            
            await matcher.send(f"正在删除记忆 [{payload}]...")
            await memory_service.delete(payload)
            await matcher.finish("删除完成。")
            
        else:
            # Default help
            await matcher.finish(
                "🧠 Miku 记忆管理指令:\n"
                "-------------------\n"
                "/profile ls       - 查看你的所有记忆\n"
                "/profile add <内容> - 手动添加一条关于你的记忆\n"
                "/profile rm <ID>  - 删除指定 ID 的记忆"
            )
    except RuntimeError as e:
        await matcher.finish(f"记忆系统暂时不可用 (System Error): {e}")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"Error in profile command: {e}")
        await matcher.finish(f"发生未知错误: {e}")


# * 1. 闲聊
is_chatting = False
ai = on_regex(r"^(miku,|miku，)|([,，]miku)$", flags=re.IGNORECASE, priority=1, block=False)
@ai.handle()
async def _(event: GroupMessageEvent):
    splited_info, simulated_msg = get_event_info(event)
    sender_id = splited_info["sender_id"]
    group_id = splited_info["group_id"]
    LISTENER.listen(simulated_msg)

    global is_chatting
    if is_chatting:
        message = Message(MessageSegment.at(sender_id).text(" 别急，等我先说完嘛"))
        await ai.finish(message)
    else:
        is_chatting = True

    sb = SentenceBuffer()
    is_first_sent = True
    context = LISTENER.get_context(group_id)
    
    try:
        # --- Memory Retrieval (Long-term Memory) ---
        user_input = event.get_plaintext().strip()
        # 移除 Miku 前缀以获得纯净的搜索词
        query_text = re.sub(r"^(miku,|miku，)|([,，]miku)$", "", user_input, flags=re.IGNORECASE).strip()
        
        memories = await memory_service.search(query_text, user_id=str(sender_id))
        
        # Fix: mem0 v1.1 search returns {'results': [...]}
        if isinstance(memories, dict) and "results" in memories:
            memories = memories["results"]

        memory_context = ""
        if memories:
            # Support both 'memory' (v1.0) and 'text' (v1.1) keys
            memory_list = []
            for m in memories:
                if isinstance(m, dict):
                    content = m.get("memory") or m.get("text")
                    if content:
                        memory_list.append(content)
                elif isinstance(m, str):
                    memory_list.append(m)
            
            if memory_list:
                formatted_memories = []
                for m in memory_list:
                    # Ensure subject is explicit to prevent self-identification errors
                    if not m.lower().startswith("user"):
                        m = f"User {m}"
                    formatted_memories.append(f"* {m}")
                
                memory_context = "\n\n## 关于该用户的记忆 (User Profile)\n" + "\n".join(formatted_memories)
                logger.debug(f"Retrieved {len(memory_list)} memories for user {sender_id}")

        # 构造请求消息列表
        # 1. System Prompt (Loaded from Config & Inject Voice Info & Memories)
        prompts_config = config_manager.get_config("prompts")
        current_sys_prompt = prompts_config.get("chat_system", "You are Miku.")
        
        # Inject Memories
        if memory_context:
            current_sys_prompt += memory_context

        # Inject Voice Identity
        try:
            from src.plugins.voice_module.config import config as voice_config
            # Try to extract a meaningful name or just show the reference text
            # Assuming ref_audio_path is like "/app/ref_audio/mika_zh.wav"
            voice_name = Path(voice_config.ref_audio_path).stem  # e.g., "mika_zh"
            
            prompts_config = config_manager.get_config("prompts")
            voice_template = prompts_config.get("voice_injection_template")
            
            if voice_template:
                try:
                    voice_injection = voice_template.format(
                        voice_name=voice_name,
                        ref_text=voice_config.ref_text
                    )
                except KeyError as e:
                    logger.error(f"Failed to format voice template: {e}")
                    # Fallback
                    voice_injection = (
                        f"\n\n## 当前状态感知 (System Awareness)\n"
                        f"*   **当前使用音色 ID**: `{voice_name}`\n"
                        f"*   **音色参考台词**: \"{voice_config.ref_text}\"\n"
                        f"*   **自我认知更新**: 你现在拥有上述参考台词所体现的声线和语气特点。请在对话中自然地融入这种语感（例如：如果参考台词很温柔，就表现得温柔；如果很傲娇，就表现得傲娇）。\n"
                        f"*   **语音使用频度**: 请根据情境灵活判断是否使用语音（`speak_text`），**不必**每句话都使用，保持自然的对话节奏。"
                    )
            else:
                voice_injection = (
                    f"\n\n## 当前状态感知 (System Awareness)\n"
                    f"*   **当前使用音色 ID**: `{voice_name}`\n"
                    f"*   **音色参考台词**: \"{voice_config.ref_text}\"\n"
                    f"*   **自我认知更新**: 你现在拥有上述参考台词所体现的声线和语气特点。请在对话中自然地融入这种语感（例如：如果参考台词很温柔，就表现得温柔；如果很傲娇，就表现得傲娇）。\n"
                    f"*   **语音使用频度**: 请根据情境灵活判断是否使用语音（`speak_text`），**不必**每句话都使用，保持自然的对话节奏。"
                )

            current_sys_prompt += voice_injection
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to inject voice info: {e}")

        current_date = datetime.now().strftime("%Y-%m-%d %A")
        current_sys_prompt += f"\n\n[Context]\nCurrent Date: {current_date}\nCurrent Group ID: {group_id}"
        
        # --- 构建消息列表 (Structured Messages) ---
        # 方案：严格区分 System / History / Current Query
        # 这样能有效防止 AI 对旧消息进行“补全”而非“回复”
        
        messages = [{"role": PLUGIN_CONFIG.ROLE_SYSTEM, "content": current_sys_prompt}]
        
        # 1. 处理历史记录 (Short-term Memory)
        # context 包含了 [..., msg_n-1, msg_n]
        # 我们把 msg_n (当前用户的触发消息) 单独拿出来作为 Prompt 的最后一条
        
        history_msgs = []
        current_msg_obj = None
        
        if context:
            # 简单启发式：如果最后一条消息的内容包含了用户的 query_text，
            # 或者就是用户刚刚发的，那么把它视为 Current Query
            last_msg = context[-1]
            
            # 判断最后一条是否是本次触发的消息（通过内容匹配，虽然有风险但对于 listener 机制最简便）
            # listener 存进去的内容可能带有 "Name: " 前缀 (如果是 User)
            # 我们的 query_text 是去除了 Miku 前缀的纯文本
            
            # 这里直接取最后一条作为当前消息，剩下的作为历史
            # 这样 AI 就能明确：上面的都是过去式，最后这一句才是现在要处理的
            current_msg_obj = last_msg
            history_msgs = context[:-1]
        
        # 添加历史背景
        messages.extend(history_msgs)
        
        # 添加当前消息 (Trigger)
        # 显式地将其作为最后一条 User 消息，引导模型聚焦
        if current_msg_obj:
             messages.append(current_msg_obj)
        else:
            # 兜底：如果 listener 还没来得及存进去（理论上不应发生），手动构造一条
            messages.append({"role": PLUGIN_CONFIG.ROLE_USER, "content": f"User: {user_input}"})

        # ---------------------------------------------------------------------
        # Stage 1: Intent Detection (Non-Stream)
        # ---------------------------------------------------------------------
        # 尝试调用工具，关闭流式以确保解析稳定
        response = await AIService.chat_completion(messages, tools=tool_registry.get_tools(), stream=False)
        first_msg = response.choices[0].message
        
        # 准备一个内部函数来处理文本片段（复用流式和非流式逻辑）
        full_ai_response = ""
        async def process_text_segment(text_seg: str):
            nonlocal full_ai_response
            full_ai_response += text_seg
            for char in text_seg:
                sentence = sb.append(char)
                if sentence:
                    # 全面去除行首的 Miku: 前缀，增加人味
                    # 使用 MULTILINE 模式确保处理多行文本（兜底 SentenceBuffer 可能漏切的情况）
                    miku_prefix = r"^\s*Miku[:：]+\s*"
                    sentence = re.sub(miku_prefix, "", sentence, flags=re.IGNORECASE | re.MULTILINE).strip()
                    
                    if sentence:
                        # 二次切分：防止因代码块标记等原因导致的大段文本未切分
                        sub_lines = [s.strip() for s in sentence.split('\n') if s.strip()]
                        for sub_line in sub_lines:
                            await ai.send(sub_line)
                            group_msg = SimulatedGroupMsg(group_id, PLUGIN_CONFIG.AI_NAME, PLUGIN_CONFIG.ROLE_ASSISTANT, f"{PLUGIN_CONFIG.AI_NAME}: {sub_line}")
                            LISTENER.listen(group_msg)
                            await asyncio.sleep(PLUGIN_CONFIG.SEND_INTERVAL)

        # Check for DSML (DeepSeek XML format)
        dsml_tool_calls = []
        if not first_msg.tool_calls and first_msg.content:
            dsml_tool_calls = parse_dsml_tool_calls(first_msg.content)

        if first_msg.tool_calls or dsml_tool_calls:
            # --- Tool Call Branch ---
            if dsml_tool_calls:
                 # DSML Detected: Content might be mixed (Text + DSML)
                 # We need to extract the text part to display it to the user
                 full_content = first_msg.content or ""
                 
                 # Regex to find the DSML block (using the robust pattern)
                 block_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*function_calls\s*>.*?<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*function_calls\s*>"
                 
                 # Remove ALL DSML blocks to get pure text
                 text_content = re.sub(block_pattern, "", full_content, flags=re.DOTALL).strip()
                 
                 if text_content:
                     await process_text_segment(text_content)

                 # 手动构造 assistant 消息存入历史
                 messages.append({
                    "role": "assistant",
                    "content": full_content, 
                    "tool_calls": dsml_tool_calls
                 })
                 actual_tool_calls = dsml_tool_calls
            else:
                 # Native Tool Calls (usually no content, but check just in case)
                 if first_msg.content:
                     await process_text_segment(first_msg.content)

                 messages.append(first_msg) 
                 actual_tool_calls = first_msg.tool_calls
            
            for tool_call in actual_tool_calls:
                try:
                    # 兼容对象和字典访问
                    if isinstance(tool_call, dict):
                        func_name = tool_call["function"]["name"]
                        args_str = tool_call["function"]["arguments"]
                        call_id = tool_call["id"]
                    else:
                        func_name = tool_call.function.name
                        args_str = tool_call.function.arguments
                        call_id = tool_call.id

                    args = json.loads(args_str)
                    # 执行工具
                    tool_res = await tool_registry.dispatch(func_name, args)

                    # Helper to process voice tags
                    async def process_voice_tag(tag_content: str) -> str:
                        voice_path = tag_content[7:-1]
                        try:
                            # Windows path fix: file:///C:/...
                            path_obj = Path(voice_path)
                            if path_obj.exists():
                                # Use base64 to avoid filesystem sharing issues between containers
                                with open(path_obj, "rb") as f:
                                    voice_data = f.read()
                                    base64_str = base64.b64encode(voice_data).decode()
                                await ai.send(MessageSegment.record(file=f"base64://{base64_str}"))
                                return "已发送语音。"
                            else:
                                return "语音文件生成失败 (文件不存在)。"
                        except Exception as e:
                            logger.error(f"Failed to send voice: {e}")
                            return f"语音生成成功但发送失败: {e}"

                    history_content = ""
                    import inspect
                    if inspect.isasyncgen(tool_res):
                        # 流式工具结果处理
                        async for chunk in tool_res:
                            chunk_str = str(chunk)
                            if chunk_str.startswith("[VOICE:"):
                                res_msg = await process_voice_tag(chunk_str)
                                history_content += res_msg + "\n"
                            else:
                                history_content += chunk_str
                    else:
                        # 普通工具结果处理
                        tool_res_str = str(tool_res)
                        if tool_res_str.startswith("[VOICE:"):
                            history_content = await process_voice_tag(tool_res_str)
                        else:
                            history_content = tool_res_str

                    tool_res = history_content.strip()

                except Exception as e:
                    tool_res = f"Error executing tool: {e}"
                
                # 把结果加进去
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": str(tool_res)
                })
            
            # -----------------------------------------------------------------
            # Stage 2: Result Generation (Stream)
            # -----------------------------------------------------------------
            # 带着结果再次请求 AI (开启流式，不传 tools 防止循环)
            stream = await AIService.chat_completion(messages, stream=True)
            async for resp in stream:
                delta = resp.choices[PLUGIN_CONFIG.TOP_INDEX].delta
                if delta.content:
                    await process_text_segment(delta.content)
        
        else:
            # --- Direct Text Branch ---
            # 没有调用工具，直接处理文本
            if first_msg.content:
                # Fallback: Even if parse_dsml_tool_calls failed, if we see DSML tags, strip them
                clean_content = first_msg.content
                if "<" in clean_content and "DSML" in clean_content:
                    block_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*.*?/.*?[|｜]\s*DSML\s*[|｜]\s*.*?>"
                    clean_content = re.sub(block_pattern, "", clean_content, flags=re.DOTALL | re.IGNORECASE).strip()
                
                if clean_content:
                    await process_text_segment(clean_content)

        # 处理流结束后剩余的文本
        remain_text = sb.force_flush()
        if remain_text:
            miku_prefix = r"^(Miku[:：])+"
            remain_text = re.sub(miku_prefix, "", remain_text, flags=re.IGNORECASE).strip()
            
            if remain_text:
                full_ai_response += remain_text
                await ai.send(remain_text)
                group_msg = SimulatedGroupMsg(group_id, PLUGIN_CONFIG.AI_NAME, PLUGIN_CONFIG.ROLE_ASSISTANT, f"{PLUGIN_CONFIG.AI_NAME}: {remain_text}")
                LISTENER.listen(group_msg)

        # --- Memory Storage (Asynchronous) ---
        if query_text and full_ai_response:
            # Construct context-rich interaction for better memory extraction
            # Pass list of messages to mem0 for better structural understanding
            memory_messages = []
            
            # FULL CONTEXT + FOCUS INSTRUCTION MODE
            # Strategy: Send full group context to preserve logic, but use an in-context instruction
            # to tell the LLM exactly which user to focus on.
            current_user_name = simulated_msg.info['name']
            
            if context:
                # 1. Include recent context (last 20 msgs) to capture multi-user interactions
                for msg in context[-20:]:
                    role = msg['role']
                    content = msg['content']
                    
                    if role == 'assistant':
                        # Add prefix for clarity in multi-user transcript
                        memory_messages.append({"role": "assistant", "content": f"{PLUGIN_CONFIG.AI_NAME}: {content}"})
                    elif role == 'user':
                        # Content is already "Name: Msg"
                        memory_messages.append({"role": "user", "content": content})
            
            # 2. Add the explicit instruction to guide extraction
            # This acts as a dynamic system prompt injection
            
            prompts_config = config_manager.get_config("prompts")
            instruction_template = prompts_config.get("memory_instruction")
            
            if instruction_template:
                # Use the template from config
                try:
                    instruction = instruction_template.format(current_user_name=current_user_name)
                except KeyError as e:
                    logger.error(f"Failed to format memory instruction template: {e}")
                    # Fallback if template keys don't match
                    instruction = (
                        f"【记忆提取指令 (Memory Extraction Directive)】\n"
                        f"当前目标用户 (Target User): [{current_user_name}]。\n"
                        f"任务：请分析上述对话上下文，**仅提取**关于目标用户 [{current_user_name}] 的事实、偏好或经历。\n"
                        f"规则：\n"
                        f"1. 忽略其他用户的个人信息，除非它们是理解目标用户行为的必要背景。\n"
                        f"2. 提取出的事实主语请统一使用 'User' (代表 {current_user_name})。\n"
                        f"3. 如果没有关于 {current_user_name} 的新事实，则不提取。"
                    )
            else:
                # Fallback if config is missing
                instruction = (
                    f"【记忆提取指令 (Memory Extraction Directive)】\n"
                    f"当前目标用户 (Target User): [{current_user_name}]。\n"
                    f"任务：请分析上述对话上下文，**仅提取**关于目标用户 [{current_user_name}] 的事实、偏好或经历。\n"
                    f"规则：\n"
                    f"1. 忽略其他用户的个人信息，除非它们是理解目标用户行为的必要背景。\n"
                    f"2. 提取出的事实主语请统一使用 'User' (代表 {current_user_name})。\n"
                    f"3. 如果没有关于 {current_user_name} 的新事实，则不提取。"
                )
            
            memory_messages.append({"role": "user", "content": instruction})

            # 3. Append the current assistant response to complete the loop
            # (Context usually lags one step behind current response)
            memory_messages.append({"role": "assistant", "content": f"{PLUGIN_CONFIG.AI_NAME}: {full_ai_response}"})
            
            # 后台异步执行记忆提取，不阻塞响应
            asyncio.create_task(memory_service.add(memory_messages, user_id=str(sender_id), metadata={"group_id": group_id}))

    except Exception as e:
        logger.error(f"AI Chat Error: {e}")
        await ai.send("唔...脑子有点乱，等下再聊吧。")
    finally:
        is_chatting = False


# * 4. 检查系统情况
sys_stat = on_command("stat", aliases=PLUGIN_CONFIG.SYS_PREFIX, priority=2, permission=SUPERUSER)
@sys_stat.handle()
async def _(bot: Bot, event: MessageEvent):  # 支持私聊
    # 获取各项状态
    uptime = SystemMonitor.uptime()
    balance = await SystemMonitor.balance() # 记得 await 异步方法
    mem = SystemMonitor.memory()
    cpu = SystemMonitor.cpu()
    vram = SystemMonitor.vram()
    
    # 获取群组信息
    try:
        group_list = await bot.get_group_list()
        total_count = len(group_list)
    except Exception as e:
        logger.error(f"Failed to get group list: {e}")
        total_count = "Unknown"
        
    active_groups = list(LISTENER.group_queues.keys())
    group_stat = f"群总数量: {total_count}"
    if active_groups:
         group_stat += f"\n活跃上下文: {len(active_groups)}\n" + "\n".join(active_groups)
    
    # 拼接消息
    # 如果 vram 存在，则加入到消息中
    vram_section = f"{vram}\n" if vram else ""

    message = (
        f"Miku 状态报告\n"
        f"------------------\n"
        f"{uptime}\n"
        f"{cpu}\n"
        f"{mem}\n"
        f"{vram_section}"
        f"------------------\n"
        f"{balance}\n"
        f"------------------\n"
        f"{group_stat}"
    )
    await sys_stat.send(message)

# * 5. 使用指南
user_manual = on_command("help")
@user_manual.handle()
async def _(event: MessageEvent, bot: Bot, args: Message = CommandArg()):  # 支持私聊
    arg_text = args.extract_plain_text().strip()
    
    if not arg_text:
        # Show main menu
        await user_manual.finish(get_main_menu_text())
    else:
        # Show specific help
        detail = get_plugin_help_text(arg_text)
        if detail:
            # Check if user wants "all" or specific
            await user_manual.finish(detail)
        else:
             # Fallback: if arg is "all" or "manual", maybe show the full image?
             if arg_text.lower() in ["all", "full", "manual"]:
                try:
                    if MANUAL_CONTENT.startswith("Error"):
                         await user_manual.finish("说明书好像弄丢了... (文件读取失败)")
                    img = await md_to_pic(MANUAL_CONTENT)
                    await user_manual.finish(MessageSegment.image(img))
                except FinishedException:
                    raise
                except Exception as e:
                    logger.error(f"Failed to render help manual: {e}")
                    await user_manual.finish("说明书渲染失败了...")

             await user_manual.finish(f"未找到关于 '{arg_text}' 的功能说明哦。\n请发送 `/help` 查看列表，或发送 `/help all` 查看完整长图。")

# todo * 9. 服务测试
    
# 监听群消息
listen_background = on_message(priority=10, block=False)
@listen_background.handle()
async def _(event: GroupMessageEvent):
    _, simulated_msg = get_event_info(event)
    LISTENER.listen(simulated_msg)

# todo 好友系统
friend_req = on_request()
@friend_req.handle()
async def _(event: FriendRequestEvent, bot: Bot, state: T_State):
    qq = event.get_user_id()
    state["qq"] = qq
    await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"{qq} 想要加Miku为好友。")
    await bot.set_friend_add_request(flag=event.flag, approve=PLUGIN_CONFIG.FRIEND_REQ)
    if PLUGIN_CONFIG.FRIEND_REQ:
        await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"Miku已经同意 {state['qq']} 的好友请求。")
    else:
        await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"Miku已经拒绝 {state['qq']} 的好友请求。")

# todo 测试
test = on_request()
# @test.handle()
async def _(bot: Bot, event: GroupRequestEvent):
    if event.sub_type == "add":  # 只处理加群请求
        # 格式如下：
        # 问题
        # 答案：xxxxx
        # 筛选出：xxxxx
        note = event.comment.split("\n")[-1][3:]  # 获取验证信息
        group_id = event.group_id  # 获取群号
        user_id = event.user_id  # 获取申请者QQ号

        logger.info(f"note: {note}\ngroup_id: {group_id}\nuser_id: {user_id}")
        # 验证密码
        if note == "123456":
            # 同意加群申请
            await bot.set_group_add_request(
                flag=event.flag,
                sub_type="add",
                approve=True,
                reason="欢迎加入！"
            )
            await bot.send_private_msg(
                user_id="可以填写管理员（非bot）的qq，或者任意你希望接受bot消息的用户", message=f"({user_id})，成功加入群 {group_id}。"
            )
        else:
            # 拒绝加群申请
            await bot.set_group_add_request(
                flag=event.flag,
                sub_type="add",
                approve=False,
                reason="密码错误，请重新申请！"
            )
            await bot.send_private_msg(
                user_id="可以填写管理员（非bot）的qq，或者任意你希望接受bot消息的用户", message=f"({user_id})加群失败。\n原因：密码错误。"
            )

# --- Configuration Management ---
from src.common.config_manager import config_manager
reload_cmd = on_command("reload_config", aliases={"刷新配置", "重载配置"}, permission=SUPERUSER, priority=1, block=True)

@reload_cmd.handle()
async def _(matcher: Matcher):
    try:
        config_manager.reload()
        # Trigger voice config reload if module is active
        try:
            from src.plugins.voice_module.config import config as voice_config
            voice_config.load_from_file()
        except ImportError:
            pass
            
        await matcher.finish("配置已刷新！(Plugin Configs reloaded from YAML)")
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        await matcher.finish(f"配置刷新失败：{e}")