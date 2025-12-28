from openai import AsyncOpenAI
from .config import GLOBAL_AI_CONFIG

class AIService:
    _client = None

    @classmethod
    def get_client(cls) -> AsyncOpenAI:
        """单例模式获取 Client，避免重复创建"""
        if cls._client is None:
            cls._client = AsyncOpenAI(
                api_key=GLOBAL_AI_CONFIG.API_KEY,
                base_url=GLOBAL_AI_CONFIG.BASE_URL
            )
        return cls._client

    @classmethod
    async def chat_completion(cls, messages: list[dict]):
        """
        通用的对话接口
        :param messages: 标准的 OpenAI 消息列表 [{"role": "user", "content": "..."}]
        :return: Stream Response
        """
        client = cls.get_client()
        response = await client.chat.completions.create(
            model=GLOBAL_AI_CONFIG.CHAT_MODEL,
            messages=messages, # type: ignore
            frequency_penalty=GLOBAL_AI_CONFIG.FREQUENCY_PENALTY,
            presence_penalty=GLOBAL_AI_CONFIG.PRESENCE_PENALTY,
            temperature=GLOBAL_AI_CONFIG.TEMPERATURE,
            max_tokens=GLOBAL_AI_CONFIG.MAX_TOKENS,
            stream=GLOBAL_AI_CONFIG.STREAM
        )
        return response
