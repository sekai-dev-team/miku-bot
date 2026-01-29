import asyncio
import os
import functools
from typing import List, Dict, Any, Optional
from pathlib import Path
from mem0 import Memory
from .config import GLOBAL_AI_CONFIG
from .config_manager import config_manager
from nonebot import logger


class MemoryService:
    _instance = None
    _memory: Optional[Memory] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryService, cls).__new__(cls)
        return cls._instance

    async def initialize(self):
        """Initialize connection to Mem0."""
        try:
            # --- DEBUG: Environment Probe ---
            import sys
            import sqlite3

            logger.info(
                f"DEBUG PROBE: sqlite3.sqlite_version = {sqlite3.sqlite_version}"
            )
            logger.info(
                f"DEBUG PROBE: sqlite3 path = {getattr(sqlite3, '__file__', 'unknown')}"
            )
            logger.info(
                f"DEBUG PROBE: sys.modules['sqlite3'] = {sys.modules.get('sqlite3')}"
            )
            try:
                import chromadb

                logger.info(
                    f"DEBUG PROBE: chromadb imported successfully. Version: {chromadb.__version__}"
                )
            except ImportError as e:
                logger.error(f"DEBUG PROBE: chromadb import FAILED: {e}")
            except Exception as e:
                logger.error(
                    f"DEBUG PROBE: chromadb import raised unexpected exception: {e}"
                )
            # --------------------------------

            config = config_manager.get_config("memory")

            # 基础路径配置
            db_path = config.get("db_path", "./data/memory_store")
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

            # 设置环境变量以适配 DeepSeek (绕过 mem0 配置限制)
            if GLOBAL_AI_CONFIG.base_url:
                os.environ["OPENAI_BASE_URL"] = GLOBAL_AI_CONFIG.base_url
                logger.info(f"Set OPENAI_BASE_URL to {GLOBAL_AI_CONFIG.base_url}")

            # Mem0 配置
            prompts_config = config_manager.get_config("prompts")
            custom_prompt = prompts_config.get("memory_extraction")

            if not custom_prompt:
                logger.warning(
                    "Memory extraction prompt not found in config, using default fallback."
                )
                custom_prompt = (
                    "你是一位专业的记忆管理专家。你的任务是从对话中提取关于用户的简洁、客观的事实（FACTS），用于构建用户画像。\n"
                    "规则：\n"
                    "1. **主语明确**：提取的事实必须以 'User' 开头。例如 'User 喜欢抹茶'，禁止省略主语。\n"
                    "2. **过滤琐事**：严厉忽略无意义的闲聊、情绪宣泄（如'急'、'草'、'哈哈'）、即时状态（如'在吗'、'去吃饭了'）以及对AI功能的询问。\n"
                    "3. **事实导向**：只记录用户的偏好、背景信息、观点或长期计划。不要记录具体的对话过程。\n"
                    "   - ❌ 错误：'User 说这句急' -> 忽略\n"
                    "   - ❌ 错误：'User 问能不能用港卡' -> ✅ 正确：'User 关注港卡支付或海外AI服务' (提取意图)\n"
                    "   - ❌ 错误：'喜欢抹茶' (缺主语) -> ✅ 正确：'User 喜欢抹茶口味'\n"
                    "4. **指代消解**：将 '它'、'这个' 等代词替换为明确的名词。\n"
                    "5. **语言要求**：提取出的记忆内容请使用**简体中文**。"
                )

            mem0_config = {
                "version": "v1.1",
                "vector_store": {
                    "provider": "chroma",
                    "config": {
                        "path": str(Path(db_path).absolute()),
                        "collection_name": "miku_memories",
                    },
                },
                "llm": {
                    "provider": "openai",
                    "config": {
                        "api_key": GLOBAL_AI_CONFIG.api_key,
                        "model": GLOBAL_AI_CONFIG.chat_model,
                        "max_tokens": 1000,
                        "temperature": 0.1,
                    },
                },
                "embedder": {
                    "provider": config.get("embedder_provider", "openai"),
                    "config": {
                        "api_key": config.get(
                            "embedder_api_key", GLOBAL_AI_CONFIG.api_key
                        ),
                        "model": config.get("embedder_model", "text-embedding-3-small"),
                    },
                },
                "custom_prompt": custom_prompt,
            }

            # 内存节省模式：使用本地 CPU 嵌入模型
            if config.get("use_local_embedder", True):
                mem0_config["embedder"] = {
                    "provider": "huggingface",
                    "config": {
                        "model": config.get(
                            "local_embedder_model",
                            "sentence-transformers/all-MiniLM-L6-v2",
                        ),
                    },
                }

            self._memory = Memory.from_config(mem0_config)
            logger.info(f"MemoryService initialized with db_path: {db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize MemoryService: {e}")
            self._memory = None

    async def add(
        self, data: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ):
        """
        异步添加记忆。
        使用 functools.partial 确保参数以关键字形式传递，避免位置参数错误。
        """
        if not self._memory:
            raise RuntimeError("MemoryService is not initialized.")

        try:
            loop = asyncio.get_event_loop()
            # 修正：使用 partial 传递关键字参数
            func = functools.partial(
                self._memory.add, messages=data, user_id=user_id, metadata=metadata
            )
            result = await loop.run_in_executor(None, func)

            # 记录提取的事实
            if result and isinstance(result, list):
                for res in result:
                    event = res.get("event")
                    content = res.get("data")
                    if event == "add":
                        logger.info(f"Memory Extracted for user {user_id}: {content}")
                    elif event == "update":
                        logger.info(f"Memory Updated for user {user_id}: {content}")
            else:
                logger.debug(f"Memory task completed for user {user_id}")

        except Exception as e:
            logger.error(f"Error adding memory: {e}")

    async def search(
        self, query: str, user_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        搜索相关记忆。
        """
        if not self._memory:
            return []

        try:
            loop = asyncio.get_event_loop()
            # 修正：使用 partial 传递关键字参数
            func = functools.partial(
                self._memory.search, query=query, user_id=user_id, limit=limit
            )
            results = await loop.run_in_executor(None, func)

            if results:
                # 尝试解析 results 结构，防止日志报错
                try:
                    memory_summaries = [
                        r.get("memory") for r in results if isinstance(r, dict)
                    ]
                    logger.info(
                        f"Memories Found for user {user_id} (query: '{query}'): {memory_summaries}"
                    )
                except Exception:
                    logger.info(
                        f"Memories Found for user {user_id}: {len(results)} items"
                    )
            else:
                logger.debug(
                    f"No relevant memories found for user {user_id} with query: '{query}'"
                )

            return results
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []

    async def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """
        获取用户的所有记忆。
        """
        if not self._memory:
            return []
        try:
            loop = asyncio.get_event_loop()
            # 修正：使用 partial 传递关键字参数，解决 "takes 1 positional argument but 2 were given"
            func = functools.partial(self._memory.get_all, user_id=user_id)
            return await loop.run_in_executor(None, func)
        except Exception as e:
            logger.error(f"Error getting all memories: {e}")
            return []

    async def delete(self, memory_id: str):
        """
        根据 ID 删除记忆。
        """
        if not self._memory:
            return
        try:
            loop = asyncio.get_event_loop()
            # 修正：mem0 v1.1 使用 memory_id 而不是 vector_id
            func = functools.partial(self._memory.delete, memory_id=memory_id)
            await loop.run_in_executor(None, func)
            logger.info(f"Memory deleted: {memory_id}")
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id}: {e}")
            raise e  # 向上抛出异常，让前端能感知到失败

    async def retrieve_formatted_memory(self, user_id: str, query_text: str) -> str:
        """
        检索并格式化记忆，供 Prompt 使用。
        """
        memories = await self.search(query_text, user_id=user_id)
        if isinstance(memories, dict) and "results" in memories:
            memories = memories["results"]

        if not memories:
            return ""

        memory_list = []
        for m in memories:
            if isinstance(m, dict):
                content = m.get("memory") or m.get("text")
                if content:
                    memory_list.append(content)
            elif isinstance(m, str):
                memory_list.append(m)

        if not memory_list:
            return ""

        formatted_memories = []
        for m in memory_list:
            # 简单的 heuristic: 如果没有显式的主语，加上 User
            # 注意: 这里的 m 已经是提取过的 "User xxxx" 格式 (如果 prompt 遵循了指令)
            # 但为了保险起见，可以检查一下
            if not m.lower().strip().startswith("user"):
                m = f"User {m}"
            formatted_memories.append(f"* {m}")

        return "\n\n## 关于该用户的记忆 (User Profile)\n" + "\n".join(
            formatted_memories
        )

    async def save_chat_memory(
        self,
        user_id: str,
        group_id: str,
        user_name: str,
        ai_name: str,
        ai_response: str,
        context_msgs: List[Dict[str, str]],
    ):
        """
        分析并保存对话记忆。
        :param context_msgs: 最近的对话上下文 [{"role": "user"|"assistant", "content": "..."}]
        """
        memory_messages = []

        # 1. 构建用于提取记忆的上下文
        # 限制上下文长度，例如最近 20 条
        for msg in context_msgs[-20:]:
            role = msg.get("role")
            content = msg.get("content")
            if role == "assistant":
                memory_messages.append(
                    {"role": "assistant", "content": f"{ai_name}: {content}"}
                )
            elif role == "user":
                memory_messages.append({"role": "user", "content": content})

        # 2. 获取提取指令
        prompts_config = config_manager.get_config("prompts")
        template = prompts_config.get("memory_instruction")

        instruction = ""
        if template:
            try:
                instruction = template.format(current_user_name=user_name)
            except Exception:
                pass

        if not instruction:
            instruction = (
                f"【记忆提取指令 (Memory Extraction Directive)】\n"
                f"目标用户: [{user_name}]\n"
                f"请分析上述对话，**仅提取**关于 {user_name} 的长期事实、偏好或经历。\n\n"
                f"**核心规则**:\n"
                f"1. **去噪**: 忽略即时状态(如'饿了')、情绪宣泄(如'草')、玩笑话及对AI功能的询问。\n"
                f"2. **整合**: 将零散的句子整合成完整的语义。例如把'脑子兜不住'和'玩鸣潮导致的'整合成一条因果描述。\n"
                f"3. **保守**: 如果不确定是否为长期事实，则**不提取**。宁缺毋滥。\n"
                f"4. **格式**: 必须以 'User' 开头，使用中文。\n\n"
                f"如果没有值得记录的新事实，请直接返回空字符串。"
            )

        memory_messages.append({"role": "user", "content": instruction})
        memory_messages.append(
            {"role": "assistant", "content": f"{ai_name}: {ai_response}"}
        )
        print(memory_messages)
        # 3. 执行添加
        await self.add(
            memory_messages, user_id=user_id, metadata={"group_id": group_id}
        )


# 单例导出
memory_service = MemoryService()

try:
    from nonebot import get_driver

    driver = get_driver()

    @driver.on_startup
    async def _():
        await memory_service.initialize()

except ValueError:
    # 允许在非 NoneBot 环境（如调试脚本）中导入
    logger.warning("NoneBot driver not found. MemoryService will not auto-initialize.")
except ImportError:
    pass
