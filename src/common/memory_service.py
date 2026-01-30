import asyncio
from typing import List, Dict, Any, Optional
from nonebot import logger

from .memory.manager import memory_manager

class MemoryService:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryService, cls).__new__(cls)
        return cls._instance

    async def initialize(self):
        """
        初始化 Miku-Memory-Layer (MML) 系统。
        替代原有的 mem0 初始化。
        """
        try:
            await memory_manager.initialize()
            logger.info("MemoryService (MML Architecture) initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize MemoryService: {e}")

    async def add(
        self, data: str, user_id: str, metadata: Optional[Dict[str, Any]] = None
    ):
        """
        [兼容接口] 添加记忆。
        在新架构中，我们不再手动添加零碎的 Fact。
        为了兼容性，我们将这些数据视为一次特殊的对话记录存入 L1 缓存。
        """
        try:
            # 将外部强制添加的记忆视为一次 Assistant 的自我陈述
            await memory_manager.add_message(
                user_id=user_id,
                user_name="System",
                ai_response=str(data),
                context_msgs=[] # 空上下文
            )
            logger.debug(f"Legacy add_memory called for user {user_id}, redirected to L1 buffer.")
        except Exception as e:
            logger.error(f"Error in add_memory: {e}")

    async def search(
        self, query: str, user_id: str, limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        [兼容接口] 搜索记忆。
        返回相关的情境记忆 (L2 Summaries)。
        """
        try:
            # 这里我们需要手动调用 vector_store，或者通过 manager 暴露
            # 为了简单，我们临时构造一个符合旧接口返回格式的列表
            # 但实际上，retrieve_formatted_memory 才是被主要调用的方法
            from .memory.vector_store import vector_store
            from .memory.embedding import embedding_service
            
            vec = await embedding_service.get_embedding(query)
            if not vec:
                return []
                
            results = vector_store.search_similar(user_id, vec, limit=limit)
            
            # 转换为 mem0 风格的返回格式，防止调用方崩溃
            formatted_results = []
            for r in results:
                formatted_results.append({
                    "memory": r["content"],
                    "metadata": r["metadata"],
                    "score": 0.0 # ChromaDB 默认 API 可能不直接返回 score，或者需要调整
                })
            return formatted_results
        except Exception as e:
            logger.error(f"Error searching memory: {e}")
            return []

    async def get_all(self, user_id: str) -> List[Dict[str, Any]]:
        """
        [兼容接口] 获取所有记忆。
        返回 L3 用户画像作为唯一的核心记忆。
        """
        try:
            from .memory.profile_store import profile_store
            profile = profile_store.get_profile(user_id)
            if profile:
                return [{"memory": profile, "metadata": {"type": "profile"}}]
            return []
        except Exception as e:
            logger.error(f"Error getting all memories: {e}")
            return []

    async def delete(self, memory_id: str):
        """
        [兼容接口] 删除记忆。
        暂不支持删除特定的 L2/L3 记忆片段。
        """
        logger.warning("delete_memory is not supported in MML architecture yet.")
        pass

    async def retrieve_formatted_memory(self, user_id: str, query_text: str) -> str:
        """
        核心接口：为 Prompt 检索并格式化记忆。
        """
        try:
            return await memory_manager.get_context_for_prompt(user_id, query_text)
        except Exception as e:
            logger.error(f"Error retrieving formatted memory: {e}")
            return ""

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
        核心接口：保存对话上下文。
        """
        try:
            await memory_manager.add_message(
                user_id=user_id,
                user_name=user_name,
                ai_response=ai_response,
                context_msgs=context_msgs
            )
        except Exception as e:
            logger.error(f"Error saving chat memory: {e}")


# 单例导出
memory_service = MemoryService()

try:
    from nonebot import get_driver

    driver = get_driver()

    @driver.on_startup
    async def _():
        await memory_service.initialize()

except ValueError:
    logger.warning("NoneBot driver not found. MemoryService will not auto-initialize.")
except ImportError:
    pass