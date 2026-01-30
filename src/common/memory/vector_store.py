import chromadb
from typing import List, Dict, Any
from pathlib import Path
from nonebot import logger

class VectorStore:
    _instance = None
    _collection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStore, cls).__new__(cls)
        return cls._instance

    def initialize(self, db_path: str = "./data/memory/chroma_db"):
        """初始化 ChromaDB"""
        if self._collection is not None:
            return

        try:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            
            # 使用 PersistentClient 持久化存储
            self.client = chromadb.PersistentClient(path=db_path)
            
            # 获取或创建集合
            # metadata 里的 hnsw:space 定义了距离度量，cosine 适合文本相似度
            self._collection = self.client.get_or_create_collection(
                name="episodic_memory",
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"VectorStore initialized at {db_path}, collection: episodic_memory")
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise e

    def add_session_summary(self, 
                          user_id: str, 
                          summary: str, 
                          embedding: List[float], 
                          metadata: Dict[str, Any]):
        """
        添加会话摘要到向量库
        """
        if self._collection is None:
            self.initialize()

        # 生成唯一 ID (基于时间戳或 UUID，这里简单用 random_uuid)
        import uuid
        doc_id = str(uuid.uuid4())
        
        # 确保 metadata 包含关键信息
        metadata["user_id"] = user_id
        metadata["type"] = "session_summary"

        try:
            self._collection.add(
                documents=[summary],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[doc_id]
            )
            # logger.debug(f"Added session summary for user {user_id}: {doc_id}")
        except Exception as e:
            logger.error(f"Error adding to ChromaDB: {e}")

    def search_similar(self, 
                      user_id: str, 
                      query_embedding: List[float], 
                      limit: int = 3) -> List[Dict[str, Any]]:
        """
        搜索相似的记忆片段
        """
        if self._collection is None:
            self.initialize()

        try:
            # 过滤条件：只搜索该用户的记忆
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where={"user_id": user_id} 
            )
            
            # 解析结果
            # results 结构: {'ids': [['id1', ...]], 'documents': [['text1', ...]], 'metadatas': [[{meta1}, ...]], ...}
            parsed_results = []
            if results["ids"] and len(results["ids"][0]) > 0:
                ids = results["ids"][0]
                docs = results["documents"][0]
                metas = results["metadatas"][0]
                
                for i in range(len(ids)):
                    parsed_results.append({
                        "id": ids[i],
                        "content": docs[i],
                        "metadata": metas[i]
                    })
            
            return parsed_results

        except Exception as e:
            logger.error(f"Error searching ChromaDB: {e}")
            return []

vector_store = VectorStore()
