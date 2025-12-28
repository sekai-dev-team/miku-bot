from pydantic import BaseModel
from nonebot import get_plugin_config

class Config(BaseModel):
    # 记录触发词（回复消息时）
    RECORD_KEYWORDS: set[str] = {"记", "记仇", "入典", "📸", "📝"}
    
    # 随机回顾触发词（直接发送）
    REVIEW_KEYWORDS: set[str] = {"来点语录", "翻翻小本本", "随机黑历史", "随机迫害", "语录", "黑历史", "抽黑历史"}

    # 戳一戳是否触发
    ENABLE_POKE: bool = True

plugin_config = get_plugin_config(Config)
