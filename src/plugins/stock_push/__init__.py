from nonebot import on_command, require, get_bot
from nonebot.adapters.onebot.v11 import Message, MessageEvent, Bot, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.exception import FinishedException
from nonebot.params import CommandArg
from nonebot.log import logger
import base64
import json
import re
from pathlib import Path
from typing import List, Set

require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

from .service import StockService
from .config import stock_config

# 尝试导入 VoiceService
try:
    from src.plugins.voice_module.service import VoiceService
except ImportError:
    VoiceService = None
    logger.warning("VoiceService import failed in stock_push")

# --- Helper: Markdown Cleaner ---
def clean_markdown_for_tts(text: str) -> str:
    """清洗 Markdown 文本，使其适合 TTS 播报"""
    if not text:
        return ""
    
    # 1. 移除图片 ![...](...)
    text = re.sub(r"!\[.*?]\[.*?\(.*?)\)", "", text)
    # 2. 移除链接 [...](...)
    text = re.sub(r"\\[(.*?)\\]\(.*?\)", r"\1", text)
    # 3. 移除标题标记 #, ##, ###
    text = re.sub(r"^#+\\s*", "", text, flags=re.MULTILINE)
    # 4. 移除加粗/斜体 **, *, __, _
    text = re.sub(r"(\*\*|__)(.*?)\1", r"\2", text)
    text = re.sub(r"(\*|_)(.*?)\1", r"\2", text)
    # 5. 移除表格行 (以 | 开头和结尾的行)
    text = re.sub(r"^\\[\s*\|.*\|\\]\s*$", "", text, flags=re.MULTILINE)
    # 6. 移除代码块
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`.*?`", "", text)
    # 7. 压缩多余空行
    text = re.sub(r"\\n\\s*\\n", "\\n", text)
    
    return text.strip()

# --- Helper: Subscriber Manager ---
class SubscriberManager:
    DATA_FILE = Path("data/stock_subscribers.json")
    
    @classmethod
    def load(cls) -> Set[str]:
        if not cls.DATA_FILE.exists():
            return set()
        try:
            with open(cls.DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(map(str, data.get("groups", [])))
        except Exception as e:
            logger.error(f"Failed to load stock subscribers: {e}")
            return set()

    @classmethod
    def save(cls, groups: Set[str]):
        cls.DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(cls.DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({"groups": list(groups)}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stock subscribers: {e}")

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
        """获取所有目标群组 (Env配置 + 动态订阅)"""
        env_groups = set(map(str, stock_config.stock_push_groups))
        json_groups = cls.load()
        total = env_groups | json_groups
        return [int(g) for g in total if g.isdigit()]

# Register the command
stock_cmd = on_command("stock", aliases={"股票", "查股价"}, priority=5, block=True)

@stock_cmd.handle()
async def handle_stock(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    
    # 1. 无参数：默认行为（股市概览）
    if not arg_text:
        latest_date = StockService.get_latest_date()
        if not latest_date:
            await stock_cmd.finish("数据库中暂时没有股票数据哦。")
            return
            
        top_gainers = StockService.get_top_gainers(limit=5)
        msg = f"📊 股市概览 ({latest_date})\n------------------\n🔥 今日涨幅榜:\n"
        for idx, item in enumerate(top_gainers, 1):
            msg += f"{idx}. {item['code']}: {item['close']} ({item['pct_chg']}%)\n"
        
        msg += "\n💡 Tip: 发送 /stock list 查看所有自选股，或 /stock <代码> 查看详情。"
        await stock_cmd.finish(msg)
        return

    # 2. 特殊指令：自选股列表 (watchlist)
    if arg_text in ["list", "列表", "自选", "all"]:
        watchlist = StockService.get_watchlist()
        if not watchlist:
            await stock_cmd.finish("暂时没有获取到自选股数据。")
            return
        
        latest_date = StockService.get_latest_date()
        msg = f"📅 自选股监控清单 ({latest_date})\n"
        msg += "------------------------------\n"
        watchlist.sort(key=lambda x: x['pct_chg'], reverse=True)
        
        for item in watchlist:
            emoji = "🔴" if item['pct_chg'] > 0 else "🟢" if item['pct_chg'] < 0 else "⚪"
            name_part = f"{item['name']} " if 'name' in item and item['name'] != item['code'] else ""
            msg += f"{emoji} {name_part}{item['code']}: {item['close']} ({item['pct_chg']}%) \n"
            
        msg += "\n💡 发送 /stock <代码> 可查看该股的 AI 深度研报卡片。"
        await stock_cmd.finish(msg)
        return

    # 3. 特殊指令：复盘 (market review)
    if arg_text in ["review", "复盘", "大盘", "market"]:
        content = StockService.get_market_review_content()
        await stock_cmd.finish(f"📅 最新大盘复盘：\n\n{content}")
        return

    # 4. 特殊指令：研报 (analysis report) - 发送完整文件
    if arg_text in ["report", "研报", "分析", "analysis"]:
        file_path = StockService.get_latest_report_file("report")
        if not file_path:
            await stock_cmd.finish("暂时没有找到最新的 AI 深度研报哦。")
            return
            
        await stock_cmd.send("正在为您提取最新的深度研报 (Markdown文件)... 📑")
        
        try:
            file_bytes = file_path.read_bytes()
            file_b64 = base64.b64encode(file_bytes).decode('utf-8')
            file_name = file_path.name
            
            if isinstance(event, GroupMessageEvent):
                await bot.upload_group_file(group_id=event.group_id, file=f"base64://{file_b64}", name=file_name)
            elif isinstance(event, PrivateMessageEvent):
                await bot.upload_private_file(user_id=event.user_id, file=f"base64://{file_b64}", name=file_name)
        except Exception as e:
            logger.error(f"Failed to send stock report: {e}")
            await stock_cmd.finish(f"文件发送失败了... ({e})")
        return

    # 5. 特殊指令：订阅管理
    if arg_text in ["bind", "订阅", "开启推送"]:
        if isinstance(event, GroupMessageEvent):
            SubscriberManager.add(str(event.group_id))
            await stock_cmd.finish(f"已开启本群 ({event.group_id}) 的每日股市播报！")
        else:
            await stock_cmd.finish("请在群聊中使用此指令哦。")
        return

    if arg_text in ["unbind", "退订", "关闭推送"]:
        if isinstance(event, GroupMessageEvent):
            SubscriberManager.remove(str(event.group_id))
            await stock_cmd.finish(f"已关闭本群 ({event.group_id}) 的每日股市播报。")
        else:
            await stock_cmd.finish("请在群聊中使用此指令哦。")
        return

    # 6. 个股查询
    code = arg_text
    report_content = StockService.extract_stock_report_section(code)
    if report_content:
        try:
            await stock_cmd.send(f"🔍 正在生成 {code} 的 AI 分析卡片...")
            img_bytes = await StockService.render_stock_card(report_content, is_html=True)
            await stock_cmd.finish(MessageSegment.image(img_bytes))
            return
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"Failed to render stock card for {code}: {e}")
            pass

    # 回退逻辑
    stock_info = StockService.get_stock_info(code)
    if stock_info:
        msg = StockService.format_stock_msg(stock_info)
        extra_hint = "\n(未找到该股的深度研报，仅显示实时行情)" if not report_content else "\n(图片生成失败，转为文本显示)"
        await stock_cmd.finish(msg + extra_hint)
    else:
        await stock_cmd.finish(f"找不到代码为 {code} 的股票数据呢，请确认代码是否正确（或尝试 /stock review）。")

# --- Scheduled Task ---
async def broadcast_daily_stock():
    """每日股市播报任务"""
    targets = SubscriberManager.get_all_targets()
    if not targets:
        logger.info("[StockPush] No targets to push.")
        return

    logger.info(f"[StockPush] Starting broadcast to {len(targets)} groups...")
    
    # 1. 获取内容
    content = StockService.get_market_review_content()
    if not content or len(content) < 10:
        logger.warning("[StockPush] Market review content is empty or too short.")
        return

    # 2. 清洗文本
    clean_text = clean_markdown_for_tts(content)
    if len(clean_text) > 500:
        clean_text = clean_text[:495] + "..."
    
    # 3. 合成语音
    try:
        if VoiceService:
            logger.info(f"[StockPush] Synthesizing speech (len={len(clean_text)})...")
            voice_path = await VoiceService.synthesize(clean_text, lang="zh")
            with open(voice_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            msg = f"[VOICE:base64://{b64}]"
        else:
            msg = f"【每日复盘】\n{clean_text}" 
    except Exception as e:
        logger.error(f"[StockPush] Voice synthesis failed: {e}")
        msg = f"【每日复盘】\n{clean_text}"

    # 4. 推送
    try:
        bot = get_bot()
    except ValueError:
        logger.warning("[StockPush] No bot connected.")
        return

    for group_id in targets:
        try:
            await bot.send_group_msg(group_id=group_id, message=msg)
        except Exception as e:
            logger.error(f"[StockPush] Failed to send to group {group_id}: {e}")

# Init Scheduler
try:
    h, m = map(int, stock_config.stock_push_time.split(":"))
    scheduler.add_job(broadcast_daily_stock, "cron", hour=h, minute=m, id="stock_push_daily")
    logger.info(f"[StockPush] Scheduled daily broadcast at {stock_config.stock_push_time}")
except Exception as e:
    logger.error(f"[StockPush] Failed to schedule task: {e}")
