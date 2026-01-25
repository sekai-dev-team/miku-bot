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
            logger.info(f"DEBUG PROBE: sqlite3 path = {getattr(sqlite3, '__file__', 'unknown')}")
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
                        "temperature": 0.1,
                        "max_tokens": 1000,
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
                "custom_prompt": (
                    "You are an expert memory manager. Extract key facts about the user from the conversation.\n"
                    "CRITICAL RULES:\n"
                    "1. RESOLVE PRONOUNS: You MUST use the conversation context to replace pronouns (it, this, that, the recipe) with specific nouns.\n"
                    "   - BAD: 'User asked how to make it.'\n"
                    "   - GOOD: 'User asked for the recipe of Matcha Basque Cake.'\n"
                    "2. SELF-CONTAINED: Extracted memories must be fully understandable without context.\n"
                    "3. IGNORE CHITCHAT: Do not save greetings ('Hello') or system acknowledgments."
                ),
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
                    memory_summaries = [r.get("memory") for r in results if isinstance(r, dict)]
                    logger.info(
                        f"Memories Found for user {user_id} (query: '{query}'): {memory_summaries}"
                    )
                except Exception:
                    logger.info(f"Memories Found for user {user_id}: {len(results)} items")
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
            raise e # 向上抛出异常，让前端能感知到失败


# 单例导出
memory_service = MemoryService()

from nonebot import get_driver
driver = get_driver()

@driver.on_startup
async def _():
    await memory_service.initialize()