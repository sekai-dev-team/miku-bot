from nonebot import on_command
from nonebot.adapters.onebot.v11 import Message, MessageEvent, Bot, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.exception import FinishedException
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
        # 排序：涨幅从高到低
        watchlist.sort(key=lambda x: x['pct_chg'], reverse=True)
        
        for item in watchlist:
            emoji = "🔴" if item['pct_chg'] > 0 else "🟢" if item['pct_chg'] < 0 else "⚪"
            # 兼容A股红涨绿跌习惯，或者根据Emoji: 🔴涨 🟢跌
            msg += f"{emoji} {item['code']}: {item['close']} ({item['pct_chg']}%) \n"
            
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

    # 5. 个股查询：尝试生成图片卡片，失败则回退到纯文本
    code = arg_text
    
    # 尝试提取研报内容并渲染图片
    report_content = StockService.extract_stock_report_section(code)
    if report_content:
        try:
            await stock_cmd.send(f"🔍 正在生成 {code} 的 AI 分析卡片...")
            img_bytes = await StockService.render_stock_card(report_content)
            await stock_cmd.finish(MessageSegment.image(img_bytes))
            return
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"Failed to render stock card for {code}: {e}")
            # 渲染失败，继续执行下方的文本回退逻辑
            pass

    # 回退逻辑：查询 DB 纯数据
    stock_info = StockService.get_stock_info(code)
    if stock_info:
        msg = StockService.format_stock_msg(stock_info)
        extra_hint = "\n(未找到该股的深度研报，仅显示实时行情)" if not report_content else "\n(图片生成失败，转为文本显示)"
        await stock_cmd.finish(msg + extra_hint)
    else:
        await stock_cmd.finish(f"找不到代码为 {code} 的股票数据呢，请确认代码是否正确（或尝试 /stock review）。")
