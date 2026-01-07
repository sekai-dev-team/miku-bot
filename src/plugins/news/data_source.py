import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
from collections import Counter

class NewsDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def get_longest_running_topics(self, limit: int = 5) -> List[Dict]:
        """获取在线时间最长（抓取次数最多）的新闻"""
        if not self.db_path.exists():
            return []
            
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                # 简单的去重策略：只取 title 唯一的
                query = """
                    SELECT title, platform_id, crawl_count, first_crawl_time, last_crawl_time 
                    FROM news_items 
                    GROUP BY title 
                    ORDER BY crawl_count DESC 
                    LIMIT ?
                """
                cursor.execute(query, (limit,))
                columns = ["title", "platform", "count", "start", "end"]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception:
            return []

    def search_keyword(self, keyword: str) -> Dict:
        """搜索关键词相关新闻统计"""
        if not self.db_path.exists():
            return {"error": "Database not found"}

        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                # 模糊搜索
                query = """
                    SELECT title, platform_id, rank, crawl_count 
                    FROM news_items 
                    WHERE title LIKE ?
                    ORDER BY crawl_count DESC
                """
                cursor.execute(query, (f"%{keyword}%",))
                rows = cursor.fetchall()
                
                if not rows:
                    return {"total": 0, "items": []}

                total_count = len(rows)
                platforms = Counter(row[1] for row in rows)
                
                # 提取不重复的标题 (有些标题可能只是标点不同，这里简单去重)
                unique_titles = list(set(row[0] for row in rows))
                
                # 找出最高排名的记录 (假设 rank 越小越靠前，且 > 0)
                # 注意：有些平台 rank 可能是 -1 或 0 表示无排名
                valid_ranks = [row[2] for row in rows if row[2] > 0]
                best_rank = min(valid_ranks) if valid_ranks else None
                
                return {
                    "total": total_count,
                    "platform_dist": dict(platforms),
                    "titles": unique_titles[:10], # 只返回前10个标题
                    "best_rank": best_rank
                }
        except Exception as e:
            return {"error": str(e)}

    def get_platform_stats(self) -> Dict[str, int]:
        """获取各平台新闻数量统计"""
        if not self.db_path.exists():
            return {}
            
        try:
            with self._connect() as conn:
                cursor = conn.cursor()
                query = "SELECT platform_id, COUNT(*) FROM news_items GROUP BY platform_id"
                cursor.execute(query)
                return dict(cursor.fetchall())
        except Exception:
            return {}
