import sqlite3
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any
from nonebot_plugin_htmlrender import md_to_pic

# 优先从环境变量读取，默认指向容器内挂载点
STOCK_ROOT = Path(os.getenv("STOCK_DATA_PATH", "/app/data/stock"))
# 如果容器路径不存在（比如本地调试），则回退到本地相对路径（仅作为 fallback）
if not STOCK_ROOT.exists():
    STOCK_ROOT = Path("src/common/resources")

DB_PATH = STOCK_ROOT / "data" / "stock_analysis.db"
# 如果是旧的目录结构（src/common/resources/stock_analysis.db直接存在），也要兼容
if not DB_PATH.exists() and (STOCK_ROOT / "stock_analysis.db").exists():
    DB_PATH = STOCK_ROOT / "stock_analysis.db"

REPORTS_PATH = STOCK_ROOT / "reports"

from src.common.tool_registry import tool_registry

class StockService:
    @staticmethod
    def _get_connection():
        if not DB_PATH.exists():
             # 尝试寻找本地开发路径作为最后手段
             dev_path = Path("src/common/resources/stock_analysis.db")
             if dev_path.exists():
                 return sqlite3.connect(dev_path)
             raise FileNotFoundError(f"Database not found at {DB_PATH}")
        return sqlite3.connect(DB_PATH)

    @staticmethod
    def get_latest_date() -> Optional[str]:
        """Get the latest date available in the database."""
        try:
            with StockService._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(date) FROM stock_daily")
                result = cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"Error getting latest date: {e}")
            return None

    @staticmethod
    @tool_registry.register(
        name="get_stock_info",
        description="获取特定股票代码的最新行情数据（收盘价、涨跌幅等）。",
        parameters={
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "股票代码（6位数字，如 '300750'）",
                }
            },
            "required": ["code"]
        }
    )
    def get_stock_info(code: str) -> Optional[Dict[str, Any]]:
        """Get the latest information for a specific stock code."""
        try:
            with StockService._get_connection() as conn:
                cursor = conn.cursor()
                # Get the latest record for this code
                cursor.execute("""
                    SELECT code, date, open, high, low, close, volume, pct_chg, amount
                    FROM stock_daily 
                    WHERE code = ? 
                    ORDER BY date DESC 
                    LIMIT 1
                """, (code,))
                
                row = cursor.fetchone()
                if row:
                    return {
                        "code": row[0],
                        "date": row[1],
                        "open": row[2],
                        "high": row[3],
                        "low": row[4],
                        "close": row[5],
                        "volume": row[6],
                        "pct_chg": row[7],
                        "amount": row[8]
                    }
                return None
        except Exception as e:
            print(f"Error getting stock info for {code}: {e}")
            return None

    @staticmethod
    def get_watchlist() -> List[Dict[str, Any]]:
        """获取最新的自选股列表（基于最新日期）"""
        latest_date = StockService.get_latest_date()
        if not latest_date:
            return []
            
        try:
            with StockService._get_connection() as conn:
                cursor = conn.cursor()
                # 获取当日所有股票及其涨跌幅
                cursor.execute("""
                    SELECT code, close, pct_chg 
                    FROM stock_daily 
                    WHERE date = ? 
                    ORDER BY pct_chg DESC 
                """, (latest_date,))
                
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "code": row[0],
                        "close": row[1],
                        "pct_chg": row[2]
                    })
                return results
        except Exception as e:
            print(f"Error getting watchlist: {e}")
            return []

    @staticmethod
    @tool_registry.register(
        name="get_market_overview",
        description="获取股市概览，包括最新的交易日期和涨幅榜前几名的股票。",
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "返回的涨幅榜股票数量，默认为 5。",
                }
            },
            "required": []
        }
    )
    def get_top_gainers(limit: int = 5) -> List[Dict[str, Any]]:
        """Get top gainers for the latest available date."""
        # 既然是自选股，Top Gainers 其实就是 Watchlist 的前几名
        watchlist = StockService.get_watchlist()
        return watchlist[:limit]

    @staticmethod
    def format_stock_msg(data: Dict[str, Any]) -> str:
        """Format stock data into a readable message."""
        if not data:
            return "未找到该股票数据。"
            
        emoji = "📈" if data['pct_chg'] > 0 else "📉" if data['pct_chg'] < 0 else "➖"
        
        # Format amount (e.g. 100000 -> 10万)
        amount_str = f"{data['amount']/100000000:.2f}亿" if data['amount'] > 100000000 else f"{data['amount']/10000:.2f}万"
        
        msg = (
            f"{emoji} 股票代码: {data['code']}\n"
            f"📅 日期: {data['date']}\n"
            f"------------------\n"
            f"💰 收盘: {data['close']} ({data['pct_chg']}%)\n"
            f"🌅 开盘: {data['open']}\n"
            f"🔺 最高: {data['high']}\n"
            f"🔻 最低: {data['low']}\n"
            f"📊 成交额: {amount_str}"
        )
        return msg

    @staticmethod
    def get_latest_report_file(prefix: str) -> Optional[Path]:
        """
        寻找最新的报告文件。
        :param prefix: 文件名前缀，如 "market_review" 或 "report"
        :return: 文件路径或 None
        """
        if not REPORTS_PATH.exists():
            return None
        
        # 查找所有匹配前缀的 .md 文件
        files = list(REPORTS_PATH.glob(f"{prefix}_*.md"))
        if not files:
            return None
            
        # 按文件名（通常包含日期）倒序排列
        files.sort(key=lambda x: x.name, reverse=True)
        return files[0]

    @staticmethod
    @tool_registry.register(
        name="get_market_review_content",
        description="获取最新的大盘复盘报告（Market Review）的内容文本。",
        parameters={
             "type": "object",
             "properties": {},
             "required": []
        }
    )
    def get_market_review_content() -> str:
        """读取最新的 market_review 文本"""
        file_path = StockService.get_latest_report_file("market_review")
        if not file_path:
            return "暂时没有找到最新的大盘复盘报告哦。"
        
        try:
            return file_path.read_text(encoding="utf-8")
        except Exception as e:
            return f"读取报告出错: {e}"

    @staticmethod
    def extract_stock_report_section(code: str) -> Optional[str]:
        """
        从最新的 report_*.md 中提取特定股票的段落。
        假设格式为: ## 🟢 股票名 (Code)
        """
        file_path = StockService.get_latest_report_file("report")
        if not file_path:
            return None
        
        try:
            content = file_path.read_text(encoding="utf-8")
            # 匹配模式：
            # ## [emoji] 股票名 (code) ... 到下一个 ## 或 ---
            # 这里的 code 是传入的 code 参数
            # 考虑到可能有正则特殊字符，使用 re.escape 并不是完全适用，因为我们要匹配 markdown 结构
            
            # 搜索标题行，类似 "## 🟢 XD工业富 (601138)"
            # 我们寻找包含 `(code)` 的二级标题
            pattern = re.compile(rf"^##\s+.*?\({code}\).*?$(.*?)(?=^##|\Z)", re.MULTILINE | re.DOTALL)
            
            match = pattern.search(content)
            if match:
                # 提取出的内容包含标题本身（因为group(0)会包含，但这里使用了group(1)提取content）
                # 等等，上面的正则 group(1) 是 (.*?)，也就是标题后的内容。
                # 我们希望包含标题，以便知道是哪只股票
                
                # 重新调整正则：捕获整个块
                full_pattern = re.compile(rf"(^##\s+.*?\({code}\).*?)(?=^##|---|\Z)", re.MULTILINE | re.DOTALL)
                full_match = full_pattern.search(content)
                if full_match:
                    return full_match.group(1).strip()
            return None
        except Exception as e:
            print(f"Error extracting stock report: {e}")
            return None

    @staticmethod
    async def render_stock_card(markdown_content: str) -> bytes:
        """
        将 Markdown 内容渲染为图片。
        使用 nonebot_plugin_htmlrender
        """
        # 添加一些自定义 CSS 来美化卡片
        css = """
            body {
                font-family: "Microsoft YaHei", "Heiti SC", sans-serif;
                padding: 20px;
                background-color: #f0f2f5;
            }
            .markdown-body {
                box-sizing: border-box;
                min-width: 200px;
                max-width: 600px;
                margin: 0 auto;
                padding: 30px;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
            }
            h2 { border-bottom: 2px solid #eaecef; padding-bottom: .3em; color: #24292e; }
            h3 { color: #24292e; margin-top: 24px; }
            blockquote { color: #6a737d; border-left: .25em solid #dfe2e5; padding: 0 1em; margin: 0; }
            table { border-collapse: collapse; width: 100%; margin: 15px 0; }
            th, td { border: 1px solid #dfe2e5; padding: 6px 13px; }
            th { background-color: #f6f8fa; font-weight: 600; }
            tr:nth-child(2n) { background-color: #f6f8fa; }
        """
        
        # 使用 md_to_pic 直接转换，它会自动处理 markdown 解析
        # width 设置为 600 左右比较适合手机查看
        return await md_to_pic(
            md=markdown_content,
            css=css,
            width=650
        )
