from nonebot import get_plugin_config
from pydantic import BaseModel
from typing import List, Set

class StockConfig(BaseModel):
    # 默认推送时间 (格式: "HH:MM")
    stock_push_time: str = "15:30"
    # 默认推送群组 (来自 .env)
    stock_push_groups: List[str] = []

stock_config = get_plugin_config(StockConfig)
