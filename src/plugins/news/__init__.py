import os
import base64
import re
from datetime import datetime, timedelta
from pathlib import Path

from bs4 import BeautifulSoup
from nonebot import on_command, on_message, get_bot
from nonebot.exception import FinishedException
from nonebot.adapters.onebot.v11 import Bot, Message, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import to_me
from nonebot.log import logger

from src.common.ai_service import AIService
from src.common.config import GLOBAL_AI_CONFIG
from .data_source import NewsDatabase

# 尝试导入渲染引擎
try:
    from nonebot_plugin_htmlrender import get_new_page
except ImportError:
    logger.error("未找到 nonebot_plugin_htmlrender 插件，PDF 渲染功能将不可用。")

# 路径定义 - 对应 docker-compose 中的挂载点
NEWS_ROOT = Path("/app/data/news")

news_cmd = on_command("news", aliases={"新闻"}, priority=5, block=True)

# 辅助函数：从 HTML 提取数据
def extract_news_data(html_path: Path) -> str:
    """解析 HTML，提取分类和标题，生成 Prompt 上下文"""
    try:
        content = html_path.read_text(encoding="utf-8")
        soup = BeautifulSoup(content, "html.parser")
        
        output_lines = []
        
        # 1. 提取 word-group (主要热点)
        groups = soup.find_all("div", class_="word-group")
        for group in groups:
            header = group.find("div", class_="word-name")
            if not header:
                continue
            topic = header.get_text(strip=True)
            output_lines.append(f"【话题：{topic}】")
            
            items = group.find_all("div", class_="news-title")
            for idx, item in enumerate(items, 1):
                title = item.get_text(strip=True)
                output_lines.append(f"{idx}. {title}")
            output_lines.append("") # 空行分隔
            
        # 2. 提取 RSS (可选)
        rss_section = soup.find("div", class_="rss-section")
        if rss_section:
            output_lines.append("【RSS 订阅更新】")
            rss_items = rss_section.find_all("div", class_="rss-title")
            for idx, item in enumerate(rss_items, 1):
                title = item.get_text(strip=True)
                output_lines.append(f"{idx}. {title}")
        
        return "\n".join(output_lines)
    except Exception as e:
        logger.error(f"HTML 解析失败: {e}")
        return ""

# 辅助函数：调用 AI 生成总结
async def generate_ai_summary(date_str: str) -> str:
    """读取指定日期的 HTML 并调用 DeepSeek 生成总结"""
    html_path = NEWS_ROOT / date_str / "html" / "当日汇总.html"
    db_path = NEWS_ROOT / "news" / f"{date_str}.db"
    
    if not html_path.exists():
        return "找不到当天的数据文件，无法生成总结呢 (>_<)"
        
    raw_data = extract_news_data(html_path)
    if not raw_data:
        return "数据解析失败，HTML 可能损坏了..."

    # 获取数据库统计信息作为补充上下文
    db_stats_text = ""
    if db_path.exists():
        try:
            db = NewsDatabase(db_path)
            # 1. 获取最持久话题
            long_topics = db.get_longest_running_topics(3)
            if long_topics:
                db_stats_text += "\n【客观数据补充（请参考这些数据来判断热度）】\n"
                db_stats_text += "今日最持久的话题（霸榜时间最长）：\n"
                for t in long_topics:
                    db_stats_text += f"- 《{t['title']}》 ({t['platform']})\n"
            
            # 2. 平台分布
            plat_stats = db.get_platform_stats()
            if plat_stats:
                top_plat = max(plat_stats, key=plat_stats.get)
                db_stats_text += f"今日最活跃平台：{top_plat} (贡献了 {plat_stats[top_plat]} 条热搜)\n"
        except Exception as e:
            logger.error(f"读取 DB 统计失败: {e}")
        
    system_prompt = (
        "你是 Miku，一个元气可爱的 AI 助手。这是今天收集到的新闻热搜列表（仅包含标题和关键词）。"
        "请根据这些标题，整理出一份『今日热点速览』。\n"
        "要求：\n"
        "1. 按话题分类（如：国际风云、科技前沿、社会百态等，你可以根据关键词重新归类，也可以参考原有的关键词）。\n"
        "2. 每个分类下，挑选 1-3 个最重要/最吸睛的标题，用**一句话**概括这个话题下的核心事件（只能基于标题猜测，不要编造细节）。\n"
        "3. 参考【客观数据补充】中的信息，如果某些话题是“持久霸榜”的，请在总结中特别提到（例如：“这件事今天大家都在讨论哦！”）。\n"
        "4. 结尾给一个『Miku 的碎碎念』，评价一下今天的世界。\n"
        "5. 保持格式清晰，使用 Emoji 点缀。\n"
        "6. 字数控制在 500 字以内。"
    )
    
    user_content = f"今日新闻列表:\n{raw_data}\n{db_stats_text}"

    try:
        response = await AIService.chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ])
        
        # 处理流式响应
        full_content = ""
        async for chunk in response:
             if chunk.choices[0].delta.content is not None:
                full_content += chunk.choices[0].delta.content
                
        return full_content
        
    except Exception as e:
        logger.error(f"AI 调用失败: {e}")
        return f"呜... Miku 的大脑（AI服务）连不上了：{e}"

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
        db_path = NEWS_ROOT / "news" / f"{date_str}.db"
        if not db_path.exists():
             await news_cmd.finish(f"找不到 {date_str} 的数据库，无法搜索呢。")
        
        db = NewsDatabase(db_path)
        result = db.search_keyword(search_keyword)
        
        if result.get("error"):
            await news_cmd.finish(f"搜索出错了：{result['error']}")
            
        if result["total"] == 0:
             await news_cmd.finish(f"在 {date_str} 的记录里没有找到关于“{search_keyword}”的新闻呢。")
             
        # 构造搜索结果回复
        msg = f"🔍 关键词【{search_keyword}】({date_str})\n"
        msg += f"共找到 {result['total']} 条相关热搜。\n"
        
        if result['best_rank']:
            msg += f"🔥 最高排名：Top {result['best_rank']}\n"
            
        msg += "📊 平台分布：\n"
        for plat, count in result['platform_dist'].items():
            msg += f"- {plat}: {count} 条\n"
            
        msg += "\n📝 相关标题（前5条）：\n"
        for t in result['titles'][:5]:
            msg += f"- {t}\n"
            
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
        summary_text = await generate_ai_summary(date_str)
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
    summary_text = await generate_ai_summary(target_date)
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

