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
    def extract_news_data(html_path: Path, keywords: list[str] = None) -> str:
        """解析 HTML，提取分类和标题，生成 Prompt 上下文。支持关键词筛选。"""
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
                
                # 如果有关键词，先检查话题名
                topic_match = False
                if keywords:
                    for kw in keywords:
                        if kw.lower() in topic.lower():
                            topic_match = True
                            break
                
                items = group.find_all("div", class_="news-title")
                filtered_items = []
                for idx, item in enumerate(items, 1):
                    title = item.get_text(strip=True)
                    # 如果话题没匹配，再检查具体新闻标题
                    if not keywords or topic_match:
                        filtered_items.append(title)
                    else:
                        for kw in keywords:
                            if kw.lower() in title.lower():
                                filtered_items.append(title)
                                break
                
                if filtered_items:
                    output_lines.append(f"【话题：{topic}】")
                    for idx, title in enumerate(filtered_items, 1):
                        output_lines.append(f"{idx}. {title}")
                    output_lines.append("") # 空行分隔
                
            # 2. 提取 RSS (可选)
            rss_section = soup.find("div", class_="rss-section")
            if rss_section:
                rss_items = rss_section.find_all("div", class_="rss-title")
                filtered_rss = []
                for item in rss_items:
                    title = item.get_text(strip=True)
                    if not keywords:
                        filtered_rss.append(title)
                    else:
                        for kw in keywords:
                            if kw.lower() in title.lower():
                                filtered_rss.append(title)
                                break
                
                if filtered_rss:
                    output_lines.append("【RSS 订阅更新】")
                    for idx, title in enumerate(filtered_rss, 1):
                        output_lines.append(f"{idx}. {title}")
            
            return "\n".join(output_lines)
        except Exception as e:
            logger.error(f"HTML 解析失败: {e}")
            return ""

    @staticmethod
    @tool_registry.register(
        name="get_news_summary",
        description="获取今天或指定日期的新闻热点总结、世界局势。可以指定关键词来筛选特定国家或领域的新闻。",
        parameters={
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "日期，格式为 YYYY-MM-DD。如果是'今天'，请获取当前日期。",
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "可选。用于筛选新闻的关键词列表（如 ['美国', '科技', 'AI']）。如果不提供，则获取全天摘要。",
                }
            },
            "required": ["date_str"]
        }
    )
    async def generate_summary(date_str: str, keywords: list[str] = None) -> str:
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
            if "/" in date_str:
                date_str = date_str.replace("/", "-")
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            logger.warning(f"日期格式错误: {date_str}，回退到今天")
            return f"日期格式不对哦 ({date_str})，Miku 需要 YYYY-MM-DD 的格式呢。"

        html_path = NEWS_ROOT / date_str / "html" / "当日汇总.html"
        db_path = NEWS_ROOT / "news" / f"{date_str}.db"
        
        logger.info(f"[NewsService] 正在尝试访问 HTML: {html_path.absolute()} (关键词: {keywords})")
        logger.info(f"[NewsService] 正在尝试访问 DB: {db_path.absolute()}")
        
        if not html_path.exists():
            logger.error(f"[NewsService] HTML 文件不存在: {html_path.absolute()}")
            return f"找不到 {date_str} 的数据文件，请检查文件是否存在呢。"
            
        raw_data = NewsService.extract_news_data(html_path, keywords=keywords)
        if not raw_data:
            if keywords:
                return f"在 {date_str} 的新闻里，没有找到关于 {'、'.join(keywords)} 的内容呢。"
            return "数据解析失败，HTML 可能损坏了..."

        # 获取数据库统计信息作为补充上下文
        db_stats_text = ""
        if db_path.exists():
            try:
                db = NewsDatabase(db_path)
                # 1. 获取最持久话题
                long_topics = db.get_longest_running_topics(3)
                if long_topics:
                    db_stats_text += "\n【客观数据补充】\n今日最持久话题：\n"
                    for t in long_topics:
                        db_stats_text += f"- 《{t['title']}》 ({t['platform']})\n"
            except Exception as e:
                logger.error(f"读取 DB 统计失败: {e}")
            
        context_desc = f"关于 {'、'.join(keywords)} 的" if keywords else "今日"
        
        prompts_config = config_manager.get_config("prompts")
        system_prompt_template = prompts_config.get("news_summary_template")
        
        if system_prompt_template:
            try:
                system_prompt = system_prompt_template.format(context_desc=context_desc)
            except KeyError as e:
                logger.error(f"Failed to format news summary template: {e}")
                system_prompt = (
                    f"你是 Miku，大家最可爱的虚拟偶像！现在要请你帮大家整理一下{context_desc}热点新闻。\n"
                    "要求：\n"
                    "1. **纯文本口语模式**：严禁使用任何 Markdown 格式（如 `**` 加粗、标题）。严禁使用列表（1. 2. 3. 或 -）。\n"
                    "2. **自然衔接**：请用流畅的语言把新闻串联起来，使用“首先”、“其次”、“还有哦”等连接词，形成自然的段落。\n"
                    "3. **减少换行**：不要频繁换行，一段话内包含多个相关的句子。\n"
                    "4. **划重点**：挑选 3-5 个真正值得关注的大事，用你自己的语气概括一下（不要复读标题）。\n"
                    "5. **Miku 的感悟**：最后分享一下你对这些事情的小看法，要元气满满哦 ♪\n"
                    "6. **保持简洁**：不要太长，控制在 400 字以内，多用 Emoji 和颜文字。"
                )
        else:
            system_prompt = (
                f"你是 Miku，大家最可爱的虚拟偶像！现在要请你帮大家整理一下{context_desc}热点新闻。\n"
                "要求：\n"
                "1. **纯文本口语模式**：严禁使用任何 Markdown 格式（如 `**` 加粗、标题）。严禁使用列表（1. 2. 3. 或 -）。\n"
                "2. **自然衔接**：请用流畅的语言把新闻串联起来，使用“首先”、“其次”、“还有哦”等连接词，形成自然的段落。\n"
                "3. **减少换行**：不要频繁换行，一段话内包含多个相关的句子。\n"
                "4. **划重点**：挑选 3-5 个真正值得关注的大事，用你自己的语气概括一下（不要复读标题）。\n"
                "5. **Miku 的感悟**：最后分享一下你对这些事情的小看法，要元气满满哦 ♪\n"
                "6. **保持简洁**：不要太长，控制在 400 字以内，多用 Emoji 和颜文字。"
            )
        
        user_content = f"新闻数据:\n{raw_data}\n{db_stats_text}"

        try:
            # 修改：AIService.chat_completion 默认返回的是 response 对象，如果是流式则需要处理。
            # 这里为了简单起见，可以传入 stream=False 或者处理返回的 response。
            # 根据 AIService 的实现，如果不传 stream，则使用 GLOBAL_AI_CONFIG.stream。
            response = await AIService.chat_completion([
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ], stream=False)
            
            return response.choices[0].message.content
            
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
