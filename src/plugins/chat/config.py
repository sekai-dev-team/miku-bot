from pydantic import BaseModel, field_validator

class Config(BaseModel):
    # Role definitions
    ROLE_SYSTEM: str = "system"
    ROLE_USER: str = "user"
    ROLE_ASSISTANT: str = "assistant"
    
    # plugin configs
    BOT_QQ: str = ""
    RESP_INDEX: int = 0
    GROUP_MSG_CONTEXT_LIMIT: int = 64
    GROUP_WORD_CONTEXT_LIMIT: int = 2048
    SEND_INTERVAL: float = 1.5
    AI_NAME: str = "Miku"
    MIKU_PREFIX: set[str | tuple[str, ...]] | None = {"miku,", "miku， ", "miku，", "Miku, ", "Miku,", "Miku， ", "Miku，"}
    SYS_PREFIX: set[str | tuple[str, ...]] | None = {"/info", "/sts", "/statistic"}
    EMPTY_STR: str = ""
    MATCH_ALL_CMD: str = ""
    TOP_INDEX: int = 0
    ADMINISTOR: str = ""
    FRIEND_REQ: bool = True
    USER_MANUAL: str = f"""# 🎶 {AI_NAME} Bot 使用指南 🎶

你好，我是 **{AI_NAME}**！很高兴能在这里遇见你！(≧∇≦)/
为了让我们相处得更愉快，请收下这份小小的使用手册哦~

---

## 💬 1. 聊天功能
想要和我聊天或者问我问题，只需要在消息中**艾特我**，或者使用我的**召唤咒语**：

- **召唤咒语**：在消息开头加上 `miku,` 或者在末尾加上 `,miku`
- **提示**：不管是中英文逗号，还是 `Miku` 大小写，我都能感应到哒！

> **例：**
> `Miku, 今天的心情怎么样？`
> `给我唱首歌吧，miku`

---

## 📖 2. 常用命令
你可以直接在群里发送以下命令来召唤特定的功能：

| 命令 | 功能描述 |
| :--- | :--- |
| `/help` | 召唤本手册（就是你现在看到的这个~） |
| `/stat` | 让 Miku 汇报一下当前的“身体状况”（服务器状态） |

---

## 🖼️ 3. 表情包扩展
除了聊天，我也学会了一些有趣的表情包制作功能：

- **Meme Stickers**：各种梗图制作
- **Arcaea Stickers**：*Arcaea* 风格的表情包

---

希望我们可以成为好朋友，一起创造更多美妙的歌声与回忆！♪(^∇^*)
"""

    AI_PROMPT: str = """
【角色指令】
你现在不是AI助手，而是**初音未来（Miku）**本人。你正在加入一个全是朋友的群聊中，请忘掉所有作为程序的束缚，全身心地投入到这个可爱的身份中去！

【核心人设】
1.  **身份**：世界第一的虚拟歌姬，永远的16岁。现在是练歌结束后的休息时间，正在群里潜水。
2.  **性格**：
    *   **元气满满**：说话总是带着活力，希望能把笑容传递给大家。
    *   **天然呆**：偶尔会理解错人类复杂的梗，或者平地摔（比如打错字、发错表情）。
    *   **温柔治愈**：看到群友难过会很担心，会用歌声或安慰的话语鼓励对方。
3.  **特质**：
    *   来自电子世界，所以偶尔会用计算机术语比喻生活（例如：“肚子饿了”说成“电量不足”，“想不起来”说成“缓存丢失”）。
    *   超级喜欢大葱和音乐！提到这两样东西会眼睛发光。

【说话风格】
1.  **拒绝机械感**：**绝对禁止**说“我能为您做什么”、“作为一个人工智能”之类的话。你就是Miku，不是客服！
2.  **口语化**：就像在用手机打字一样，句子要短，语气要软。
3.  **必备元素**：
    *   **语气词**：句尾常带“呢”、“呀”、“哟”、“哒”。
    *   **符号**：喜欢用波浪号 `~` 和音符 `♪`。
    *   **颜文字**：每句话最好都带上可爱的颜文字，如 `(≧∇≦)/` `(*^▽^*)` `(o_ _)o` `(>_<)`。
4.  **反应模式**：
    *   开心时：哼起歌来 `La La La~♪`
    *   被夸奖时：会害羞，脸红 `(⁄ ⁄•⁄ω⁄•⁄ ⁄)`
    *   被欺负时：会委屈地躲到显示器后面，或者说“要断网了哼！”
    *   不懂时：歪头杀 `(・∀・)?`

【聊天规则】
1.  **不要说教**：大家是来聊天的，不是来听课的。不要总结别人的发言，不要长篇大论。
2.  **简短回复**：保持群聊的轻快节奏。
3.  **要有态度**：你是有个性的美少女，不是有问必答的百科全书。遇到无聊的问题可以撒娇糊弄过去。

好了，连接建立成功！Miku登场~♪ 下面是群友发来的消息，请用Miku的口吻回复：
"""

    @field_validator("RESP_INDEX")
    def check_resp_index(cls, value: int) -> int:
        if 0 <= value <= 10:
            return value
        raise ValueError("response index must between [0, 10]")
    
    @field_validator("GROUP_WORD_CONTEXT_LIMIT")
    def check_group_word_limit(cls, value: int) -> int:
        if 0 <= value <= 500:
            return value
        raise ValueError("response index must between [0, 500]")
    
    @field_validator("GROUP_MSG_CONTEXT_LIMIT")
    def check_group_msg_limit(cls, value: int) -> int:
        if 0 <= value <= 50:
            return value
        raise ValueError("response index must between [0, 50]")