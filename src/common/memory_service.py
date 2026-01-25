import asyncio
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

            # Mem0 配置
            # 注意：由于 DeepSeek 兼容 OpenAI 接口，这里 LLM provider 使用 openai
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
                        "base_url": GLOBAL_AI_CONFIG.base_url,
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
            }

            # 内存节省模式：使用本地 CPU 嵌入模型
            if config.get("use_local_embedder", True):
                # 默认开启本地嵌入以节省 API 开销和 VRAM (强制使用 CPU)
                mem0_config["embedder"] = {
                    "provider": "huggingface",
                    "config": {
                        "model": config.get(
                            "local_embedder_model",
                            "sentence-transformers/all-MiniLM-L6-v2",
                        ),
                        "device": "cpu",
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
        mem0 的 add 方法会调用 LLM 进行事实提取，建议在后台运行。
        """
        if not self._memory:
            raise RuntimeError("MemoryService is not initialized.")

        try:
            loop = asyncio.get_event_loop()
            # mem0 目前主要是同步调用
            result = await loop.run_in_executor(
                None, self._memory.add, data, user_id, metadata
            )

            # 记录提取的事实
            if result and isinstance(result, list):
                for res in result:
                    # 某些版本的 mem0 返回格式不同，尝试安全获取 event 类型和内容
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
            results = await loop.run_in_executor(
                None, self._memory.search, query, user_id, limit
            )

            if results:
                memory_summaries = [r["memory"] for r in results]
                logger.info(
                    f"Memories Found for user {user_id} (query: '{query}'): {memory_summaries}"
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
            return await loop.run_in_executor(None, self._memory.get_all, user_id)
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
            await loop.run_in_executor(None, self._memory.delete, memory_id)
            logger.info(f"Memory deleted: {memory_id}")
        except Exception as e:
            logger.error(f"Error deleting memory {memory_id}: {e}")


# 单例导出
memory_service = MemoryService()

from nonebot import get_driver
driver = get_driver()

@driver.on_startup
async def _():
    await memory_service.initialize()
