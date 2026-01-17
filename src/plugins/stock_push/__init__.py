from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, Bot, GroupMessageEvent, PrivateMessageEvent
from nonebot.params import CommandArg
from nonebot.log import logger
import base64
from .service import StockService

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
        
        msg += "\n💡 Tip: 发送 /stock <代码> 查询详情，或 /stock review 看复盘。"
        await stock_cmd.finish(msg)
        return

    # 2. 特殊指令：复盘 (market review)
    if arg_text in ["review", "复盘", "大盘", "market"]:
        content = StockService.get_market_review_content()
        # 由于内容可能较长，但通常在1000字以内，直接发送文本
        await stock_cmd.finish(f"📅 最新大盘复盘：\n\n{content}")
        return

    # 3. 特殊指令：研报 (analysis report)
    if arg_text in ["report", "研报", "分析", "analysis"]:
        file_path = StockService.get_latest_report_file("report")
        if not file_path:
            await stock_cmd.finish("暂时没有找到最新的 AI 深度研报哦。")
            return
            
        await stock_cmd.send("正在为您提取最新的深度研报 (Markdown文件)... 📑")
        
        try:
            # 发送文件
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

    # 4. 默认行为：查询个股代码
    code = arg_text
    stock_info = StockService.get_stock_info(code)
    if stock_info:
        msg = StockService.format_stock_msg(stock_info)
        await stock_cmd.finish(msg)
    else:
        await stock_cmd.finish(f"找不到代码为 {code} 的股票数据呢，请确认代码是否正确（或尝试 /stock review）。")