from collections import deque
import time
import re
from nonebot import logger
from .config import plugin_config as CONFIG


class SimulatedGroupMsg:
    def __init__(self, group_id, sender_name, user_role, content) -> None:
        self.info = {
            "group_id": group_id,
            "name": sender_name,
            "role": user_role,
            "content": content,
        }


class SimulatedGroupMsgListener:
    def __init__(self) -> None:
        self.group_queues = {}
        self.group_count = 0
        self.MSG_LIMIT = CONFIG.GROUP_MSG_CONTEXT_LIMIT
        self.CONTEXT_TTL = 3600  # 上下文有效期（秒），例如 1 小时

    def listen(self, group_msg: SimulatedGroupMsg):
        """
        监听并存储群消息，带有简单的过滤器
        """
        content = group_msg.info["content"]
        role = group_msg.info["role"]

        # --- 1. 过滤器 (Filter) ---
        # 忽略空消息
        if not content or not content.strip():
            return

        # 忽略指令消息 (以 / 开头)
        if content.strip().startswith("/"):
            return

        # 简化 CQ 码：把 [CQ:image,...] 替换为 [图片]，避免 token 浪费且干扰 AI
        # 简单正则匹配 CQ 码
        content = re.sub(r"\[CQ:image,[^\]]*\]", "[图片]", content)
        content = re.sub(r"\[CQ:face,[^\]]*\]", "[表情]", content)
        # 如果还有其他不想让 AI 看到的 CQ 码，可以继续加

        # 再次检查清洗后的内容是否为空
        if not content.strip():
            return

        group_id = group_msg.info["group_id"]
        logger.info(f"[Listener] <------ {group_msg.info['name']}: {content}")

        if group_id not in self.group_queues:
            self.group_queues[group_id] = deque(maxlen=self.MSG_LIMIT)
            self.group_count += 1

        # --- 2. 存储 (Storage) ---
        self.group_queues[group_id].append(
            {
                "role": role,
                "name": group_msg.info["name"],
                "content": content,
                "timestamp": time.time(),  # 记录接收时间
            }
        )

    def get_context(self, group_id):
        """
        获取上下文，自动过滤过期消息，并格式化
        """
        if group_id not in self.group_queues:
            return []

        queue = self.group_queues[group_id]
        context = []
        current_time = time.time()

        # 遍历队列
        for msg in queue:
            # --- 4. 格式化 (Formatting) ---
            # 如果是 User，带上名字，让 Miku 知道是谁在说话
            if msg["role"] == CONFIG.ROLE_USER:
                # 格式： Name: content
                # 这种格式有助于 DeepSeek 等模型区分多人对话
                formatted_content = f"{msg['name']}: {msg['content']}"
                context.append({"role": msg["role"], "content": formatted_content})
            else:
                # 如果是 Assistant (Miku自己)，直接放入 content
                context.append({"role": msg["role"], "content": msg["content"]})

        return context

    def get_stat_detail(self):
        groups = list(self.group_queues.keys())
        group_stat = []
        group_stat.append(f"群总数量: {self.group_count}")
        if self.group_count != 0:
            group_stat.extend(groups)
        return "\n".join(group_stat)


# Global Instance
LISTENER = SimulatedGroupMsgListener()
