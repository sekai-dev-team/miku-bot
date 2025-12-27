# nonebot
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent, GroupRequestEvent, Bot, Message, MessageSegment, FriendRequestEvent, GroupMessageEvent
from nonebot import logger, on_command, on_regex, on_request, get_plugin_config, get_driver
from nonebot.rule import to_me
from nonebot.typing import T_State
from nonebot.permission import SUPERUSER
from nonebot.params import ArgPlainText
# plugin
import asyncio, re, json
from datetime import datetime
from .config import Config as PluginConfig
from .ai import AI
from .msg_context import SimulatedGroupMsg
from .sentence_handler import State, StateMachine
from .sys_monitor import SystemMonitor
from .utils import get_event_info, is_friend
from .msg_context import SimulatedGroupMsgListener
# constant
PLUGIN_CONFIG = get_plugin_config(PluginConfig)
LISTENER = SimulatedGroupMsgListener()

# hook
driver = get_driver()

# * 1. 闲聊
is_chatting = False
ai = on_regex(r"^(nina,|nina，)|([,，]nina)$", flags=re.IGNORECASE, priority=1, block=False)
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

    msg = ""
    sm = StateMachine()
    context = LISTENER.get_context(group_id)
    stream = await AI.chat(context)
    for resp in stream:
        str_seg = resp.choices[PLUGIN_CONFIG.TOP_INDEX].delta.content
        for char in str_seg:
            msg += char
            sm.transit_by(char)
            cur_state = sm.get_current_state()
            if cur_state != State.CODE_BLOCK:
                msg.strip()
            if cur_state == State.SENTENCE_END:
                if not msg.isspace():
                    # delete nina prefix: <Nina: xxx> --> <xxx>
                    nina_prefix = r"^(Nina[:：])+"
                    msg = re.sub(nina_prefix, "", msg, flags=re.IGNORECASE).strip()
                    await ai.send(msg)
                    # current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    group_msg = SimulatedGroupMsg(group_id, PLUGIN_CONFIG.AI_NAME, PLUGIN_CONFIG.ROLE_ASSISTANT, f"{PLUGIN_CONFIG.AI_NAME}: {msg}")
                    LISTENER.listen(group_msg)
                    await asyncio.sleep(PLUGIN_CONFIG.SEND_INTERVAL)
                msg = ""
                sm.reset()
            elif cur_state == State.INVALID:
                sm.reset() 
    is_chatting = False


# * 4. 检查系统情况
sys_stat = on_command("/stat", rule=to_me(), aliases=PLUGIN_CONFIG.SYS_PREFIX, priority=2, permission=SUPERUSER)
@sys_stat.handle()
async def _():
    message = f"{SystemMonitor.balance()}\n{SystemMonitor.memory()}\n{SystemMonitor.cpu()}\n{LISTENER.get_stat_detail()}"
    await sys_stat.send(message)

# * 5. 使用指南
user_manual = on_command("/help")
@user_manual.handle()
async def _(event: GroupMessageEvent, bot: Bot):
    info, _ = get_event_info(event)
    message = Message(MessageSegment.text(f"{PLUGIN_CONFIG.USER_MANUAL}"))
    await bot.call_api("send_group_forward_msg", group_id=info["group_id"], messages=MessageSegment.node_custom(int(bot.self_id), PLUGIN_CONFIG.AI_NAME, message))

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
    await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"{qq} 想要加Nina为好友。")
    await bot.set_friend_add_request(flag=event.flag, approve=PLUGIN_CONFIG.FRIEND_REQ)
    if PLUGIN_CONFIG.FRIEND_REQ:
        await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"Nina已经同意 {state['qq']} 的好友请求。")
    else:
        await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"Nina已经拒绝 {state['qq']} 的好友请求。")

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