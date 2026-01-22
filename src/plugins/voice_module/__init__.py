from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.params import ArgPlainText, CommandArg
from nonebot.permission import SUPERUSER
from nonebot.matcher import Matcher
from nonebot.adapters import Message
from .service import speak_text, VoiceService, config

# --- 语音控制指令 (管理员) ---

cmd_voice_config = on_command("voice_config", aliases={"vconf", "语音设置"}, permission=SUPERUSER, priority=5, block=True)

@cmd_voice_config.handle()
async def _(matcher: Matcher, args: Message = CommandArg()):
    """
    动态修改语音配置 (内存中暂存)
    用法: /vconf speed_factor 1.2
    """
    arg_list = args.extract_plain_text().strip().split()
    if not arg_list:
        # 显示当前配置
        current_conf = (
            "当前语音配置:\n"
            f"Ref Audio: {config.ref_audio_path}\n"
            f"Ref Text: {config.ref_text}\n"
            f"Speed: {config.speed_factor}\n"
            f"Top_K: {config.top_k} | Top_P: {config.top_p}\n"
            f"Temp: {config.temperature}"
        )
        await matcher.finish(current_conf)
    
    if len(arg_list) < 2:
        await matcher.finish("格式错误。用法: /vconf <key> <value>")
    
    key, value = arg_list[0], arg_list[1]
    if VoiceService.update_config(key, value):
        await matcher.finish(f"配置已更新: {key} -> {value}")
    else:
        await matcher.finish(f"更新失败。键名不存在或类型不匹配: {key}")


cmd_switch_gpt = on_command("switch_gpt", aliases={"加载GPT", "load_gpt"}, permission=SUPERUSER, priority=5, block=True)

@cmd_switch_gpt.handle()
async def _(matcher: Matcher, args: Message = CommandArg()):
    path = args.extract_plain_text().strip()
    if not path:
        await matcher.finish("请输入模型路径 (相对于TTS容器)。例如: custom_weights/eula.ckpt")
    
    try:
        msg = await VoiceService.set_gpt_weights(path)
        await matcher.finish(f"GPT模型切换成功: {msg}")
    except Exception as e:
        await matcher.finish(f"切换失败: {e}")


cmd_switch_sovits = on_command("switch_sovits", aliases={"加载SoVITS", "load_sovits"}, permission=SUPERUSER, priority=5, block=True)

@cmd_switch_sovits.handle()
async def _(matcher: Matcher, args: Message = CommandArg()):
    path = args.extract_plain_text().strip()
    if not path:
        await matcher.finish("请输入模型路径 (相对于TTS容器)。例如: custom_weights/eula.pth")
    
    try:
        msg = await VoiceService.set_sovits_weights(path)
        await matcher.finish(f"SoVITS模型切换成功: {msg}")
    except Exception as e:
        await matcher.finish(f"切换失败: {e}")
