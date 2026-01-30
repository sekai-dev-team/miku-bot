import asyncio
import time
from typing import List, Dict, Any, Optional
from collections import defaultdict

from nonebot import logger

from .embedding import embedding_service
from .profile_store import profile_store
from .vector_store import vector_store
from .prompts import SUMMARY_PROMPT, REFLECTION_PROMPT
from ..ai_service import AIService

class MemoryManager:
    _instance = None
    
    # L1: 工作记忆缓存 (Working Memory)
    # 结构: user_id -> List[Dict]
    _buffer: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    
    # 配置常量
    BUFFER_SIZE_LIMIT = 15  # 对话轮数达到多少时触发存档
    IDLE_TIMEOUT = 600      # (可选) 闲置多久触发存档，暂未实现定时器

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MemoryManager, cls).__new__(cls)
        return cls._instance

    async def initialize(self):
        """初始化所有子系统"""
        # 加载数据库
        profile_store.initialize()
        vector_store.initialize()
        # 预加载 Embedding 模型 (避免第一次对话卡顿)
        # 注意：这可能会占用 CPU 一段时间
        # embedding_service.initialize() 
        logger.info("MemoryManager initialized (L1/L2/L3 ready).")

    async def add_message(self, user_id: str, user_name: str, ai_response: str, context_msgs: List[Dict[str, str]]):
        """
        处理新的对话消息。
        这是 MemoryService.save_chat_memory 的底层实现。
        """
        # 1. 将新对话加入 L1 缓存
        # 我们只需要最新的交互，而不是整个 context_msgs (因为 context_msgs 可能包含之前的历史)
        # 这里的 context_msgs 通常是 [{"role": "user", "content": "..."}] (最后一条是用户的新消息)
        
        last_user_msg = ""
        if context_msgs and context_msgs[-1]["role"] == "user":
            last_user_msg = context_msgs[-1]["content"]
        
        if not last_user_msg:
            return

        # 存入缓存
        self._buffer[user_id].append({"role": "user", "content": f"{user_name}: {last_user_msg}"})
        self._buffer[user_id].append({"role": "assistant", "content": f"Miku: {ai_response}"})

        # logger.debug(f"User {user_id} buffer size: {len(self._buffer[user_id])}")

        # 2. 检查是否需要 Flush (L1 -> L2/L3)
        if len(self._buffer[user_id]) >= self.BUFFER_SIZE_LIMIT:
            logger.info(f"Buffer full for user {user_id}, triggering background flush...")
            # 异步执行 Flush，不阻塞当前请求
            asyncio.create_task(self._flush(user_id))

    async def get_context_for_prompt(self, user_id: str, current_query: str) -> str:
        """
        为 System Prompt 准备上下文信息。
        包含：L3 用户画像 + L2 相关回忆。
        """
        # 1. 获取 L3 用户画像 (User Profile)
        profile = profile_store.get_profile(user_id)
        
        # 2. 获取 L2 相关回忆 (Episodic Memory)
        related_memories = ""
        if current_query:
            # 计算 Query 向量
            query_vec = await embedding_service.get_embedding(current_query)
            if query_vec:
                # 搜索 ChromaDB
                results = vector_store.search_similar(user_id, query_vec, limit=3)
                if results:
                    summaries = [f"- {r['content']} ({r['metadata'].get('timestamp', '未知时间')})" for r in results]
                    related_memories = "\n".join(summaries)

        # 3. 组装最终文本
        context_blocks = []
        
        if profile:
            context_blocks.append(f"## 用户画像 (User Profile)\n{profile}")
        else:
            context_blocks.append(f"## 用户画像 (User Profile)\n(暂无详细画像，请在对话中逐步了解用户)")

        if related_memories:
            context_blocks.append(f"## 相关往事回顾 (Related Memories)\n{related_memories}")

        return "\n\n".join(context_blocks)

    async def _flush(self, user_id: str):
        """
        [后台任务] 将 L1 缓存归档到 L2/L3。
        流程: Summarize -> Embed -> Save Vector -> Reflect -> Update Profile
        """
        if not self._buffer[user_id]:
            return

        # 取出并清空缓存 (原子操作般的处理)
        # 注意: 为了线程安全，应该加锁，但 asyncio 单线程模型下，只要不 await 就不怕被插队。
        # 这里的赋值是安全的。
        chat_history = list(self._buffer[user_id])
        self._buffer[user_id].clear()

        # 格式化对话文本
        context_text = "\n".join([msg["content"] for msg in chat_history])

        try:
            # Step 1: 生成摘要 (Summary)
            summary = await self._call_llm(SUMMARY_PROMPT.format(context=context_text))
            if not summary:
                logger.warning("Failed to generate summary, skipping flush.")
                return

            # Step 2: 存入向量库 (L2)
            vec = await embedding_service.get_embedding(summary)
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            vector_store.add_session_summary(
                user_id=user_id,
                summary=summary,
                embedding=vec,
                metadata={"timestamp": timestamp}
            )

            # Step 3: 更新画像 (Reflect)
            current_profile = profile_store.get_profile(user_id) or "（空）"
            new_profile = await self._call_llm(
                REFLECTION_PROMPT.format(current_profile=current_profile, new_summary=summary)
            )

            if new_profile and new_profile != current_profile:
                profile_store.update_profile(user_id, new_profile)
                logger.info(f"User {user_id} profile updated.")

        except Exception as e:
            logger.error(f"Error during memory flush for user {user_id}: {e}")
            # 失败处理：理论上应该把 chat_history 放回 buffer，防止丢失。
            # 但为了简化，暂不回滚。

    async def _call_llm(self, prompt: str) -> str:
        """辅助函数：调用 AI 生成文本"""
        try:
            messages = [{"role": "user", "content": prompt}]
            # 强制不流式，我们需要完整文本
            response = await AIService.chat_completion(messages, stream=False)
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return ""

memory_manager = MemoryManager()
