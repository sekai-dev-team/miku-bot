import sqlite3
import random
from pathlib import Path
import nonebot_plugin_localstore as store
from nonebot import logger

class HistoryManager:
    def __init__(self):
        # 获取插件的数据目录，例如 data/history_book/history.db
        self.data_dir = store.get_plugin_data_dir()
        self.db_path = self.data_dir / "history.db"
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """初始化数据库表结构"""
        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)
            
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS group_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    group_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    user_name TEXT,
                    content TEXT NOT NULL,
                    msg_type TEXT DEFAULT 'text',
                    timestamp INTEGER NOT NULL,
                    recorder_id TEXT
                )
            """)
            conn.commit()

    def add_history(self, group_id: str, user_id: str, user_name: str, content: str, msg_type: str, timestamp: int, recorder_id: str):
        """添加一条黑历史"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO group_history (group_id, user_id, user_name, content, msg_type, timestamp, recorder_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (group_id, user_id, user_name, content, msg_type, timestamp, recorder_id))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add history: {e}")
            return False

    def get_random_history(self, group_id: str):
        """随机获取一条该群的黑历史"""
        try:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                # 随机排序取一条，效率在数据量不大时可以接受
                cursor.execute("""
                    SELECT user_name, content, timestamp, user_id FROM group_history
                    WHERE group_id = ?
                    ORDER BY RANDOM()
                    LIMIT 1
                """, (group_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "user_name": row[0],
                        "content": row[1],
                        "timestamp": row[2],
                        "user_id": row[3]
                    }
                return None
        except Exception as e:
            logger.error(f"Failed to get random history: {e}")
            return None

# 全局单例
history_manager = HistoryManager()
