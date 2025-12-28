from nonebot import get_plugin_config
from pydantic import BaseModel, field_validator

class GlobalAIConfig(BaseModel):
    """
    全局 AI 配置，供所有插件共享
    """
    API_KEY: str = ""
    BASE_URL: str = "https://api.deepseek.com/"
    CHAT_MODEL: str = "deepseek-chat"
    CODE_MODEL: str = "deepseek-coder"
    
    # 全局默认参数
    FREQUENCY_PENALTY: float = 0
    PRESENCE_PENALTY: float = 0
    TEMPERATURE: float = 1.1
    MAX_TOKENS: int = 1024
    STREAM: bool = True

    @field_validator("FREQUENCY_PENALTY")
    def check_frequency_penalty(cls, value: float) -> float:
        if -2 <= value <= 2:
            return value
        raise ValueError("frequency penalty must between [-2, 2]")
    
    @field_validator("PRESENCE_PENALTY")
    def check_presence_penalty(cls, value: float) -> float:
        if -2 <= value <= 2:
            return value
        raise ValueError("presence penalty must between [-2, 2]")

    @field_validator("TEMPERATURE")
    def check_temp(cls, value: float) -> float:
        if 0 <= value <= 2:
            return value
        raise ValueError("temperature must between [0, 2]")

# 便捷获取配置的实例
GLOBAL_AI_CONFIG = get_plugin_config(GlobalAIConfig)