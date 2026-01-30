from typing import List
from sentence_transformers import SentenceTransformer
from nonebot import logger
import functools
import asyncio

class EmbeddingService:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(EmbeddingService, cls).__new__(cls)
        return cls._instance

    def initialize(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        """
        初始化 Embedding 模型。
        强制使用 CPU 设备，避免占用显存。
        """
        if self._model is not None:
            return

        try:
            logger.info(f"Loading embedding model: {model_name} on CPU...")
            # device='cpu' 强制使用 CPU
            self._model = SentenceTransformer(model_name, device='cpu')
            logger.info("Embedding model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise e

    async def get_embedding(self, text: str) -> List[float]:
        """
        获取单条文本的向量 (异步包装)。
        """
        if not text:
            return []
        return (await self.get_embeddings([text]))[0]

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        获取多条文本的向量 (异步包装)。
        """
        if self._model is None:
            # 懒加载默认模型
            self.initialize()
        
        if not texts:
            return []

        try:
            loop = asyncio.get_event_loop()
            # 在线程池中运行推理，避免阻塞主循环
            # normalize_embeddings=True 对余弦相似度搜索很重要
            func = functools.partial(self._model.encode, sentences=texts, normalize_embeddings=True, convert_to_numpy=True)
            embeddings = await loop.run_in_executor(None, func)
            
            # 转换为 Python list
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Error generating embeddings: {e}")
            return []

# 单例导出
embedding_service = EmbeddingService()
