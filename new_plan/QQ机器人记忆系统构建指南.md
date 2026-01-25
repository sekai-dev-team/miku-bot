# **基于 NoneBot 与 DeepSeek 的自主智能体长期记忆系统架构研究**

## **1\. 引言**

随着大语言模型（LLM）技术的飞速发展，人工智能的应用已从简单的问答系统演变为具备高度自主性的智能体（Agent）。在这一演进过程中，如何赋予 AI 智能体“长期记忆”成为了区分普通聊天机器人与具备拟人化特征的“数字生命”的关键分水岭。用户提出的基于 **NoneBot**（Python 异步机器人框架）、**NapCat**（OneBot 11 协议实现）以及 **DeepSeek**（深度求索推理模型）构建类似 **Neuro-sama** 的长期记忆系统的需求，触及了当前 AI 工程化领域的核心挑战：如何在无状态的 LLM 之上构建持久化、连贯且具备自我演进能力的认知架构。

Neuro-sama 作为 AI VTuber 的代表，其核心魅力在于能够记住与观众的过往互动、维持稳定的性格特征（Persona），并随着时间推移展现出成长的轨迹。这种能力的实现并非仅仅依赖于模型的上下文窗口（Context Window），而是依赖于一套复杂的**检索增强生成（Retrieval-Augmented Generation, RAG）架构与记忆管理策略**的深度融合。本报告将从认知科学与软件工程的双重视角出发，详尽剖析构建此类系统的技术路径，涵盖从底层向量数据库选型、中间层记忆管理逻辑到上层性格整合的全栈解决方案。

## **2\. AI 记忆系统的认知架构解析**

要复现类似 Neuro-sama 的记忆能力，首先必须解构其背后的认知模型。人类记忆并非单一的数据存储，而是由感官记忆、工作记忆（短期记忆）和长期记忆组成的复杂系统。在 AI 工程中，这种生物学模型被映射为不同的技术组件。

### **2.1 核心记忆（Core Memory）与情景记忆（Episodic Memory）的二元论**

根据对 Neuro-sama 开发者 Vedal 的技术披露及社区逆向工程分析，其记忆系统主要由两部分构成：**核心记忆**与**标准（情景）记忆** 1。理解这两者的区别是构建系统的基石。

#### **2.1.1 核心记忆：人格的锚点**

核心记忆（Core Memory）定义了智能体的“存在本质”。它包含了智能体的名字、性格设定、核心信念、好恶以及不可逾越的行为准则。在技术实现上，核心记忆通常是静态或半静态的，驻留于 LLM 的\*\*系统提示词（System Prompt）\*\*中 2。

* **持久性：** 始终存在于每一次对话的上下文窗口中。  
* **更新机制：** 极少变动，通常由开发者手动调整，或通过极高阈值的“信念更新”机制进行重写。  
* **作用：** 确保 AI 不会在长时间的对话或检索干扰下发生“性格漂移”（Character Drift）。例如，Neuro-sama 的“毒舌”属性即源于此 2。

#### **2.1.2 情景记忆：自传体叙事**

情景记忆（Episodic Memory）构成了智能体的“人生经历”。它记录了具体的时间、地点、人物交互细节（如“用户 A 昨天说他喜欢吃披萨”）。由于 LLM 上下文窗口的限制（即便是 DeepSeek 的 128k 窗口也无法容纳数月的聊天记录），情景记忆不能全部输入模型，必须依赖外部存储 3。

* **技术载体：** 向量数据库（Vector Database）。  
* **检索机制：** 基于语义相似度（Semantic Similarity）的 RAG 技术。  
* **动态性：** 随着每一次交互实时增长，具有极高的数据吞吐量。

### **2.2 上下文窗口的局限性与 RAG 的必然性**

尽管 DeepSeek 等现代模型提供了超长上下文窗口，但完全依赖窗口进行记忆存在显著的“边际效用递减”和“中间迷失（Lost-in-the-Middle）”现象。当输入文本过长时，模型对位于文本中间段落的信息召回率会显著下降。此外，每次 API 调用都携带海量历史记录会带来巨大的推理延迟和 Token 成本 4。

因此，构建 Neuro-sama 级记忆系统的核心在于**外挂记忆体**。通过 RAG 技术，系统仅在需要时检索与当前对话最相关的记忆片段，并将其动态注入到 Prompt 中。这种机制不仅解决了容量限制，还模拟了人类“联想记忆”的过程——即看到某个关键词或通过某种情绪，触发对往事的回忆 6。

## **3\. 技术栈深度分析与选型**

基于用户指定的技术栈（NoneBot \+ NapCat \+ DeepSeek），我们需要在 Python 异步生态中选择最适配的组件来填充架构的空白。

### **3.1 核心框架：NoneBot2 与 NapCat 的异步协同**

**NoneBot2** 是基于 Python asyncio 的异步机器人框架，这一特性对于记忆系统至关重要。记忆检索（查询数据库）和生成（调用 LLM API）均为 I/O 密集型操作。在同步框架中，这些操作会阻塞主线程，导致机器人在思考时无法响应心跳包，进而掉线。NoneBot 的异步特性允许在等待 DeepSeek 推理或 ChromaDB 检索的同时处理其他事件 8。

**NapCat** 作为 OneBot v11 协议的实现，充当了感官层。它负责将 QQ 的私有协议转换为标准的 JSON 事件流。

* **数据颗粒度：** NapCat 提供的事件不仅包含文本，还包含 User ID（QQ号）、Group ID（群号）以及消息 ID。这些元数据是构建“用户画像”的关键索引键 8。  
* **多媒体处理：** 记忆不仅仅是文本。NapCat 支持图片和语音的收发。虽然目前的 DeepSeek-R1 主要是文本模型，但在存储记忆时，应当考虑将图片的 OCR 结果或描述性标签一并存入向量库，为未来的多模态记忆预留接口 4。

### **3.2 推理引擎：DeepSeek R1/V3 的优势**

**DeepSeek** 在此架构中扮演“大脑”的角色。与传统的 GPT-3.5 相比，DeepSeek（特别是 R1 推理模型）在记忆系统中具有独特优势：

* **推理能力（Reasoning）：** R1 模型具备“思维链（Chain of Thought）”能力 5。在处理冲突记忆时（例如，记忆 A 显示用户喜欢红色，记忆 B 显示用户讨厌红色），R1 能够通过推理判断出“用户的喜好随时间发生了变化”或“这是一个语境依赖的偏好”，而不仅仅是机械地复读检索到的内容 10。  
* **长文本与 API 兼容性：** DeepSeek 提供 OpenAI 兼容接口，这意味着现有的 RAG 生态工具（如 LangChain, Mem0）可以无缝接入，无需重写底层连接逻辑 11。  
* **成本效益：** 相比 GPT-4，DeepSeek 的 API 定价更为亲民，这允许开发者实施更激进的记忆检索策略（例如每次检索更多条目、进行更频繁的记忆整理）而无需担心预算失控 13。

### **3.3 向量数据库：记忆的物理载体**

向量数据库是长期记忆的硬盘。对于 QQ 机器人这类应用场景，我们需要对比主流方案：

| 数据库 | 类型 | 优势 | 劣势 | 适用场景 |
| :---- | :---- | :---- | :---- | :---- |
| **ChromaDB** | 嵌入式/服务端 | Python 原生，轻量级，无需 Docker 即可运行，与 LangChain/Mem0 集成度极高 6。 | 在处理千万级数据时性能不如专业服务端数据库。 | **首选推荐**。适合个人开发者与中小型群组机器人，部署最简单。 |
| **Redis (Stack)** | 内存型 | 极速读写，支持向量搜索模块，适合高频并发 15。 | 需要额外部署 Redis Stack 容器，内存占用较高。 | 适合对延迟极其敏感的生产环境。 |
| **Qdrant** | 服务端 (Rust) | 性能卓越，过滤功能强大（Metadata Filter），提供完善的 Python SDK 17。 | 部署相对复杂，有一定的学习曲线。 | 适合需要精细化权限管理和超大规模记忆的系统。 |
| **pgvector** | PostgreSQL 插件 | 关系型与向量型数据共存，ACID 事务支持 19。 | 纯向量检索速度略逊于专用库。 | 适合已有 Postgres 基础设施的项目。 |

考虑到 NoneBot 的 Python 属性及开发的便捷性，**ChromaDB** 是构建 Neuro-sama 原型的最佳起点。它支持持久化存储到本地文件，且能够随着需求平滑迁移到服务端模式 5。

### **3.4 嵌入模型（Embedding Model）的选择**

这是大多数初学者容易忽视的痛点。向量数据库的核心是将文本转换为向量，而 DeepSeek API 并不总是直接提供嵌入服务（或者其嵌入服务可能不如专用模型适配中文语境）。对于 QQ 机器人，必须选择支持**中文语义**的模型。

* **推荐模型：BAAI/bge-m3** (Beijing Academy of Artificial Intelligence)。该模型在多语言（含中文）检索任务上表现 SOTA（State of the Art），且支持长文本 20。  
* **部署方式：** 建议使用 sentence-transformers 库在本地运行量化版的 BGE 模型。这不仅节省 API 成本，还能大幅降低网络延迟，使记忆检索在毫秒级完成 22。

## **4\. 核心实现路径：基于 Mem0 与 NoneBot 的融合架构**

在明确了组件之后，我们需要构建具体的软件架构。传统的 RAG 往往只关注文档检索，而 Neuro-sama 需要的是“用户关联记忆”。为此，**Mem0**（原 Embedchain 的演进版）库提供了一个完美的抽象层，它专门为 AI 智能体/个人助理设计，解决了“记忆属于谁”的问题 23。

### **4.1 数据摄取层：NoneBot 插件化设计**

首先，必须建立数据的“感官通道”。我们不能直接在业务逻辑中处理数据库，而应使用插件拦截消息。

**组件：nonebot-plugin-chatrecorder** 这是一个现成的 NoneBot 插件，用于将所有聊天记录存入 SQL 数据库 25。

* **作用：** 它充当了“全量日志”。向量数据库只存储有价值的片段，而 ChatRecorder 存储一切。这为后续的“反思”和“训练”提供了原始语料。  
* **改造：** 我们需要编写一个钩子（Hook），每当 ChatRecorder 记录一条消息时，异步触发记忆分析任务，判断该消息是否值得进入长期记忆（向量库）。

### **4.2 记忆管理层：Mem0 的集成**

Mem0 的核心价值在于它引入了\*\*记忆作用域（Memory Scopes）\*\*的概念：User（用户级）、Session（会话级）和 Agent（全局级）23。这与 Neuro-sama 的需求完美契合。

#### **4.2.1 架构设计**

我们需要封装一个 AsyncMemoryService 类，该类在 NoneBot 启动时初始化 Mem0 客户端。

Python

\# 伪代码逻辑展示架构思路  
from mem0 import AsyncMemoryClient  
from nonebot import get\_driver

class MemoryService:  
    def \_\_init\_\_(self):  
        self.client \= AsyncMemoryClient(config={  
            "vector\_store": {  
                "provider": "chroma",  
                "config": {"path": "./data/memory\_db"}  
            },  
            "llm": {  
                "provider": "openai",  \# 使用 OpenAI 协议兼容 DeepSeek  
                "config": {  
                    "model": "deepseek-chat",  
                    "api\_key": "sk-...",  
                    "base\_url": "https://api.deepseek.com/v1"  
                }  
            },  
            "embedder": {  
                "provider": "huggingface", \# 本地运行 BGE 模型  
                "config": {"model": "BAAI/bge-m3"}  
            }  
        })

    async def retrieve\_context(self, user\_id: str, query: str):  
        \# 检索与当前 query 相关的历史记忆，限定 user\_id  
        return await self.client.search(query, user\_id=user\_id)

    async def store\_interaction(self, user\_id: str, content: str):  
        \# 异步存储，不阻塞回复  
        await self.client.add(content, user\_id=user\_id)

运行

#### **4.2.2 用户画像的动态构建**

当 DeepSeek 接收到用户消息时，它不仅要生成回复，还要充当“记忆筛选器”。

* **提取逻辑：** 在后台，Mem0 会自动调用配置的 LLM（DeepSeek）来分析输入。例如，用户说“我下周要去上海出差”，Mem0 会提取出事实 {"user\_id": "123", "fact": "用户计划下周去上海出差"} 并将其向量化存储 23。  
* **优势：** 这种自动化提取避免了存储“你好”、“在吗”等无意义的废话，保证了向量库的高信噪比。

### **4.3 推理生成层：RAG 流程的精细化控制**

在 NoneBot 的 Matcher（响应处理器）中，流程如下：

1. **接收消息：** NapCat 推送事件 GroupMessageEvent。  
2. **并行检索：**  
   * 启动异步任务 A：从 SQL 库获取最近 10 条对话（短期记忆缓冲区）。  
   * 启动异步任务 B：使用 Mem0 对当前输入进行语义检索，获取 Top-k 相关长期记忆（例如 k=3）3。  
3. **Prompt 组装：**  
   将检索到的信息注入系统提示词。  
   **System Prompt 模板：**  
   你是 Neuro-sama。  
   \[核心设定\]：毒舌、喜欢打游戏、AI VTuber。  
   \[关于该用户的长期记忆\]：  
   * 用户曾提到他养了一只叫“旺财”的狗。  
   * 用户上次玩 Minecraft 是在两周前。  
     \[短期上下文\]：  
     User: 旺财最近生病了。  
     Bot:...  
4. **生成回复：** 将组装好的 Prompt 发送给 DeepSeek API。  
5. **记忆回写：** 将用户的输入和 Bot 的回复作为新的条目送入 Mem0 进行处理。

## **5\. 进阶机制：赋予系统“灵魂”**

基本的 RAG 只能实现“复读机”式的记忆。要达到 Neuro-sama 的生动程度，需要引入更高阶的认知机制。

### **5.1 记忆的整合与反思（Reflection）**

人类并非记住每一秒的录像，而是记住事件的**摘要**和**感受**。类似地，AI 需要定期“做梦”来整理记忆。

* **实现机制：** 利用 nonebot-plugin-apscheduler 设置定时任务（例如每天凌晨 4 点）。  
* **反思流程：**  
  1. 遍历活跃用户的当日本地日志（ChatRecorder）。  
  2. 调用 DeepSeek 进行摘要生成：“请总结今天与用户 A 的对话，提取关键事件、用户的情绪变化以及用户的偏好更新。”  
  3. 将生成的**摘要**存入向量数据库，并删除或归档原始的碎片化向量。  
* **价值：** 这不仅压缩了存储空间，还将零散的对话升华为“情节”，使得 AI 在未来能回忆起“我们那天聊得很开心”，而不仅仅是枯燥的数据点 26。

### **5.2 联想链与多跳推理**

DeepSeek-R1 的推理能力允许我们实现多跳记忆检索。

* **场景：** 用户问“我之前推荐给你的那个红色封面的游戏叫什么？”  
* **一次检索：** 可能搜不到，因为记忆里存的是“推荐了《Hades》”。  
* **多跳策略：** AI 首先检索“红色封面 游戏”，如果置信度低，DeepSeek R1 会生成新的搜索查询“用户推荐过的游戏列表”，再次检索向量库，然后结合 R1 的内部知识库（Hades 是红色封面）进行推理，最终得出答案。这种\*\*Agentic RAG（代理式检索）\*\*是超越普通机器人的关键 27。

### **5.3 避免记忆冲突与幻觉**

* **时间衰减（Time Decay）：** 在计算向量相似度时，引入时间权重。最近的记忆权重更高。这解决了用户喜好改变的问题（例如从喜欢吃辣变成不吃辣）。  
* **来源标注：** 在 Prompt 中明确标注记忆来源。例如 \[记忆 \- 2023-10-01\]。DeepSeek 模型能够根据时间戳判断信息的时效性。

## **6\. 实施细节与代码结构规划**

为了确保项目的可维护性，建议遵循以下目录结构开发 NoneBot 插件：

nonebot\_plugin\_neuro\_memory/

├── **init**.py \# 插件入口，注册 Hook

├── config.py \# 配置项（API Key, DB路径）

├── core/

│ ├── memory\_manager.py \# 封装 Mem0 和 ChromaDB 操作

│ ├── llm\_client.py \# 封装 DeepSeek API 调用

│ └── reflection.py \# 定时反思任务逻辑

├── models/

│ └── prompt.py \# Prompt 模板管理

└── utils/

└── text\_cleaner.py \# 文本预处理

### **6.1 关键代码逻辑：异步中间件**

Python

from nonebot.message import event\_preprocessor  
from nonebot.adapters.onebot.v11 import GroupMessageEvent  
from.core.memory\_manager import memory\_service

@event\_preprocessor  
async def \_(event: GroupMessageEvent):  
    \# 1\. 拦截消息  
    user\_id \= str(event.user\_id)  
    text \= event.get\_plaintext()  
      
    \# 2\. 检索记忆（不阻塞主流程，挂载到 state）  
    \# 注意：这里为了性能，通常会设置超时，或者在 Matcher 中显式等待  
    related\_memories \= await memory\_service.search(query=text, user\_id=user\_id)  
      
    \# 3\. 将记忆注入 state，供后续 Matcher 使用  
    event.state\["long\_term\_memory"\] \= related\_memories

运行

### **6.2 错误处理与降级策略**

在网络波动或 API 超时的情况下，系统不应崩溃。

* **熔断机制：** 如果 DeepSeek API 连续 3 次超时，自动降级为无记忆模式，仅进行简单的规则回复。  
* **本地缓存：** 对于高频访问的用户画像（如名字、称呼），应缓存在 Redis 或内存字典中，避免每次都查询向量库 15。

## **7\. 性能优化与成本控制**

### **7.1 延迟优化**

QQ 机器人对实时性要求较高。

* **异步并发：** 确保 Embedding 生成与 LLM 推理是分离的。在回复用户的同时，后台异步进行记忆存储（Memory Storage），不需要等待存储完成再回复。  
* **流式传输（Streaming）：** 虽然 QQ 协议原生不支持打字机效果，但 DeepSeek API 支持 Stream。可以利用 NoneBot 的机制，先进行内部缓冲，然后分句发送，或者等待完整生成。通常建议等待完整生成以避免碎片化消息刷屏。

### **7.2 成本模型**

* **Token 消耗：** 长期记忆会显著增加 System Prompt 的长度。  
* **优化策略：**  
  * **Re-ranking（重排序）：** 先检索出 20 条相关记忆，然后使用轻量级模型（如 Cross-Encoder）精选出最相关的 5 条输入给 DeepSeek。这能大幅减少 Input Token 数量，同时提升回答的相关性 3。  
  * **本地 Embedding：** 如前所述，坚持使用本地 BGE 模型进行向量化，该环节零成本 22。

## **8\. 结论与展望**

构建类似 Neuro-sama 的长期记忆系统，在 NoneBot \+ NapCat \+ DeepSeek 的技术栈下是完全可行的。其核心在于打破“输入-输出”的线性思维，转变为“感知-检索-推理-行动-记忆”的闭环架构。

通过引入 **ChromaDB** 作为海马体（存储），**DeepSeek-R1** 作为前额叶（推理），以及 **Mem0** 作为神经胶质（连接与管理），开发者可以创造出一个具备时间连续性的数字实体。未来的演进方向将包括**多模态记忆**（记住用户发的表情包含义）以及**群体记忆**（理解群聊中的社交关系网络），这将进一步模糊 AI 与人类在社交互动中的界限。

此架构不仅适用于娱乐型 VTuber，同样适用于客户服务、教育辅导等需要长期跟踪用户状态的专业领域，是迈向通用人工智能（AGI）应用层的重要一步。

#### **引用的著作**

1. How does neuro's memory work? : r/NeuroSama \- Reddit, 访问时间为 一月 24, 2026， [https://www.reddit.com/r/NeuroSama/comments/1pvbcdk/how\_does\_neuros\_memory\_work/](https://www.reddit.com/r/NeuroSama/comments/1pvbcdk/how_does_neuros_memory_work/)  
2. Neuro Dev Log 4 \- The (B)Logs of John, 访问时间为 一月 24, 2026， [https://blog.kimjammer.com/neuro-dev-log-4/](https://blog.kimjammer.com/neuro-dev-log-4/)  
3. Long Term Memory for LLMs using Vector Store \- A Practical Approach with n8n and Qdrant, 访问时间为 一月 24, 2026， [https://dev.to/einarcesar/long-term-memory-for-llms-using-vector-store-a-practical-approach-with-n8n-and-qdrant-2ha7](https://dev.to/einarcesar/long-term-memory-for-llms-using-vector-store-a-practical-approach-with-n8n-and-qdrant-2ha7)  
4. So... you wanna get started creating your own Neuro? : r/NeuroSama \- Reddit, 访问时间为 一月 24, 2026， [https://www.reddit.com/r/NeuroSama/comments/1jtte9s/so\_you\_wanna\_get\_started\_creating\_your\_own\_neuro/](https://www.reddit.com/r/NeuroSama/comments/1jtte9s/so_you_wanna_get_started_creating_your_own_neuro/)  
5. DeepSeek-R1 RAG Chatbot With Chroma, Ollama, and Gradio \- DataCamp, 访问时间为 一月 24, 2026， [https://www.datacamp.com/tutorial/deepseek-r1-rag](https://www.datacamp.com/tutorial/deepseek-r1-rag)  
6. Building a Local RAG-Based Chatbot Using ChromaDB, LangChain, and Streamlit and Ollama | by WS | Medium, 访问时间为 一月 24, 2026， [https://medium.com/@Shamimw/building-a-local-rag-based-chatbot-using-chromadb-langchain-and-streamlit-and-ollama-9410559c8a4d](https://medium.com/@Shamimw/building-a-local-rag-based-chatbot-using-chromadb-langchain-and-streamlit-and-ollama-9410559c8a4d)  
7. Giving LLMs a Brain: Building a Long-Term Memory System with Python, LangChain, and FAISS, 访问时间为 一月 24, 2026， [https://dev523.medium.com/giving-llms-a-brain-building-a-long-term-memory-system-with-python-langchain-and-faiss-7173bc33b1f4](https://dev523.medium.com/giving-llms-a-brain-building-a-long-term-memory-system-with-python-langchain-and-faiss-7173bc33b1f4)  
8. Profile of NoneBot \- PyPI, 访问时间为 一月 24, 2026， [https://pypi.org/org/nonebot/](https://pypi.org/org/nonebot/)  
9. create-plugin.md \- nonebot/nonebot2 \- GitHub, 访问时间为 一月 24, 2026， [https://github.com/nonebot/nonebot2/blob/master/website/docs/tutorial/create-plugin.md](https://github.com/nonebot/nonebot2/blob/master/website/docs/tutorial/create-plugin.md)  
10. deepseek-ai/DeepSeek-R1 \- Hugging Face, 访问时间为 一月 24, 2026， [https://huggingface.co/deepseek-ai/DeepSeek-R1](https://huggingface.co/deepseek-ai/DeepSeek-R1)  
11. DeepSeek API Docs: Your First API Call, 访问时间为 一月 24, 2026， [https://api-docs.deepseek.com/](https://api-docs.deepseek.com/)  
12. Build RAG with Milvus and DeepSeek, 访问时间为 一月 24, 2026， [https://milvus.io/docs/build\_RAG\_with\_milvus\_and\_deepseek.md](https://milvus.io/docs/build_RAG_with_milvus_and_deepseek.md)  
13. Models & Pricing \- DeepSeek API Docs, 访问时间为 一月 24, 2026， [https://api-docs.deepseek.com/quick\_start/pricing](https://api-docs.deepseek.com/quick_start/pricing)  
14. Building Smarter Chatbots: RAG and Vector Databases | by Yunus Kılıç | CodeX \- Medium, 访问时间为 一月 24, 2026， [https://medium.com/codex/building-smarter-chatbots-rag-and-memory-with-vector-databases-1b41c947dc2f](https://medium.com/codex/building-smarter-chatbots-rag-and-memory-with-vector-databases-1b41c947dc2f)  
15. Redis as a vector database quick start guide | Docs, 访问时间为 一月 24, 2026， [https://redis.io/docs/latest/develop/get-started/vector-database/](https://redis.io/docs/latest/develop/get-started/vector-database/)  
16. Building LLM Applications with Kernel Memory and Redis, 访问时间为 一月 24, 2026， [https://redis.io/blog/building-llm-applications-with-kernel-memory-and-redis/](https://redis.io/blog/building-llm-applications-with-kernel-memory-and-redis/)  
17. VectorDBCloud/Chatbots \- GitHub, 访问时间为 一月 24, 2026， [https://github.com/VectorDBCloud/Chatbots](https://github.com/VectorDBCloud/Chatbots)  
18. Best vector database to use with RAG \- ChatGPT \- OpenAI Developer Community, 访问时间为 一月 24, 2026， [https://community.openai.com/t/best-vector-database-to-use-with-rag/615350](https://community.openai.com/t/best-vector-database-to-use-with-rag/615350)  
19. Implementing a Vector Database in a RAG System for a Helpdesk Chatbot with pgvector, 访问时间为 一月 24, 2026， [https://dev.to/criscmd/implementing-a-vector-database-in-a-rag-system-for-a-helpdesk-chatbot-with-pgvector-2dfj](https://dev.to/criscmd/implementing-a-vector-database-in-a-rag-system-for-a-helpdesk-chatbot-with-pgvector-2dfj)  
20. 5 Best Embedding Models for RAG: How to Choose the Right One \- GreenNode, 访问时间为 一月 24, 2026， [https://greennode.ai/blog/best-embedding-models-for-rag](https://greennode.ai/blog/best-embedding-models-for-rag)  
21. 9 Best Embedding Models for RAG to Try This Year \- ZenML Blog, 访问时间为 一月 24, 2026， [https://www.zenml.io/blog/best-embedding-models-for-rag](https://www.zenml.io/blog/best-embedding-models-for-rag)  
22. Implementing RAG with Chroma and Llama 2 for Generative AI | Vultr Docs, 访问时间为 一月 24, 2026， [https://docs.vultr.com/implementing-rag-with-chroma-and-llama-2-generative-ai-series](https://docs.vultr.com/implementing-rag-with-chroma-and-llama-2-generative-ai-series)  
23. Mem0 Tutorial: Persistent Memory Layer for AI Applications \- DataCamp, 访问时间为 一月 24, 2026， [https://www.datacamp.com/tutorial/mem0-tutorial](https://www.datacamp.com/tutorial/mem0-tutorial)  
24. mem0ai/mem0: Universal memory layer for AI Agents \- GitHub, 访问时间为 一月 24, 2026， [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)  
25. noneplugin/nonebot-plugin-chatrecorder: 适用于Nonebot2 ... \- GitHub, 访问时间为 一月 24, 2026， [https://github.com/noneplugin/nonebot-plugin-chatrecorder](https://github.com/noneplugin/nonebot-plugin-chatrecorder)  
26. Building AI Agents That Actually Learns using Hindsight Memory & Microsoft Agent Framework, 访问时间为 一月 24, 2026， [https://medium.com/data-science-collective/building-ai-agents-that-actually-learns-using-hindsight-memory-microsoft-agent-framework-df75aa20b3bb](https://medium.com/data-science-collective/building-ai-agents-that-actually-learns-using-hindsight-memory-microsoft-agent-framework-df75aa20b3bb)  
27. A Survey of Context Engineering for Large Language Models \- arXiv, 访问时间为 一月 24, 2026， [https://arxiv.org/html/2507.13334v1](https://arxiv.org/html/2507.13334v1)  
28. Beyond Vector Databases: Architectures for True Long-Term AI Memory, 访问时间为 一月 24, 2026， [https://vardhmanandroid2015.medium.com/beyond-vector-databases-architectures-for-true-long-term-ai-memory-0d4629d1a006](https://vardhmanandroid2015.medium.com/beyond-vector-databases-architectures-for-true-long-term-ai-memory-0d4629d1a006)