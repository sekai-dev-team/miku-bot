from collections import deque
from nonebot import get_plugin_config
from nonebot import logger
from .config import Config

CONFIG = get_plugin_config(Config)
class SimulatedGroupMsg:
    def __init__(self, group_id, sender_name, user_role, content) -> None:
        self.info = {
            "group_id": group_id,
            "name": sender_name,
            "role": user_role,
            "content": content
        }

class SimulatedGroupMsgListener:
    def __init__(self) -> None:
        self.group_queues = {}
        self.group_count = 0
        self.MSG_LIMIT = CONFIG.GROUP_MSG_CONTEXT_LIMIT

    def listen(self, group_msg: SimulatedGroupMsg):
        group_id = group_msg.info["group_id"]
        logger.info(f"[Listener] <------ {group_msg.info}")
        if group_id not in self.group_queues:
            self.group_queues[group_id] = deque(maxlen=self.MSG_LIMIT)
            self.group_count += 1
        
        self.group_queues[group_id].append({
            "role": group_msg.info["role"],  
            "content": group_msg.info["content"]  
        })

    def get_context(self, group_id):
        return self.group_queues[group_id]

    def get_stat_detail(self):
        groups = list(self.group_queues.keys())
        group_stat = []
        group_stat.append(f"群总数量: {self.group_count}")
        if self.group_count != 0:
            group_stat.extend(groups)
        return "\n".join(group_stat)