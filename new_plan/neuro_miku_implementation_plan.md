# Miku-Bot 记忆系统构建计划 (Project Neuro-Miku)

## 1. 概述
本计划旨在为 Miku-Bot 构建一个类似 Neuro-sama 的长期记忆系统，使其能够生成用户画像，并针对不同用户展现出连贯的个性化反应。

**核心技术栈**:
- **数据源**: `nonebot-plugin-chatrecorder` (全量聊天记录)
- **记忆管理**: `Mem0` (Memory Layer for AI Agents)
- **向量存储**: `ChromaDB` (本地/Docker部署)
- **大脑**: `DeepSeek` (via `src/common/ai_service.py`)

---

## 2. 实施阶段 (Phases)

### Phase 1: 基础设施铺设 (Infrastructure)
**目标**: 引入必要的依赖，确保持久化存储可用，配置基础环境。

1.  **依赖管理 (`pyproject.toml`)**:
    *   添加 `nonebot-plugin-chatrecorder` (及 `nonebot-plugin-orm[default]`) 用于全量日志。
    *   添加 `chromadb` (向量数据库客户端)。
    *   添加 `mem0ai` (记忆管理层封装)。
    *   添加 `pysqlite3-binary` (如果 Linux 环境下系统 sqlite 版本过低需要)。

2.  **环境配置 (`docker-compose.yml`)**:
    *   为 ChatRecorder 的数据库（通常是 SQLite 或 PostgreSQL）配置持久化卷。
    *   为 ChromaDB 配置持久化卷（如果使用 Docker 部署 Chroma 服务，或直接映射本地目录供嵌入式使用）。

3.  **插件配置 (`plugin_configs.yaml` / `.env`)**:
    *   启用 ChatRecorder 记录功能。
    *   配置 ORM 数据库连接字符串。

### Phase 2: 感官系统接入 (Sensory Input)
**目标**: 让 Miku 自动记录发生的每一句话（全量日志），作为记忆的原始素材。

1.  **插件集成**:
    *   在 `src/plugins/__init__.py` 或入口处加载 `nonebot_plugin_chatrecorder`。
    *   确保 `nonebot_plugin_orm` 正常初始化并运行迁移。

2.  **数据验证**:
    *   编写测试脚本 `src/tests/test_history.py`，验证是否能从数据库中读取刚刚发送的消息。

### Phase 3: 海马体构建 (The Hippocampus)
**目标**: 实现“短期记忆”到“长期记忆”的转化逻辑。

1.  **服务封装 (`src/common/memory_service.py`)**:
    *   创建一个 `MemoryService` 类。
    *   **提取 (Extract)**: 编写逻辑，当对话结束后或定期，调用 LLM 分析 ChatRecorder 中的最近对话，提取“事实” (Facts) 和“偏好” (Preferences)。
    *   **存储 (Store)**: 使用 `Mem0` 将提取的信息存入 ChromaDB，关联 `user_id` 和 `group_id`。
    *   **检索 (Retrieve)**: 提供 `get_related_memories(user_id, query)` 接口。

2.  **异步处理**:
    *   利用 `nonebot.get_driver().on_startup` 初始化记忆服务。
    *   利用后台任务（background task）处理记忆存储，避免阻塞对话响应。

### Phase 4: 认知整合 (Cognitive Integration)
**目标**: 在对话中自然地调用记忆，影响生成结果。

1.  **修改核心对话逻辑 (`src/plugins/chat/__init__.py`)**:
    *   在 `ai` matcher 处理流程中，在调用 LLM 之前：
        *   调用 `MemoryService.get_related_memories(user_id, user_input)`。
    *   **Prompt 注入**:
        *   将检索到的记忆片段格式化（例如 `[Memory Context]: ...`）。
        *   动态插入到 `messages` 列表的 System Prompt 之后，User Input 之前。

2.  **记忆更新**:
    *   在 AI 回复后，将 `(User, AI)` 的对话对推送到 `MemoryService` 的待处理队列，触发新的记忆提取。

---

## 3. 目录结构规划

```text
src/
├── common/
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── service.py      # MemoryService 主逻辑
│   │   ├── storage.py      # ChromaDB/Mem0 封装
│   │   └── prompt.py       # 记忆提取专用的 System Prompt
│   └── ...
└── plugins/
    └── chat/
        └── ... (调用 memory_service)
```

## 4. 注意事项
*   **Token 消耗**: 记忆提取和检索都会消耗 Token，需监控 DeepSeek API 使用量。
*   **隐私**: 确保存储的记忆仅用于辅助对话，且敏感信息需脱敏处理（视具体需求而定）。
*   **延迟**: 检索过程必须高效，避免让用户等待过久。建议设置检索超时时间。
