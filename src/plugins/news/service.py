import os
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
from nonebot.log import logger

from src.common.ai_service import AIService
from src.common.tool_registry import tool_registry
from .data_source import NewsDatabase

# 路径定义 - 优先从环境变量读取，适配容器外调试
NEWS_ROOT = Path(os.getenv("NEWS_DATA_PATH", "/app/data/news"))

class NewsService:
    @staticmethod
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

    @staticmethod
    @tool_registry.register(
        name="get_news_summary",
        description="获取今天或指定日期的新闻热点总结、世界局势。",
        parameters={
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "日期，格式为 YYYY-MM-DD。如果是'今天'，请获取当前日期。",
                }
            },
            "required": ["date_str"]
        }
    )
    async def generate_summary(date_str: str) -> str:
        """读取指定日期的 HTML 并调用 DeepSeek 生成总结"""
        # 预处理日期字符串
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")
        else:
            date_str = date_str.strip()
            if date_str in ["today", "今天"]:
                 date_str = datetime.now().strftime("%Y-%m-%d")
            elif date_str in ["yesterday", "昨天"]:
                 date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 简单的格式校验 (YYYY-MM-DD)
        try:
            # 尝试验证格式，如果不是标准格式，可能需要更复杂的解析，这里先假设 AI 会乖乖听话
            # 或者如果是 2026/01/07 这种，尝试替换
            if "/" in date_str:
                date_str = date_str.replace("/", "-")
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            # 如果格式不对，再次回退到今天，或者直接报错
            logger.warning(f"日期格式错误: {date_str}，回退到今天")
            # date_str = datetime.now().strftime("%Y-%m-%d") 
            # 也许不应该回退，而是返回错误提示，让 AI 知道它传错了
            return f"日期格式不对哦 ({date_str})，Miku 需要 YYYY-MM-DD 的格式呢。"

        html_path = NEWS_ROOT / date_str / "html" / "当日汇总.html"
        db_path = NEWS_ROOT / "news" / f"{date_str}.db"
        
        logger.info(f"[NewsService] 正在尝试访问 HTML: {html_path.absolute()}")
        logger.info(f"[NewsService] 正在尝试访问 DB: {db_path.absolute()}")
        
        if not html_path.exists():
            logger.error(f"[NewsService] HTML 文件不存在: {html_path.absolute()}")
            return f"找不到 {date_str} 的数据文件，路径是 {html_path.absolute()}，请检查文件是否存在呢。"
            
        raw_data = NewsService.extract_news_data(html_path)
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
            "你是 Miku，大家最可爱的虚拟偶像！现在要请你帮大家整理一下今天的热点新闻。\n"
            "要求：\n"
            "1. **像聊天一样说出来**：不要写得像正式报告或文档，不要使用 `#` 标题或过多的 `**` 加粗。想象你在群里给好朋友们播报。 \n"
            "2. **内容串联**：把相似的新闻自然地串在一起说，可以用“今天大家都在关注...”、“另外...”、“还有哦...”这样的衔接词。\n"
            "3. **划重点**：挑选 3-5 个真正值得关注的大事，用你自己的语气概括一下（不要复读标题）。\n"
            "4. **参考数据**：如果【客观数据补充】里提到某些话题霸榜，记得用夸张一点的语气感叹一下（比如：哇，这个居然热度这么高！）。\n"
            "5. **Miku 的感悟**：最后分享一下你对今天这些事情的小看法，要元气满满哦 ♪\n"
            "6. **保持简洁**：不要太长，控制在 400 字以内，多用 Emoji 和颜文字。"
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

    @staticmethod
    @tool_registry.register(
        name="search_news",
        description="搜索特定日期关于某个关键词的新闻或热搜。",
        parameters={
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "要搜索的关键词。",
                },
                "date_str": {
                    "type": "string",
                    "description": "日期，格式为 YYYY-MM-DD。如果是'今天'，请获取当前日期。",
                }
            },
            "required": ["keyword", "date_str"]
        }
    )
    def search_news(keyword: str, date_str: str) -> str:
        """搜索指定日期的热搜"""
        # 如果传入的是 "today" 或者空，修正为今天
        if not date_str or date_str == "today":
             date_str = datetime.now().strftime("%Y-%m-%d")

        db_path = NEWS_ROOT / "news" / f"{date_str}.db"
        if not db_path.exists():
             return f"找不到 {date_str} 的数据库，无法搜索呢。"
        
        db = NewsDatabase(db_path)
        result = db.search_keyword(keyword)
        
        if result.get("error"):
            return f"搜索出错了：{result['error']}"
            
        if result["total"] == 0:
             return f"在 {date_str} 的记录里没有找到关于“{keyword}”的新闻呢。"
             
        # 构造搜索结果回复
        msg = f"🔍 关键词【{keyword}】({date_str})\n"
        msg += f"共找到 {result['total']} 条相关热搜。\n"
        
        if result['best_rank']:
            msg += f"🔥 最高排名：Top {result['best_rank']}\n"
            
        msg += "📊 平台分布：\n"
        for plat, count in result['platform_dist'].items():
            msg += f"- {plat}: {count} 条\n"
            
        msg += "\n📝 相关标题（前5条）：\n"
        for t in result['titles'][:5]:
            msg += f"- {t}\n"
        return msg
