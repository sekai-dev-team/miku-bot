from nonebot import on_message, on_request, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, FriendRequestEvent, Bot, GroupRequestEvent
from nonebot.typing import T_State

from ..msg_context import LISTENER, SimulatedGroupMsg
from ..utils import get_event_info
from ..config import plugin_config as PLUGIN_CONFIG

# --- Background Listener ---
listen_background = on_message(priority=10, block=False)
@listen_background.handle()
async def _(event: GroupMessageEvent):
    _, simulated_msg = get_event_info(event)
    LISTENER.listen(simulated_msg)

# --- Friend Request ---
friend_req = on_request()
@friend_req.handle()
async def _(event: FriendRequestEvent, bot: Bot, state: T_State):
    qq = event.get_user_id()
    state["qq"] = qq
    await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"{qq} 想要加Miku为好友ảng")
    await bot.set_friend_add_request(flag=event.flag, approve=PLUGIN_CONFIG.FRIEND_REQ)
    if PLUGIN_CONFIG.FRIEND_REQ:
        await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"Miku已经同意 {state['qq']} 的好友请求ảng")
    else:
        await bot.send_private_msg(user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"Miku已经拒绝 {state['qq']} 的好友请求ảng")

# --- Group Request (formerly test) ---
group_req = on_request()
@group_req.handle()
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
            try:
                 # TODO: Make administrator configurable
                 await bot.send_private_msg(
                    user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"({user_id})，成功加入群 {group_id}ảng"
                )
            except Exception:
                pass
        else:
            # 拒绝加群申请
            await bot.set_group_add_request(
                flag=event.flag,
                sub_type="add",
                approve=False,
                reason="密码错误，请重新申请！"
            )
            try:
                 await bot.send_private_msg(
                    user_id=int(PLUGIN_CONFIG.ADMINISTOR), message=f"({user_id})加群失败。\n原因：密码错误ảng"
                )
            except Exception:
                pass
