from datetime import datetime
from typing import Optional, Dict
from .manager import history_manager
from src.common.tool_registry import tool_registry

class HistoryService:
    @staticmethod
    def add_history(group_id: str, user_id: str, user_name: str, content: str, msg_type: str, timestamp: int, recorder_id: str) -> bool:
        """记录黑历史"""
        return history_manager.add_history(group_id, user_id, user_name, content, msg_type, timestamp, recorder_id)

    @staticmethod
    @tool_registry.register(
        name="get_random_history",
        description="随机获取一条群友的黑历史（语录）。当你想‘处刑’某人或回顾有趣往事时使用。",
        parameters={
            "type": "object",
            "properties": {
                "group_id": {
                    "type": "string",
                    "description": "群号 (Group ID)。请务必从上下文信息中获取当前群号传入。",
                }
            },
            "required": ["group_id"]
        }
    )
    def get_random_history_formatted(group_id: str) -> str:
        """获取并格式化一条随机黑历史（供 AI 使用）"""
        history = history_manager.get_random_history(group_id)
        
        if not history:
            return "（查找结果：该群暂时没有黑历史记录）"

        # 格式化日期
        date_str = datetime.fromtimestamp(history['timestamp']).strftime('%Y-%m-%d')
        
        # 返回结构化文本，方便 AI 理解
        return (
            f"【黑历史记录】\n"
            f"时间：{date_str}\n"
            f"当事人：{history['user_name']} (ID: {history['user_id']})\n"
            f"内容：{history['content']}"
        )