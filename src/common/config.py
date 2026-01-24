from pydantic import BaseModel, field_validator
from .config_manager import config_manager

class GlobalAIConfig(BaseModel):
    """
    全局 AI 配置，供所有插件共享
    """
    api_key: str = ""
    base_url: str = "https://api.deepseek.com/"
    chat_model: str = "deepseek-chat"
    code_model: str = "deepseek-coder"
    
    # 全局默认参数
    frequency_penalty: float = 0
    presence_penalty: float = 0
    temperature: float = 1.1
    max_tokens: int = 1024
    stream: bool = True

    @field_validator("frequency_penalty")
    def check_frequency_penalty(cls, value: float) -> float:
        if -2 <= value <= 2:
            return value
        raise ValueError("frequency penalty must between [-2, 2]")
    
    @field_validator("presence_penalty")
    def check_presence_penalty(cls, value: float) -> float:
        if -2 <= value <= 2:
            return value
        raise ValueError("presence penalty must between [-2, 2]")

    @field_validator("temperature")
    def check_temp(cls, value: float) -> float:
        if 0 <= value <= 2:
            return value
        raise ValueError("temperature must between [0, 2]")

def get_global_ai_config() -> GlobalAIConfig:
    """Helper to get fresh config"""
    data = config_manager.get_config("global_ai")
    return GlobalAIConfig(**data)

class GlobalConfigProxy:
    """Proxy to ensure we always get the latest config values"""
    def __getattr__(self, name):
        cfg = get_global_ai_config()
        return getattr(cfg, name)

# 便捷获取配置的实例 (Proxy)
GLOBAL_AI_CONFIG = GlobalConfigProxy()