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
    使用更鲁棒的正则，兼容各种空白符、全半角竖线及属性顺序。
    """
    import re
    import uuid

    tool_calls = []
    
    # 1. 提取最外层的 function_calls 块
    # 匹配 <...DSML...function_calls...> ... </...DSML...function_calls...>
    # 允许 | 或 ｜，允许前后空格
    block_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*function_calls\s*>(.*?)<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*function_calls\s*>"
    block_match = re.search(block_pattern, content, re.DOTALL | re.IGNORECASE)
    
    if not block_match:
        # 兜底：有时模型可能漏掉外层块直接输出 invoke，或者格式极度不规范
        # 这里先只处理规范块，如果以后发现频繁漏块再增加兜底
        return []
    
    block_content = block_match.group(1)
    
    # 2. 提取内部的 invoke 块
    # 匹配 <...DSML...invoke name="xxx" ...> ... </...DSML...invoke>
    invoke_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s+[^>]*?name\s*=\s*[\"'](.*?)[\"'][^>]*?>(.*?)<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*invoke\s*>"
    invokes = re.finditer(invoke_pattern, block_content, re.DOTALL | re.IGNORECASE)
    
    for invoke in invokes:
        tool_name = invoke.group(1)
        args_content = invoke.group(2)
        
        args = {}
        # 3. 提取 parameter
        # 匹配 <...DSML...parameter name="xxx" ...>value</...DSML...parameter>
        param_pattern = r"<\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s+[^>]*?name\s*=\s*[\"'](.*?)[\"'][^>]*?>(.*?)<\s*/\s*[|｜]\s*DSML\s*[|｜]\s*parameter\s*>"
        params = re.finditer(param_pattern, args_content, re.DOTALL | re.IGNORECASE)
        
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

class DSMLFilter:
    """
    流式过滤器，用于从输出流中拦截并移除 DeepSeek 的 <｜DSML｜...> 标签块。
    支持处理跨 chunk 的标签和换行。
    """
    def __init__(self):
        self.buffer = ""
        self.state = "NORMAL" # NORMAL, CHECKING, INSIDE_BLOCK

    def feed(self, text: str) -> str:
        output = []
        for char in text:
            if self.state == "NORMAL":
                if char == "<":
                    self.state = "CHECKING"
                    self.buffer += char
                else:
                    output.append(char)
            
            elif self.state == "CHECKING":
                self.buffer += char
                # 检查缓冲区是否已经明显不是 DSML 标签
                if self._is_mismatch(self.buffer):
                    # 匹配失败，说明不是 DSML (如 "<hello")
                    # 将缓冲区内容全部作为普通文本输出
                    output.append(self.buffer)
                    self.buffer = ""
                    self.state = "NORMAL"
                elif self._is_start_tag_complete(self.buffer):
                    # 成功匹配到开始标签 (如 <｜DSML｜invoke...>)
                    # 进入屏蔽模式，丢弃后续内容直到结束标签
                    self.state = "INSIDE_BLOCK"
                    self.buffer = "" # 清空缓冲区，开始寻找结束标签
            
            elif self.state == "INSIDE_BLOCK":
                self.buffer += char
                if char == ">":
                    # 每当遇到 '>'，检查是否构成了结束标签
                    if self._check_end_tag(self.buffer):
                        self.state = "NORMAL"
                        self.buffer = ""
                    else:
                        # 优化：为了防止缓冲区无限膨胀 (比如模型忘记闭合)，
                        # 我们只需要保留末尾足够匹配结束标签的长度。
                        # 结束标签通常是 </｜DSML｜xxx>，长度一般在 50 以内。
                        if len(self.buffer) > 100:
                            self.buffer = self.buffer[-50:]
                            
        return "".join(output)

    def flush(self) -> str:
        """流结束时调用，将缓冲区内剩余的非标签内容输出"""
        res = ""
        # 如果还在 CHECKING 状态，说明剩下的不足以构成标签，全部吐出
        if self.state == "CHECKING" and self.buffer:
            res = self.buffer
        # 如果在 INSIDE_BLOCK 状态，说明标签未闭合。
        # 选择丢弃（认为是被截断的指令），还是输出（认为是乱码）？
        # 通常为了安全，不输出未闭合的 DSML 块。
        
        self.buffer = ""
        self.state = "NORMAL"
        return res

    def _is_mismatch(self, s: str) -> bool:
        """
        判断字符串 s 是否**不可能**成为 <...|DSML... 的前缀
        """
        # 如果长度还没到关键特征区，先认为不是 mismatch
        # 关键特征序列: < -> space -> |/｜ -> space -> D -> S -> M -> L
        
        # 1. 必须以 < 开头
        if not s.startswith("<"): return True
        
        # 使用正则检查是否匹配"合法前缀"
        # 这是一个宽松的正则，只要字符串符合 DSML 标签的起始部分的任何子集，就返回 True
        import re
        # 允许的模式： < \s* [|｜]? \s* D? S? M? L?
        # 注意：这里逻辑反过来写比较好——如果它连这个宽松模式都不匹配，那就是 Mismatch
        
        # 暂时用简单的逐字符逻辑，更加可控
        content = s[1:] # 去掉 <
        
        # 跳过开头的空白
        content = content.lstrip()
        if not content: return False # 只有 < 和空格，合法
        
        # 检查管道符
        if content[0] not in ('|', '｜'):
            return True # 第一个非空字符不是管道符，Mismatch
            
        content = content[1:] # 去掉管道符
        content = content.lstrip() # 去掉后续空白
        if not content: return False
        
        # 检查 DSML 关键字
        target = "DSML"
        # content 必须是 "DSML" 的前缀
        if not target.startswith(content) and not content.startswith(target):
             # 比如 content="A", mismatch
             # content="DS", match
             # content="DSMLxxx", match (handled by start tag check)
             return True
             
        return False

    def _is_start_tag_complete(self, s: str) -> bool:
        """检查是否完整匹配了开始标签"""
        import re
        # 匹配 <...|...DSML...> 
        return bool(re.search(r"<\s*[|｜]\s*DSML.*?>", s, re.IGNORECASE))

    def _check_end_tag(self, s: str) -> bool:
        """检查字符串末尾是否是结束标签"""
        import re
        # 匹配 </...|...DSML...> 结尾
        # 注意：结束标签通常也包含 function_calls 或 invoke 等，所以只要匹配到 </...DSML...> 结构即可
        return bool(re.search(r"<\/\s*[|｜]\s*DSML.*?>$", s, re.IGNORECASE))