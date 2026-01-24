from openai import AsyncOpenAI
from .config import GLOBAL_AI_CONFIG
from typing import Optional, List, Dict, Any

class AIService:
    _client = None

    @classmethod
    def get_client(cls) -> AsyncOpenAI:
        """单例模式获取 Client，避免重复创建"""
        if cls._client is None:
            cls._client = AsyncOpenAI(
                api_key=GLOBAL_AI_CONFIG.api_key,
                base_url=GLOBAL_AI_CONFIG.base_url
            )
        return cls._client

    @classmethod
    async def chat_completion(cls, messages: list[dict], tools: Optional[List[Dict[str, Any]]] = None, tool_choice: str = "auto", stream: Optional[bool] = None):
        """
        通用的对话接口
        :param messages: 标准的 OpenAI 消息列表 [{"role": "user", "content": "..."}]
        :param tools: 工具定义列表 (OpenAI 格式)
        :param tool_choice: 工具选择策略
        :param stream: 是否流式输出。如果不传，默认使用 Config 配置。
        :return: Stream Response (if configured) or full response
        """
        client = cls.get_client()
        
        # 默认使用配置，但允许覆盖
        use_stream = GLOBAL_AI_CONFIG.stream if stream is None else stream

        # 构造参数字典
        kwargs = {
            "model": GLOBAL_AI_CONFIG.chat_model,
            "messages": messages,
            "frequency_penalty": GLOBAL_AI_CONFIG.frequency_penalty,
            "presence_penalty": GLOBAL_AI_CONFIG.presence_penalty,
            "temperature": GLOBAL_AI_CONFIG.temperature,
            "max_tokens": GLOBAL_AI_CONFIG.max_tokens,
            "stream": use_stream
        }
        
        # 只有当提供了 tools 时才添加相关参数
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice

        response = await client.chat.completions.create(**kwargs)
        return response
