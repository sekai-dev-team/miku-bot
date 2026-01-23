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
        await matcher.send("请输入新的手册内容：")
    else:
        await matcher.reject("指令无法识别，请重新输入（0/1/2）：")

@cmd_manual.got("content")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action"), content: str = ArgPlainText("content")):
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
        # 构造请求消息列表
        # 1. System Prompt (Loaded from Config & Inject Voice Info)
        prompts_config = config_manager.get_config("prompts")
        current_sys_prompt = prompts_config.get("chat_system", "You are Miku.")

        # Inject Voice Identity
        try:
            from src.plugins.voice_module.config import config as voice_config
            # Try to extract a meaningful name or just show the reference text
            # Assuming ref_audio_path is like "/app/ref_audio/mika_zh.wav"
            voice_name = Path(voice_config.ref_audio_path).stem  # e.g., "mika_zh"
            
            voice_injection = (
                f"\n\n## 当前状态感知 (System Awareness)\n"
                f"*   **当前使用音色 ID**: `{voice_name}`\n"
                f"*   **音色参考台词**: \"{voice_config.ref_text}\"\n"
                f"*   **自我认知更新**: 你现在拥有上述参考台词所体现的声线和语气特点。请在对话中自然地融入这种语感（例如：如果参考台词很温柔，就表现得温柔；如果很傲娇，就表现得傲娇）。"
            )
            current_sys_prompt += voice_injection
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to inject voice info: {e}")

        current_sys_prompt += f"\n\n[Context]\nCurrent Group ID: {group_id}"
        messages = [{"role": PLUGIN_CONFIG.ROLE_SYSTEM, "content": current_sys_prompt}]
        # 2. Context History
        messages.extend(context)

        # ---------------------------------------------------------------------
        # Stage 1: Intent Detection (Non-Stream)
        # ---------------------------------------------------------------------
        # 尝试调用工具，关闭流式以确保解析稳定
        response = await AIService.chat_completion(messages, tools=tool_registry.get_tools(), stream=False)
        first_msg = response.choices[0].message
        
        # 准备一个内部函数来处理文本片段（复用流式和非流式逻辑）
        async def process_text_segment(text_seg: str):
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
                 # 手动构造 assistant 消息存入历史
                 messages.append({
                    "role": "assistant",
                    "content": first_msg.content, 
                    "tool_calls": dsml_tool_calls
                 })
                 actual_tool_calls = dsml_tool_calls
            else:
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
                await process_text_segment(first_msg.content)

        # 处理流结束后剩余的文本
        remain_text = sb.force_flush()
        if remain_text:
            miku_prefix = r"^(Miku[:：])+"
            remain_text = re.sub(miku_prefix, "", remain_text, flags=re.IGNORECASE).strip()
            
            if remain_text:
                await ai.send(remain_text)
                group_msg = SimulatedGroupMsg(group_id, PLUGIN_CONFIG.AI_NAME, PLUGIN_CONFIG.ROLE_ASSISTANT, f"{PLUGIN_CONFIG.AI_NAME}: {remain_text}")
                LISTENER.listen(group_msg)

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
    message = (
        f"Miku 状态报告\n"
        f"------------------\n"
        f"{uptime}\n"
        f"{cpu}\n"
        f"{mem}\n"
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