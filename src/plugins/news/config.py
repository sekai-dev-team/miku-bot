from pydantic import BaseModel
from typing import List
from src.common.config_manager import config_manager

class NewsConfig(BaseModel):
    # 默认推送时间 (格式: "HH:MM")
    news_push_time: str = "08:30"
    # 默认推送群组 (来自 .env)
    news_push_groups: List[str] = []

def get_config() -> NewsConfig:
    return NewsConfig(**config_manager.get_config("news"))

class ConfigProxy:
    def __getattr__(self, name):
        return getattr(get_config(), name)

news_config = ConfigProxy()
