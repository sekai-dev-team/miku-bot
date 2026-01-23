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


cmd_switch_model = on_command("switch_model", aliases={"切换模型", "load_model"}, permission=SUPERUSER, priority=5, block=True)

@cmd_switch_model.handle()
async def _(matcher: Matcher, args: Message = CommandArg()):
    """
    切换模型
    用法: 
    1. /switch_model <model_name> (自动匹配同名文件)
    2. /switch_model -g <gpt_path> -s <sovits_path> (指定路径)
    """
    args_str = args.extract_plain_text().strip()
    if not args_str:
        await matcher.finish("用法: /switch_model <model_name> 或 /switch_model -g <gpt_path> -s <sovits_path>")
    
    # 简单的参数解析
    import shlex
    
    try:
        # split args
        arg_list = shlex.split(args_str)
        
        gpt_path = None
        sovits_path = None
        model_name = None

        if "-g" in arg_list and "-s" in arg_list:
            try:
                g_index = arg_list.index("-g")
                gpt_path = arg_list[g_index + 1]
                s_index = arg_list.index("-s")
                sovits_path = arg_list[s_index + 1]
            except IndexError:
                await matcher.finish("参数解析错误：-g 和 -s 后必须紧跟路径")
        else:
             # Treat the whole first argument as model name if no flags found
             if len(arg_list) > 0:
                 model_name = arg_list[0]
        
        if model_name:
            msg = await VoiceService.set_model(model_name=model_name)
            await matcher.finish(f"模型切换成功: {msg}")
        elif gpt_path and sovits_path:
            msg = await VoiceService.set_model(gpt_path=gpt_path, sovits_path=sovits_path)
            await matcher.finish(f"模型切换成功: {msg}")
        else:
            await matcher.finish("参数不足。请提供模型名称或同时提供 GPT 和 SoVITS 路径。")
             
    except Exception as e:
        await matcher.finish(f"操作失败: {e}")
