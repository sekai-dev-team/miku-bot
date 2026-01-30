import sqlite3
import threading
from pathlib import Path
from typing import Optional
from nonebot import logger

class ProfileStore:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProfileStore, cls).__new__(cls)
        return cls._instance

    def initialize(self, db_path: str = "./data/memory/profiles.db"):
        """初始化 SQLite 数据库"""
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_text TEXT NOT NULL,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
        logger.info(f"ProfileStore initialized at {db_path}")

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def get_profile(self, user_id: str) -> str:
        """获取用户画像，如果不存在返回空字符串"""
        if not hasattr(self, 'db_path'):
            self.initialize()
            
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT profile_text FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            return row[0] if row else ""

    def update_profile(self, user_id: str, profile_text: str):
        """更新用户画像"""
        if not hasattr(self, 'db_path'):
            self.initialize()
            
        with self._lock:
            with self._get_conn() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO user_profiles (user_id, profile_text, last_updated)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(user_id) DO UPDATE SET
                        profile_text = excluded.profile_text,
                        last_updated = CURRENT_TIMESTAMP
                """, (user_id, profile_text))
                conn.commit()
                # logger.debug(f"Updated profile for user {user_id}")

profile_store = ProfileStore()
