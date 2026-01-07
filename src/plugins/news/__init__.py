import os
import base64
import re
from datetime import datetime, timedelta
from pathlib import Path

from nonebot import on_command, on_message, get_bot
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.log import logger

from src.common.ai_service import AIService
from src.common.config import GLOBAL_AI_CONFIG
from .data_source import NewsDatabase
from .service import NewsService

# 尝试导入渲染引擎
try:
    from nonebot_plugin_htmlrender import get_new_page
except ImportError:
    logger.error("未找到 nonebot_plugin_htmlrender 插件，PDF 渲染功能将不可用。")

# 路径定义 - 对应 docker-compose 中的挂载点
NEWS_ROOT = Path("/app/data/news")

news_cmd = on_command("news", aliases={"新闻"}, priority=5, block=True)

@news_cmd.handle()
async def handle_news(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    # 1. 解析参数
    arg_list = args.extract_plain_text().strip().split()
    offset = 0
    need_summary = False
    search_keyword = None
    
    # 简单的参数解析逻辑
    if len(arg_list) >= 2 and arg_list[0] in ["search", "搜", "搜索", "find"]:
        search_keyword = arg_list[1]
    else:
        for arg in arg_list:
            if arg in ["summary", "总结", "ai"]:
                need_summary = True
            else:
                try:
                    # 支持传入 -1, -2 等，也支持传入 1, 2
                    val = int(arg)
                    offset = val if val <= 0 else -val
                except ValueError:
                    pass # 忽略非数字非指令参数

    # 2. 计算目标日期
    target_date = datetime.now() + timedelta(days=offset)
    date_str = target_date.strftime("%Y-%m-%d")

    # --- 新增分支：搜索模式 ---
    if search_keyword:
        msg = NewsService.search_news(search_keyword, date_str)
        await news_cmd.finish(msg)

    # 3. 构造 HTML 文件路径
    html_path = NEWS_ROOT / date_str / "html" / "当日汇总.html"
    
    if not html_path.exists():
        if not (NEWS_ROOT / date_str).exists():
            await news_cmd.finish(f"找不到 {date_str} 的新闻数据呢，那天 Miku 还没开始收集呀。")
        else:
            await news_cmd.finish(f"虽然有 {date_str} 的记录，但找不到“当日汇总.html”文件呢。")

    # 4. 开始渲染 PDF (如果只请求总结，其实可以跳过这步，但为了完整性还是发一下PDF作为凭证)
    await news_cmd.send(f"正在准备 {date_str} 的新闻汇总，请稍候... 📅")
    
    # 发送 PDF
    try:
        pdf_bytes = await html_to_pdf(html_path)
        
        # 发送文件
        file_name = f"新闻汇总_{date_str}.pdf"
        file_b64 = base64.b64encode(pdf_bytes).decode('utf-8')
        file_url = f"base64://{file_b64}"
        
        if isinstance(event, GroupMessageEvent):
            await bot.upload_group_file(group_id=event.group_id, file=file_url, name=file_name)
        elif isinstance(event, PrivateMessageEvent):
            await bot.upload_private_file(user_id=event.user_id, file=file_url, name=file_name)
            
    except FinishedException:
        raise
    except Exception as e:
        logger.exception("新闻 PDF 生成或发送失败")
        await news_cmd.send(f"PDF 生成失败了 ({e})，不过 Miku 试试能不能直接发总结...")

    # 5. 如果需要总结，调用 AI
    if need_summary:
        await news_cmd.send("Miku 正在阅读新闻并整理重点，稍等哦... ✨")
        summary_text = await NewsService.generate_summary(date_str)
        await news_cmd.finish(summary_text)

# --- 补充交互：回复文件触发总结 ---

async def is_reply_summary(event: MessageEvent) -> bool:
    """检查是否是回复消息，且内容包含关键词"""
    if not event.reply:
        return False
    text = event.get_plain_text().strip()
    return text in ["summary", "总结", "ai", "AI", "太长不看"]

summary_reply = on_message(rule=is_reply_summary, priority=5, block=True)

@summary_reply.handle()
async def handle_summary_reply(event: MessageEvent, bot: Bot):
    if not event.reply:
        return

    # 尝试从回复的消息中提取文件名
    # 注意：OneBot V11 的 reply 字段可能不包含 file 字段，取决于实现
    # 这里我们尝试解析原始消息内容中的文件名，或者依赖上下文
    # 为了简化，我们假设用户回复的是 bot 发送的 PDF，且我们只能根据日期推断
    # 既然是回复，通常意味着关注的是"那一份"新闻
    
    # 策略：
    # 1. 尝试解析回复消息中的文件名 (如果有)
    # 2. 如果没有，默认假设是对“今天”或“最近一次发送”的新闻进行总结
    # 3. 这里我们做一个简单的假设：用户回复这个指令，就是想看今天的新闻总结（或者让 Miku 猜）
    
    # 但更严谨的做法是：检查 reply 的 sender_id 是否是 bot 自己
    if str(event.reply.sender.user_id) != str(event.self_id):
        return # 不是回复机器人的消息，忽略

    # 尝试匹配文件名中的日期 (如果回复的是文件消息，raw_message 可能会包含文件名)
    # 格式: News_Summary_2026-01-07.pdf
    target_date = datetime.now().strftime("%Y-%m-%d") # 默认今天
    
    # 检查回复内容是否有文件名特征
    reply_raw = str(event.reply.message)
    match = re.search(r"新闻汇总_(\d{4}-\d{2}-\d{2})", reply_raw)
    if match:
        target_date = match.group(1)
    
    await summary_reply.send(f"收到！正在为 {target_date} 的新闻生成 AI 速览...")
    summary_text = await NewsService.generate_summary(target_date)
    await summary_reply.finish(summary_text)


async def html_to_pdf(html_path: Path) -> bytes:
    """使用 Playwright 渲染 HTML 为 PDF"""
    async with get_new_page() as page:
        # 构造 file:// URL
        file_url = f"file://{html_path.absolute()}"
        
        # 设置较大视口以确保图表等元素渲染正常
        await page.set_viewport_size({"width": 1280, "height": 720})
        
        # 访问页面并等待网络空闲
        await page.goto(file_url, wait_until="networkidle")
        
        # 导出 PDF (A4 格式，打印背景)
        return await page.pdf(
            format="A4",
            print_background=True,
            margin={
                "top": "1cm",
                "bottom": "1cm",
                "left": "1cm",
                "right": "1cm"
            }
        )

