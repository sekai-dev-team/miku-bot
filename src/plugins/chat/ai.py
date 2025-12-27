# plugin
from openai import OpenAI
from nonebot import get_plugin_config
from .config import Config


CONFIG = get_plugin_config(Config)
AI_CLIENT = OpenAI(api_key=CONFIG.API_KEY, base_url=CONFIG.BASE_URL)
class AI:
    @classmethod
    async def chat(cls, context):
        messages = [{"role": CONFIG.ROLE_SYSTEM, "content": CONFIG.AI_PROMPT}]
        messages.extend(context)

        stream = AI_CLIENT.chat.completions.create(
                    model=CONFIG.CHAT_MODEL,
                    messages=messages, # type: ignore
                    frequency_penalty=CONFIG.FREQUENCY_PENALTY,
                    presence_penalty=CONFIG.PRESENCE_PENALTY,
                    temperature=CONFIG.TEMPERATURE,
                    max_tokens=CONFIG.MAX_TOKENS,
                    stream=CONFIG.STREAM
        )
        return stream

    @classmethod
    async def ask(cls, messages):
        stream = AI_CLIENT.chat.completions.create(
                    model=CONFIG.CHAT_MODEL,
                    messages=messages, # type: ignore
                    frequency_penalty=CONFIG.FREQUENCY_PENALTY,
                    presence_penalty=CONFIG.PRESENCE_PENALTY,
                    temperature=CONFIG.TEMPERATURE,
                    max_tokens=CONFIG.MAX_TOKENS,
                    stream=CONFIG.STREAM
        )
        return stream