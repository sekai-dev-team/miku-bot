import os
from datetime import datetime, timedelta
from pathlib import Path

from nonebot import on_command, get_bot
from nonebot.adapters.onebot.v11 import Message, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.log import logger

# 尝试导入渲染引擎
try:
    from nonebot_plugin_htmlrender import get_new_page
except ImportError:
    logger.error("未找到 nonebot_plugin_htmlrender 插件，PDF 渲染功能将不可用。")

# 路径定义 - 对应 docker-compose 中的挂载点
NEWS_ROOT = Path("/app/data/news")

news_cmd = on_command("news", aliases={"新闻"}, priority=5, block=True)

@news_cmd.handle()
async def handle_news(event: MessageEvent, args: Message = CommandArg()):
    # 1. 解析参数 (offset)
    arg_str = args.extract_plain_text().strip()
    offset = 0
    if arg_str:
        try:
            # 支持传入 -1, -2 等，也支持传入 1, 2 (自动转为负数处理，符合直觉)
            val = int(arg_str)
            offset = val if val <= 0 else -val
        except ValueError:
            await news_cmd.finish("参数错误呢，请输入数字（如：/news -1 表示昨天）")

    # 2. 计算目标日期
    target_date = datetime.now() + timedelta(days=offset)
    date_str = target_date.strftime("%Y-%m-%d")
    
    # 3. 构造 HTML 文件路径
    # 结构: {date}/html/当日汇总.html
    html_path = NEWS_ROOT / date_str / "html" / "当日汇总.html"
    
    if not html_path.exists():
        if not (NEWS_ROOT / date_str).exists():
            await news_cmd.finish(f"找不到 {date_str} 的新闻数据呢，那天 Miku 还没开始收集呀。")
        else:
            await news_cmd.finish(f"虽然有 {date_str} 的记录，但找不到“当日汇总.html”文件呢。")

    # 4. 开始渲染 PDF
    await news_cmd.send(f"正在准备 {date_str} 的新闻汇总 PDF，请稍候...")
    
    try:
        pdf_bytes = await html_to_pdf(html_path)
        
        # 5. 临时保存 PDF (保留作为备份/缓存)
        temp_dir = Path("/tmp/miku_news")
        temp_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"News_Summary_{date_str}.pdf"
        temp_pdf_path = temp_dir / file_name
        temp_pdf_path.write_bytes(pdf_bytes)
        
        # 6. 发送文件 (使用 MessageSegment 发送 bytes，避免跨容器路径问题)
        # 虽然这会作为文件消息发送而不是上传到群文件，但兼容性最好
        await news_cmd.finish(MessageSegment.file(pdf_bytes, name=file_name))
            
    except Exception as e:
        logger.exception("新闻 PDF 生成失败")
        await news_cmd.finish(f"抱歉，生成 PDF 过程中出现了点小问题：{str(e)}")

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
