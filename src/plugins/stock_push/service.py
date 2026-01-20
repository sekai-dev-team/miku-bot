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
    def get_stock_name_map() -> Dict[str, str]:
        """从最新的 report 文件中提取代码到名称的映射"""
        import markdown
        from bs4 import BeautifulSoup

        file_path = StockService.get_latest_report_file("report")
        if not file_path:
            return {}

        name_map = {}
        try:
            content = file_path.read_text(encoding="utf-8")
            # 使用 Markdown 解析结构，比纯正则匹配全文更健壮
            md = markdown.Markdown(extensions=["tables", "fenced_code"])
            html_content = md.convert(content)
            soup = BeautifulSoup(html_content, "html.parser")

            for h2 in soup.find_all("h2"):
                text = h2.get_text().strip()
                # 期望格式: "Emoji Name (Code)"，例如 "⚪ 宁德时代 (300750)"
                # 检查是否以 (6位数字) 结尾
                if len(text) > 8 and text.endswith(")"):
                    # 提取倒数第7位到倒数第1位作为代码
                    potential_code = text[-7:-1]
                    # 确保提取的是数字且前面是左括号
                    if potential_code.isdigit() and text[-8] == "(":
                        code = potential_code
                        # 获取括号前的部分，例如 "⚪ 宁德时代"
                        name_part = text[:-8].strip()
                        # 去除 Emoji (假设 Emoji 与名字间有空格)
                        # Split maxsplit=1: ["⚪", "宁德时代"] -> 取最后一个作为名字
                        parts = name_part.split(maxsplit=1)
                        name = parts[-1] if len(parts) > 0 else name_part

                        name_map[code] = name

        except Exception as e:
            print(f"Error parsing stock names from report: {e}")

        return name_map

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
            "required": ["code"],
        },
    )
    def get_stock_info(code: str) -> Optional[Dict[str, Any]]:
        """Get the latest information for a specific stock code."""
        try:
            with StockService._get_connection() as conn:
                cursor = conn.cursor()
                # Get the latest record for this code
                cursor.execute(
                    """
                    SELECT code, date, open, high, low, close, volume, pct_chg, amount
                    FROM stock_daily 
                    WHERE code = ? 
                    ORDER BY date DESC 
                    LIMIT 1
                """,
                    (code,),
                )

                row = cursor.fetchone()
                if row:
                    # 尝试获取名称
                    name_map = StockService.get_stock_name_map()
                    name = name_map.get(code, code)

                    return {
                        "code": row[0],
                        "name": name,
                        "date": row[1],
                        "open": row[2],
                        "high": row[3],
                        "low": row[4],
                        "close": row[5],
                        "volume": row[6],
                        "pct_chg": row[7],
                        "amount": row[8],
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
                cursor.execute(
                    """
                    SELECT code, close, pct_chg 
                    FROM stock_daily 
                    WHERE date = ? 
                    ORDER BY pct_chg DESC 
                """,
                    (latest_date,),
                )

                # 获取名称映射
                name_map = StockService.get_stock_name_map()

                results = []
                for row in cursor.fetchall():
                    code = row[0]
                    results.append(
                        {
                            "code": code,
                            "name": name_map.get(code, code),
                            "close": row[1],
                            "pct_chg": row[2],
                        }
                    )
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
            "required": [],
        },
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

        emoji = "📈" if data["pct_chg"] > 0 else "📉" if data["pct_chg"] < 0 else "➖"

        # Format amount (e.g. 100000 -> 10万)
        amount_str = (
            f"{data['amount']/100000000:.2f}亿"
            if data["amount"] > 100000000
            else f"{data['amount']/10000:.2f}万"
        )

        # 获取名称（如果有）
        name_str = (
            f" {data['name']}"
            if "name" in data and data["name"] != data["code"]
            else ""
        )

        msg = (
            f"{emoji} {name_str} ({data['code']})\n"
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
        parameters={"type": "object", "properties": {}, "required": []},
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
        返回该段落的 HTML 文本。
        """
        import markdown
        from bs4 import BeautifulSoup

        file_path = StockService.get_latest_report_file("report")
        if not file_path:
            return None

        try:
            content = file_path.read_text(encoding="utf-8")
            
            # Convert full MD to HTML first to parse structure reliably
            md = markdown.Markdown(extensions=["tables", "fenced_code"])
            html_content = md.convert(content)
            
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Find the H2 header containing the code
            # We iterate to find the one containing "(code)"
            target_header = None
            for h2 in soup.find_all("h2"):
                if f"({code})" in h2.get_text():
                    target_header = h2
                    break
            
            if not target_header:
                return None
            
            # Collect content: Header + all siblings until next H2
            section_parts = [str(target_header)]
            for sibling in target_header.next_siblings:
                if sibling.name == "h2":
                    break
                # sibling can be a Tag or NavigableString
                section_parts.append(str(sibling))
                
            return "".join(section_parts)

        except Exception as e:
            print(f"Error extracting stock report: {e}")
            return None

    @staticmethod
    async def render_stock_card(content: str, is_html: bool = False) -> bytes:
        """
        将 Markdown 或 HTML 内容渲染为图片。
        :param content: Markdown 文本 或 HTML 片段
        :param is_html: 如果为 True，则跳过 Markdown 转换直接渲染
        """
        import markdown
        from nonebot_plugin_htmlrender import html_to_pic

        # 1. Prepare HTML body
        if is_html:
            html_body = content
        else:
            html_body = markdown.markdown(
                content, extensions=["tables", "fenced_code"]
            )

        # 2. Construct full HTML with custom CSS
        css = """
            body {
                font-family: "Microsoft YaHei", "Heiti SC", sans-serif;
                padding: 20px;
                background-color: #f0f2f5;
                margin: 0;
            }
            .card {
                box-sizing: border-box;
                width: 600px;
                padding: 30px;
                background-color: #ffffff;
                border-radius: 12px;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
                margin: 0 auto;
            }
            h2 { 
                border-bottom: 2px solid #eaecef; 
                padding-bottom: .3em; 
                color: #24292e; 
                font-size: 1.5em;
                margin-top: 0;
            }
            h3 { color: #24292e; margin-top: 24px; font-size: 1.25em; }
            p { line-height: 1.6; color: #333; }
            blockquote { color: #6a737d; border-left: .25em solid #dfe2e5; padding: 0 1em; margin: 0; }
            table { border-collapse: collapse; width: 100%; margin: 15px 0; }
            th, td { border: 1px solid #dfe2e5; padding: 6px 13px; }
            th { background-color: #f6f8fa; font-weight: 600; }
            tr:nth-child(2n) { background-color: #f6f8fa; }
            code { background-color: rgba(27,31,35,.05); border-radius: 3px; font-size: 85%; margin: 0; padding: .2em .4em; }
        """

        html_content = f"""
        <html>
        <head>
            <style>{css}</style>
        </head>
        <body>
            <div class="card">
                {html_body}
            </div>
        </body>
        </html>
        """

        # 3. Render directly from HTML string
        return await html_to_pic(
            html=html_content,
            viewport={"width": 650, "height": 100},  # Height will auto-expand
        )
