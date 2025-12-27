# nonebot
from nonebot.adapters.onebot.v11 import MessageEvent as OneBotMessageEvent, Bot, Message, MessageSegment
from nonebot import logger, get_plugin_config, get_bot
# plugin
from .msg_context import SimulatedGroupMsg
from .config import Config as PluginConfig
from datetime import datetime
import json

# constant
PLUGIN_CONFIG = get_plugin_config(PluginConfig)

def get_event_info(event: OneBotMessageEvent) -> tuple[dict, SimulatedGroupMsg]:
    # group_<group_id>_<qq>
    session_seg = event.get_session_id().split("_")
    splited_info = {
        "group_id": session_seg[1],
        "sender_id": session_seg[2],
        "sender_name": event.sender.nickname,
        "sender_msg": event.get_plaintext(),
        "role": __get_sender_role__(event)
    }
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    group_msg = SimulatedGroupMsg(session_seg[1], session_seg[2], __get_sender_role__(event), f"[{current_time}] {event.sender.nickname}：{event.get_plaintext()}")

    return splited_info, group_msg

def read_json_from(json_file: str) -> dict:
    with open(json_file, "r", encoding="utf-8") as source:
        return json.load(source)

def write_to_json(json_file: str, data: dict) -> None:
    with open(json_file, "w", encoding="utf-8") as dest:
        json.dump(data, dest, ensure_ascii=False, indent=4)

async def is_friend(qq: str) -> bool:
    friend_list = await bot.get_friend_list()
    return any(str(friend["user_id"]) == str(qq) for friend in friend_list)

def log_suc(module: str, msg: str) -> None:
    logger.success(f"[{module}]: {msg}")

def log_err(module: str, msg: str) -> None:
    logger.error(f"[{module}]: {msg}")

def log_warn(module: str, msg: str) -> None:
    logger.warning(f"[{module}]: {msg}")

def log_info(module: str, msg: str) -> None:
    logger.info(f"[{module}]: {msg}")

def __get_sender_role__(event: OneBotMessageEvent):
    if event.get_user_id() == PLUGIN_CONFIG.BOT_QQ:
        return PLUGIN_CONFIG.ROLE_ASSISTANT
    else:
        return PLUGIN_CONFIG.ROLE_USER

class MsgUtils:
    def __init__(self) -> None:
        self.__msg_list = []

    def at(self, qq: str, msg) -> Message:
        pass

    def add_msg(self, msg: str) -> int:
        pass

    def construct(self) -> Message:
        pass
        
    def construct_split(self) -> Message:
        pass