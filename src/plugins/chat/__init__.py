# nonebot
import nonebot
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, GroupRequestEvent, Bot, Message, MessageSegment, FriendRequestEvent
from nonebot import logger, on_command, on_regex, on_request, get_plugin_config, get_driver
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.permission import SUPERUSER
from nonebot.params import ArgPlainText
from nonebot_plugin_htmlrender import md_to_pic
# plugin
import asyncio, re, json
from pathlib import Path
from datetime import datetime
from .config import Config as PluginConfig
# from .ai import AI  <-- Removed
from src.common.ai_service import AIService # <-- Added
from .msg_context import SimulatedGroupMsg
from .sentence_handler import SentenceBuffer
from .sys_monitor import SystemMonitor
from .utils import get_event_info, is_friend
from .msg_context import SimulatedGroupMsgListener
# constant
PLUGIN_CONFIG = get_plugin_config(PluginConfig)
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

PROMPT_CONTENT = load_resource("miku_prompt.md")
MANUAL_CONTENT = load_resource("manual.md")


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
    context = LISTENER.get_context(group_id)
    
    try:
        # 构造请求消息列表
        # 1. System Prompt (Loaded from file)
        messages = [{"role": PLUGIN_CONFIG.ROLE_SYSTEM, "content": PROMPT_CONTENT}]
        # 2. Context History
        messages.extend(context)

        # 调用通用 AI 服务
        stream = await AIService.chat_completion(messages)

        async for resp in stream:
            delta = resp.choices[PLUGIN_CONFIG.TOP_INDEX].delta
            if delta.content:
                str_seg = delta.content
                for char in str_seg:
                    sentence = sb.append(char)
                    if sentence:
                        # delete miku prefix: <Miku: xxx> --> <xxx>
                        miku_prefix = r"^(Miku[:：])+"
                        sentence = re.sub(miku_prefix, "", sentence, flags=re.IGNORECASE).strip()
                        
                        if sentence:
                            await ai.send(sentence)
                            group_msg = SimulatedGroupMsg(group_id, PLUGIN_CONFIG.AI_NAME, PLUGIN_CONFIG.ROLE_ASSISTANT, f"{PLUGIN_CONFIG.AI_NAME}: {sentence}")
                            LISTENER.listen(group_msg)
                            await asyncio.sleep(PLUGIN_CONFIG.SEND_INTERVAL)

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
async def _(event: MessageEvent):  # 支持私聊
    # 获取各项状态
    uptime = SystemMonitor.uptime()
    balance = await SystemMonitor.balance() # 记得 await 异步方法
    mem = SystemMonitor.memory()
    cpu = SystemMonitor.cpu()
    group_stat = LISTENER.get_stat_detail() # 这里也可以考虑优化输出格式
    
    # 拼接消息
    message = (
        f"📊 Miku 状态报告\n"
        f"------------------\n"
        f"{uptime}\n"
        f"{cpu}\n"
        f"{mem}\n"
        f"------------------\n"
        f"{balance}\n"
        f"------------------\n"
        f"👥 {group_stat}"
    )
    await sys_stat.send(message)

# * 5. 使用指南
user_manual = on_command("help")
@user_manual.handle()
async def _(event: MessageEvent, bot: Bot):  # 支持私聊
    try:
        # 将预加载的文本渲染为 Markdown 图片
        if MANUAL_CONTENT.startswith("Error"):
             await user_manual.finish("说明书好像弄丢了... (文件读取失败)")
             
        img = await md_to_pic(MANUAL_CONTENT)
        await user_manual.finish(MessageSegment.image(img))
    except nonebot.exception.FinishedException:
        raise
    except Exception as e:
        logger.error(f"Failed to render help manual: {e}")
        await user_manual.finish("说明书渲染失败了...请检查日志。")

# todo * 9. 服务测试
    
# 监听群消息
listen_background = on_command(PLUGIN_CONFIG.MATCH_ALL_CMD, priority=10, block=True)
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