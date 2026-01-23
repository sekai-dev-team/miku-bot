import os
import base64
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Set

from nonebot import on_command, on_message, get_bot, require
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.log import logger

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from src.common.ai_service import AIService
from src.common.config import GLOBAL_AI_CONFIG
from .data_source import NewsDatabase
from .service import NewsService
from .config import news_config

# 尝试导入 VoiceService
try:
    from src.plugins.voice_module.service import VoiceService
except ImportError:
    VoiceService = None
    logger.warning("VoiceService import failed in news")

# 尝试导入渲染引擎
try:
    from nonebot_plugin_htmlrender import get_new_page
except ImportError:
    logger.error("未找到 nonebot_plugin_htmlrender 插件，PDF 渲染功能将不可用。")

# 路径定义 - 优先从环境变量读取
NEWS_ROOT = Path(os.getenv("NEWS_DATA_PATH", "/app/data/news"))

# --- Subscriber Manager ---
class NewsSubscriberManager:
    DATA_FILE = Path("data/news_subscribers.json")
    
    @classmethod
    def load(cls) -> Set[str]:
        if not cls.DATA_FILE.exists():
            return set()
        try:
            with open(cls.DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(map(str, data.get("groups", [])))
        except Exception as e:
            logger.error(f"Failed to load news subscribers: {e}")
            return set()

    @classmethod
    def save(cls, groups: Set[str]):
        cls.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(cls.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"groups": list(groups)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save news subscribers: {e}")

    @classmethod
    def add(cls, group_id: str):
        groups = cls.load()
        groups.add(str(group_id))
        cls.save(groups)

    @classmethod
    def remove(cls, group_id: str):
        groups = cls.load()
        if str(group_id) in groups:
            groups.remove(str(group_id))
            cls.save(groups)
    
    @classmethod
    def get_all_targets(cls) -> List[int]:
        env_groups = set(map(str, news_config.news_push_groups))
        json_groups = cls.load()
        return [int(g) for g in (env_groups | json_groups) if g.isdigit()]

news_cmd = on_command("news", aliases={"新闻"}, priority=5, block=True)

@news_cmd.handle()
async def handle_news(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    arg_list = args.extract_plain_text().strip().split()
    offset = 0
    need_summary = False
    search_keyword = None
    
    # --- 订阅管理 ---
    if arg_list and arg_list[0] in ["bind", "订阅", "开启推送"]:
        if isinstance(event, GroupMessageEvent):
            NewsSubscriberManager.add(str(event.group_id))
            await news_cmd.finish(f"已开启本群 ({event.group_id}) 的每日新闻播报！")
        else:
            await news_cmd.finish("请在群聊中使用此指令哦。")
        return

    if arg_list and arg_list[0] in ["unbind", "退订", "关闭推送"]:
        if isinstance(event, GroupMessageEvent):
            NewsSubscriberManager.remove(str(event.group_id))
            await news_cmd.finish(f"已关闭本群 ({event.group_id}) 的每日新闻播报。")
        else:
            await news_cmd.finish("请在群聊中使用此指令哦。")
        return
    
    if len(arg_list) >= 2 and arg_list[0] in ["search", "搜", "搜索", "find"]:
        search_keyword = arg_list[1]
    else:
        for arg in arg_list:
            if arg in ["summary", "总结", "ai"]:
                need_summary = True
            else:
                try:
                    val = int(arg)
                    offset = val if val <= 0 else -val
                except ValueError:
                    pass

    target_date = datetime.now() + timedelta(days=offset)
    date_str = target_date.strftime("%Y-%m-%d")

    if search_keyword:
        msg = NewsService.search_news(search_keyword, date_str)
        await news_cmd.finish(msg)

    html_path = NEWS_ROOT / date_str / "html" / "当日汇总.html"
    
    if not html_path.exists():
        if not (NEWS_ROOT / date_str).exists():
            await news_cmd.finish(f"找不到 {date_str} 的新闻数据呢，那天 Miku 还没开始收集呀。")
        else:
            await news_cmd.finish(f"虽然有 {date_str} 的记录，但找不到“当日汇总.html”文件呢。")

    await news_cmd.send(f"正在准备 {date_str} 的新闻汇总，请稍候... 📅")
    
    try:
        pdf_bytes = await html_to_pdf(html_path)
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

    if need_summary:
        await news_cmd.send("Miku 正在阅读新闻并整理重点，稍等哦... ✨")
        summary_text = await NewsService.generate_summary(date_str)
        await news_cmd.finish(summary_text)

# --- 补充交互：回复文件触发总结 ---

async def is_reply_summary(event: MessageEvent) -> bool:
    if not event.reply:
        return False
    text = event.get_plaintext().strip()
    return text in ["summary", "总结", "ai", "AI", "太长不看"]

summary_reply = on_message(rule=is_reply_summary, priority=5, block=True)

@summary_reply.handle()
async def handle_summary_reply(event: MessageEvent, bot: Bot):
    if not event.reply:
        return
    if str(event.reply.sender.user_id) != str(event.self_id):
        return 

    target_date = datetime.now().strftime("%Y-%m-%d") 
    reply_raw = str(event.reply.message)
    match = re.search(r"新闻汇总_(\d{4}-\d{2}-\d{2})", reply_raw)
    if match:
        target_date = match.group(1)
    
    await summary_reply.send(f"收到！正在为 {target_date} 的新闻生成 AI 速览...")
    summary_text = await NewsService.generate_summary(target_date)
    await summary_reply.finish(summary_text)

async def html_to_pdf(html_path: Path) -> bytes:
    async with get_new_page() as page:
        file_url = f"file://{html_path.absolute()}"
        await page.set_viewport_size({"width": 1280, "height": 720})
        await page.goto(file_url, wait_until="networkidle")
        return await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "1cm", "bottom": "1cm", "left": "1cm", "right": "1cm"}
        )

# --- Scheduled Task ---
async def broadcast_daily_news():
    """每日新闻播报任务"""
    targets = NewsSubscriberManager.get_all_targets()
    if not targets:
        logger.info("[News] No targets to push.")
        return

    logger.info(f"[News] Starting broadcast to {len(targets)} groups...")
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    try:
        summary = await NewsService.generate_summary(date_str)
    except Exception as e:
        logger.error(f"[News] Failed to generate summary: {e}")
        return

    if not summary or (len(summary) < 50 and "失败" in summary):
         logger.warning(f"[News] Summary generation might have failed: {summary}")
         return

    try:
        if VoiceService:
            logger.info(f"[News] Synthesizing speech (len={len(summary)})...")
            voice_path = await VoiceService.synthesize(summary, lang="zh")
            with open(voice_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            msg = f"[VOICE:base64://{b64}]"
        else:
            msg = f"【每日新闻】\n{summary}"
    except Exception as e:
        logger.error(f"[News] Voice synthesis failed: {e}")
        msg = f"【每日新闻】\n{summary}"

    try:
        bot = get_bot()
    except ValueError:
        logger.warning("[News] No bot connected.")
        return

    for group_id in targets:
        try:
            await bot.send_group_msg(group_id=group_id, message=msg)
        except Exception as e:
            logger.error(f"[News] Failed to send to group {group_id}: {e}")

# Init Scheduler
try:
    h, m = map(int, news_config.news_push_time.split(":"))
    scheduler.add_job(broadcast_daily_news, "cron", hour=h, minute=m, id="news_daily")
    logger.info(f"[News] Scheduled daily broadcast at {news_config.news_push_time}")
except Exception as e:
    logger.error(f"[News] Failed to schedule task: {e}")
