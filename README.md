# Miku Bot 🎵

Miku Bot 是一个基于 [NoneBot2](https://github.com/nonebot/nonebot2) 的多功能群聊机器人，集成了 AI 对话、新闻聚合、视频笔记总结、群聊黑历史记录以及股市信息查询等功能。

本项目旨在打造一个具有“人格”的智能助理，通过 ReAct (Reasoning + Acting) 模式，让 Miku 能够理解自然语言指令并自主调用工具完成任务。

---

## 🧩 模块工作流程详解 (Module Workflows)

以下是项目中各个核心模块的工作原理与数据流向说明。

### 1. 核心对话系统 (Core Chat System)
负责处理所有的自然语言对话，是 Miku 的“大脑”。

*   **入口**: `src/plugins/chat`
*   **工作流**:
    1.  **消息接收**: `sentence_handler.py` 监听所有未被特定指令捕获的消息。
    2.  **上下文构建**: `msg_context.py` 维护用户的对话历史（短期记忆）。
    3.  **AI 决策 (ReAct)**:
        *   系统将用户消息 + 上下文 + 可用工具列表（`tool_registry.py`）发送给 AI (DeepSeek/OpenAI)。
        *   AI 判断是否需要调用工具（如“查新闻”、“查股价”）。
        *   **工具调用**: 如果需要，AI 返回工具调用请求，系统执行对应 Python 函数并获取结果。
        *   **最终响应**: AI 根据工具返回的结果，生成最终的自然语言回复。
    4.  **回复发送**: 通过 OneBot 协议将回复发送给用户。

#### 🔌 已注册 AI 工具 (Registered Tools)
目前系统已注册以下 Python 函数供 AI 在对话中自主调用：

| 插件模块 | 工具名称 (Function) | 描述 (Description) |
| :--- | :--- | :--- |
| **News** | `get_news_summary` | 获取指定日期的新闻汇总与 AI 摘要 |
| **News** | `search_news` | 搜索特定关键词的历史热搜记录 |
| **Stock** | `get_stock_info` | 查询特定股票代码的实时行情 |
| **Stock** | `get_market_overview` | 获取当日股市概览与涨幅榜 |
| **History** | `get_random_history` | 随机调取一条群聊黑历史记录 |

### 2. 新闻聚合模块 (News Plugin)
提供每日新闻汇总 PDF 及 AI 摘要功能。

*   **入口**: `src/plugins/news`
*   **数据流**:
    1.  **数据采集**: (外部爬虫/定时任务) 抓取新闻数据存入 `src/common/resources/news/*.db` 及 HTML 模板。
    2.  **指令触发**: 用户发送 `/news` 或询问 AI "今天有什么新闻"。
    3.  **PDF 生成**: `service.py` 调用 Playwright (Headless Browser) 渲染当日的 HTML 文件为 PDF。
    4.  **AI 摘要**:
        *   `service.py` 解析 HTML 提取新闻标题和正文。
        *   构建 Prompt 让 AI 进行总结、划重点并发表“感想”。
    5.  **交付**: PDF 文件上传至群聊，摘要以文本形式发送。

### 3. B站视频笔记 (Bili Note)
调用本地 Docker 容器分析 Bilibili 视频内容。

*   **入口**: `src/plugins/bili_note`
*   **工作流**:
    1.  **指令接收**: 用户发送 `/笔记 <BV号/链接>`。
    2.  **任务调度**:
        *   插件通过 `docker` SDK 连接本地 Docker 守护进程。
        *   在 `sekai-bilinote-local` 容器中执行 `python main.py <url>` 命令。
    3.  **内容处理**:
        *   容器内的服务下载视频音频/字幕。
        *   调用 ASR (语音转文字) 和 LLM 进行总结。
        *   结果生成为 Markdown 文件，写入共享 Volume (`src/common/resources/local_bilinote`).
    4.  **结果返回**: 插件检测到新文件生成后，将其转换为 PDF 或直接发送 Markdown 文件给用户。

### 4. 群聊黑历史 (History Book)
记录群友的“名言”并随机回顾。

*   **入口**: `src/plugins/history_book`
*   **工作流**:
    1.  **记录 (Write)**:
        *   监听用户回复消息并发送“入典”、“记仇”等关键词。
        *   `HistoryService` 将被引用消息的内容、发送者、时间戳存入 SQLite 数据库。
    2.  **回顾 (Read)**:
        *   用户发送“来点黑历史”或“戳一戳” Miku。
        *   从数据库中随机 `ORDER BY RANDOM()` 抽取一条该群的历史记录。
        *   格式化输出（包含当时的时间和发言人）。

### 5. 股市行情 (Stock Push)
提供基础的股票查询服务。

*   **入口**: `src/plugins/stock_push`
*   **工作流**:
    1.  **数据源**: 读取 `src/common/resources/stock_analysis.db` (由外部量化脚本每日更新)。
    2.  **服务层**: `service.py` 封装 SQL 查询（获取最新日期、个股行情、涨幅榜）。
    3.  **交互层**:
        *   **指令**: `/stock` 直接调用服务层返回格式化文本。
        *   **复盘/研报**:
            *   `/stock review`: 读取 `reports/market_review_*.md` 并直接发送文本。
            *   `/stock report`: 读取 `reports/report_*.md` 并以文件形式上传。
        *   **AI 工具**: 注册 `get_stock_info` 工具。当用户问“宁德时代股价”时，AI 自动调用此函数获取 JSON 数据，再转换成人话回答。

---

## 🛠️ 项目结构

```
A:\project\miku-bot\
├── docker/                 # Docker 部署相关配置
├── src/
│   ├── common/             # 公共模块
│   │   ├── ai_service.py   # 统一 AI 接口 (ReAct 核心)
│   │   ├── tool_registry.py# 工具注册中心
│   │   └── resources/      # 数据文件 (DB, HTML, Markdown)
│   └── plugins/
│       ├── chat/
│       ├── news/
│       ├── bili_note/      # B站笔记 (Docker集成)
│       ├── history_book/   # 黑历史记录
│       └── stock_push/     # 股市行情
├── .env                    # 配置文件
├── bot.py                  # 启动入口
└── pyproject.toml          # 依赖管理
```