from nonebot import on_message, on_notice, logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, PokeNotifyEvent, Message
from nonebot.rule import Rule
from nonebot.typing import T_State
from datetime import datetime
import time

from .config import plugin_config
from .manager import history_manager

# --- 规则定义 ---

async def is_record_request(event: GroupMessageEvent) -> bool:
    """
    判断是否是记录请求：
    1. 必须有回复 (event.reply)
    2. 当前消息内容必须是触发词 (纯文本匹配)
    """
    if not event.reply:
        return False
    
    # 获取纯文本内容并去除首尾空格
    text = event.get_plaintext().strip()
    return text in plugin_config.RECORD_KEYWORDS

async def is_review_request(event: GroupMessageEvent) -> bool:
    """判断是否是回顾请求 (关键词触发)"""
    text = event.get_plaintext().strip()
    return text in plugin_config.REVIEW_KEYWORDS

async def is_poke_request(event: PokeNotifyEvent, bot: Bot) -> bool:
    """判断是否是戳一戳 Bot 请求"""
    return plugin_config.ENABLE_POKE and \
           event.target_id == int(bot.self_id)

# --- Matchers ---

# 1. 记录黑历史
record_matcher = on_message(rule=is_record_request, priority=5, block=True)

@record_matcher.handle()
async def _(event: GroupMessageEvent):
    # 获取被回复的消息对象
    reply = event.reply
    if not reply:
        return

    # 提取信息
    group_id = str(event.group_id)
    user_id = str(reply.sender.user_id)
    user_name = reply.sender.nickname or reply.sender.card or "神秘人"
    # 获取原始消息内容 (包含CQ码)
    content = str(reply.message)
    timestamp = int(time.time())
    recorder_id = str(event.user_id)

    # 保存
    success = history_manager.add_history(
        group_id, user_id, user_name, content, "text", timestamp, recorder_id
    )

    if success:
        # 随机回复一个确认
        replies = ["📸 咔嚓！已记录在案~", "✍️ 这种话也敢说，我记下来了！", "已入典！"]
        import random
        await record_matcher.finish(random.choice(replies), at_sender=True)
    else:
        await record_matcher.finish("记录失败了...是不是我的本子满了？(>_<)")


# 2. 随机回顾 (关键词触发)
review_cmd_matcher = on_message(rule=is_review_request, priority=5, block=True)

@review_cmd_matcher.handle()
async def send_random_history(bot: Bot, event: GroupMessageEvent):
    group_id = str(event.group_id)
    history = history_manager.get_random_history(group_id)

    if not history:
        await review_cmd_matcher.finish("这个群还没有黑历史哦... 要不你先贡献一条？(¬‿¬)")

    # 格式化输出
    # 转换时间戳
    date_str = datetime.fromtimestamp(history['timestamp']).strftime('%Y-%m-%d')
    
    # 构造消息
    msg = (
        f"📅 {date_str}\n"
        f"👤 {history['user_name']} ({history['user_id']}) 说：\n"
        f"“{history['content']}”"
    )
    
    await review_cmd_matcher.finish(msg)


# 3. 随机回顾 (戳一戳触发)
poke_matcher = on_notice(rule=is_poke_request, priority=5, block=True)

@poke_matcher.handle()
async def _(bot: Bot, event: PokeNotifyEvent):
    # PokeNotifyEvent 也有 group_id，但可能是 None (私聊戳)
    # 这里我们只处理群聊戳
    if not getattr(event, 'group_id', None):
        return

    group_id = str(event.group_id)
    history = history_manager.get_random_history(group_id)

    if not history:
        # 如果没有历史，就随便卖个萌
        await poke_matcher.finish("别戳啦，还没有黑历史可以看呢！")

    date_str = datetime.fromtimestamp(history['timestamp']).strftime('%Y-%m-%d')
    
    # 稍微不同的文案
    msg = (
        f"既然你诚心诚意地戳了...\n"
        f"📅 {date_str}\n"
        f"👤 {history['user_name']} 说：\n"
        f"“{history['content']}”"
    )
    
    await poke_matcher.finish(msg)
