from typing import List, Dict, Optional
import time
import re
from nonebot import logger
from .config import plugin_config as CONFIG
from src.common.token_utils import estimate_messages_token


class SimulatedGroupMsg:
    def __init__(self, group_id, sender_name, user_role, content) -> None:
        self.info = {
            "group_id": group_id,
            "name": sender_name,
            "role": user_role,
            "content": content,
        }


class FullContextManager:
    """
    基于会话批处理 (Session-based Batching) 的全量上下文管理器。

    Structure:
    - Pending Buffer (A): 临时存储区，存放自上次 AI 响应后的新消息。
    - Committed History (B): 长期存储区，存放已确认的 AI 对话历史（用于缓存命中）。
    """

    def __init__(self) -> None:
        # A: Pending Buffer -> {group_id: [msg_string, ...]}
        self._pending_buffer: Dict[str, List[str]] = {}

        # B: Committed History -> {group_id: [{"role": "user", "content": ...}, ...]}}
        self._committed_history: Dict[str, List[Dict[str, str]]] = {}

        self.group_count = 0

        # Token Watermarks (High/Low)
        # DeepSeek 128k = ~128,000 tokens
        # Reserve 4k for output, buffer limit to ~120k?
        # Let's start conservative: 64k limit to test
        self.HIGH_WATERMARK = 60000  # Start pruning above this
        self.LOW_WATERMARK = 45000  # Prune down to this

    def _format_msg_content(self, msg: SimulatedGroupMsg) -> Optional[str]:
        """清洗并格式化单条消息"""
        content = msg.info["content"]
        name = msg.info["name"]

        # 1. 基础过滤
        if not content or not content.strip():
            return None
        if content.strip().startswith("/"):  # Ignore commands
            return None

        # 2. CQ 码清洗
        content = re.sub(r"\[CQ:image,[^]]*\]", "[图片]", content)
        content = re.sub(r"\[CQ:face,[^]]*\]", "[表情]", content)
        content = re.sub(r"\[CQ:json,[^]]*\]", "[卡片消息]", content)
        content = re.sub(r"\[CQ:xml,[^]]*\]", "[卡片消息]", content)

        if not content.strip():
            return None

        # 3. 格式化: "Name: Content"
        return f"{name}: {content}"

    def listen(self, group_msg: SimulatedGroupMsg):
        """
        监听群消息，并追加到 Pending Buffer (A)。
        """
        formatted = self._format_msg_content(group_msg)
        if not formatted:
            return

        group_id = group_msg.info["group_id"]

        # Init storage if new
        if group_id not in self._pending_buffer:
            self._pending_buffer[group_id] = []
            self.group_count += 1
        if group_id not in self._committed_history:
            self._committed_history[group_id] = []

        # 追加到 Buffer A
        self._pending_buffer[group_id].append(formatted)
        logger.info(f"[Context] Pending Buffer Append <--- {formatted}")

    def get_context_and_prepare_commit(self, group_id: str) -> List[Dict[str, str]]:
        """
        获取用于 API 请求的完整上下文 (System + History + Current_Batch)。
        此操作不会清空 Buffer，Buffer 的清空必须在 commit_transaction 中显式调用。

        Return:
          context: 用于 API 的 messages 列表（不含 System Prompt，System Prompt 由调用方添加）
        """
        history = self._committed_history.get(group_id, [])
        pending = self._pending_buffer.get(group_id, [])

        logger.debug(f"[Context] Retrieving context for {group_id}: History={len(history)}, Pending={len(pending)}")

        if not pending:
            # 只有历史，没有新消息（可能是直接被唤醒？）
            # 这种情况下，虽然没有新 User 消息，但为了逻辑统一，
            # 我们可能还是返回 History。调用方需要判断 pending 是否为空来决定是否真的调用 API。
            # 这里我们假定调用方只有在 Pending 不为空时才会调用。
            # 或者，如果是用户手动 /chat 触发，可能 pending 为空？
            # 暂且返回 history。
            return list(history)

        # Merge Pending Buffer into one User Block
        merged_content = "\n".join(pending)

        # Construct Request Context: History + New User Block
        # 注意：这里我们返回的是 Python List，调用方会加上 System Prompt
        request_context = list(history)
        request_context.append({"role": "user", "content": merged_content})

        return request_context

    def commit_transaction(self, group_id: str, ai_response_content: str):
        """
        API 请求成功后，提交事务。
        1. 将 Pending Buffer (A) 打包移入 History (B)。
        2. 将 AI Response 移入 History (B)。
        3. 清空 Pending Buffer (A)。
        4. 检查 History (B) 水位线并执行修剪。
        """
        if group_id not in self._pending_buffer:
            return  # Should not happen

        pending = self._pending_buffer.get(group_id, [])
        
        logger.info(f"[Context] Committing transaction for {group_id}. Pending={len(pending)}, AI Response Len={len(ai_response_content)}")

        # 1. Commit User Batch
        if pending:
            merged_content = "\n".join(pending)
            self._committed_history.setdefault(group_id, []).append(
                {"role": "user", "content": merged_content}
            )

        # 2. Commit AI Response
        if ai_response_content:
            self._committed_history.setdefault(group_id, []).append(
                {"role": "assistant", "content": ai_response_content}
            )

        # 3. Clear Buffer
        self._pending_buffer[group_id] = []
        
        # 4. Prune History (Watermark Strategy)
        self._prune_history(group_id)

    def _prune_history(self, group_id: str):
        """
        基于 Token 水位线修剪历史记录。
        策略：如果 > HIGH_WATERMARK，则删除头部直到 < LOW_WATERMARK。
        """
        history = self._committed_history.get(group_id, [])
        if not history:
            return

        current_tokens = estimate_messages_token(history)

        if current_tokens > self.HIGH_WATERMARK:
            logger.warning(
                f"[Context] Group {group_id} tokens {current_tokens} > {self.HIGH_WATERMARK}. Pruning..."
            )

            original_len = len(history)

            # Pruning Loop
            while history and current_tokens > self.LOW_WATERMARK:
                # 移除最早的一轮 (通常是 User + Assistant，但也可能不对称，简单起见逐条删)
                # 为了保持对话完整性，最好成对删除，或者至少保证首条是 User？
                # DeepSeek 对首条是不是 User 不敏感，只要格式对就行。
                removed = history.pop(0)
                # 重新估算 (为了性能，其实可以减去 removed 的 token，这里简化重算)
                current_tokens = estimate_messages_token(history)

            logger.info(
                f"[Context] Pruned {original_len - len(history)} msgs. Current tokens: {current_tokens}"
            )

    def get_stat_detail(self):
        groups = list(self._pending_buffer.keys())
        group_stat = []
        group_stat.append(f"群总数量: {self.group_count}")
        for gid in groups:
            h_len = len(self._committed_history.get(gid, []))
            p_len = len(self._pending_buffer.get(gid, []))
            group_stat.append(f"Group {gid}: History={h_len}, Pending={p_len}")
        return "\n".join(group_stat)

    @property
    def active_groups(self) -> List[str]:
        return list(self._pending_buffer.keys())


# Global Instance
LISTENER = FullContextManager()
