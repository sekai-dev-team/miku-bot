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

def parse_dsml_tool_calls(content: str) -> list[dict]:
    """
    解析 DeepSeek-V3/R1 的 <｜DSML｜function_calls> 格式
    返回格式模拟 OpenAI Tool Call Object:
    [
        {
            "id": "call_random_id",
            "function": {
                "name": "tool_name",
                "arguments": "json_string_of_args"
            },
            "type": "function"
        }
    ]
    """
    import re
    import uuid

    tool_calls = []
    
    # 提取 function_calls 块
    block_pattern = r"<｜DSML｜function_calls>(.*?)</｜DSML｜function_calls>"
    block_match = re.search(block_pattern, content, re.DOTALL)
    
    if not block_match:
        return []
    
    block_content = block_match.group(1)
    
    # 提取 invoke
    invoke_pattern = r"<｜DSML｜invoke name=\"(.*?)\">(.*?)</｜DSML｜invoke>"
    invokes = re.finditer(invoke_pattern, block_content, re.DOTALL)
    
    for invoke in invokes:
        tool_name = invoke.group(1)
        args_content = invoke.group(2)
        
        args = {}
        # 提取 parameter
        # 注意：这里假设 parameter 格式比较规范，如果有嵌套可能需要更复杂的解析
        param_pattern = r"<｜DSML｜parameter name=\"(.*?)\"(?:.*?)>(.*?)</｜DSML｜parameter>"
        params = re.finditer(param_pattern, args_content, re.DOTALL)
        
        for param in params:
            key = param.group(1)
            value = param.group(2).strip()
            args[key] = value
            
        tool_calls.append({
            "id": f"call_{uuid.uuid4().hex[:8]}",
            "function": {
                "name": tool_name,
                "arguments": json.dumps(args, ensure_ascii=False)
            },
            "type": "function"
        })
        
    return tool_calls

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