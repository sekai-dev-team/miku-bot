from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.matcher import Matcher
from nonebot.params import ArgPlainText
from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException

from src.common.config_manager import config_manager
from ..resources import resource_manager

# --- Manual Management ---
cmd_manual = on_command("mymanual", aliases={"manual", "guide"}, permission=SUPERUSER, priority=5, block=True)

@cmd_manual.handle()
async def _(matcher: Matcher):
    msg = (
        "Miku 使用手册管理\n"
        "------------------\n"
        "当前文件: manual.md\n"
        "1. 修改手册\n"
        "2. 查看当前手册\n"
        "0. 退出交互"
    )
    await matcher.send(msg)

@cmd_manual.got("action")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action")):
    if action == "0":
        await matcher.finish("操作已取消。")
    elif action == "2":
        content = resource_manager.get_manual_content()
        await matcher.finish(content)
    elif action == "1":
        await matcher.send("请输入新的手册内容 (输入 -1 退出)：")
    else:
        await matcher.reject("指令无法识别，请重新输入（0/1/2）：")

@cmd_manual.got("content")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action"), content: str = ArgPlainText("content")):
    if content.strip() == "-1":
        await matcher.finish("已退出修改")

    if action == "1":
        try:
            resource_manager.update_manual_content(content)
            await matcher.finish("使用手册更新成功！")
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"Failed to write manual: {e}")
            await matcher.finish(f"写入失败：{e}")


# --- AI Prompt Management ---
cmd_aiprompt = on_command("aiprompt", aliases={"prompt", "human_set"}, permission=SUPERUSER, priority=5, block=True)

@cmd_aiprompt.handle()
async def _(matcher: Matcher):
    msg = (
        "Miku 提示词管理\n"
        "-------------------\n"
        "当前配置: plugin_configs.yaml (prompts.chat_system)\n"
        "1. 修改提示词\n"
        "2. 查看当前提示词\n"
        "0. 退出交互"
    )
    await matcher.send(msg)

@cmd_aiprompt.got("action")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action")):
    if action == "0":
        await matcher.finish("操作已取消。")
    elif action == "2":
        prompts = config_manager.get_config("prompts")
        current_prompt = prompts.get("chat_system", "未找到配置")
        await matcher.finish(f"当前 Prompt:\n\n{current_prompt}")
    elif action == "1":
        await matcher.send("请输入新的提示词 (输入 -1 退出)：")
    else:
        await matcher.reject("指令无法识别，请重新输入（0/1/2）：")

@cmd_aiprompt.got("content")
async def _(matcher: Matcher, event: MessageEvent, action: str = ArgPlainText("action"), content: str = ArgPlainText("content")):
    if content.strip() == "-1":
        await matcher.finish("已退出修改")

    if action == "1":
        try:
            prompts = config_manager.get_config("prompts")
            prompts["chat_system"] = content
            config_manager.save_config("prompts", prompts)
            await matcher.finish("AI 提示词更新成功！(已保存至 plugin_configs.yaml)")
        except FinishedException:
            raise
        except Exception as e:
            logger.error(f"Failed to update prompt: {e}")
            await matcher.finish(f"更新失败：{e}")


# --- Configuration Management ---
reload_cmd = on_command("reload_config", aliases={"刷新配置", "重载配置"}, permission=SUPERUSER, priority=1, block=True)

@reload_cmd.handle()
async def _(matcher: Matcher):
    try:
        config_manager.reload()
        # Trigger voice config reload if module is active
        try:
            from src.plugins.voice_module.config import config as voice_config
            voice_config.load_from_file()
        except ImportError:
            pass
            
        await matcher.finish("配置已刷新！(Plugin Configs reloaded from YAML)")
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        await matcher.finish(f"配置刷新失败：{e}")
