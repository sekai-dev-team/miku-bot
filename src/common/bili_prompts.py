# prompts.py
# 存储 Bilibili 笔记生成的提示词模板
# 注意：现在主要通过 src/common/config_manager.py (plugin_configs.yaml) 进行管理
# 这里的 PROMPTS 仅作为代码层面的 fallback 或定义一些不可变的别名结构

PROMPTS = {}

# 别名映射，方便用户输入
PROMPT_ALIASES = {
    "default": "默认",
    "summary": "默认",
    "story": "剧情",
    "game": "剧情",
    "movie": "剧情",
    "music": "音乐",
    "song": "音乐",
    "funny": "搞笑",
    "meme": "搞笑",
}
