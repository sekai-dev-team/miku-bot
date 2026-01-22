from nonebot import get_plugin_config
from pydantic import BaseModel
from typing import List

class NewsConfig(BaseModel):
    # 默认推送时间 (格式: "HH:MM")
    news_push_time: str = "08:30"
    # 默认推送群组 (来自 .env)
    news_push_groups: List[str] = []

news_config = get_plugin_config(NewsConfig)
