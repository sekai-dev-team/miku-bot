from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import MessageEvent, Bot, Message, MessageSegment
from nonebot.matcher import Matcher
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException
from nonebot_plugin_htmlrender import md_to_pic

from src.common.memory_service import memory_service
from ..sys_monitor import SystemMonitor
from ..msg_context import LISTENER
from ..config import plugin_config as PLUGIN_CONFIG
from ..help_menu import get_main_menu_text, get_plugin_help_text
from ..resources import resource_manager

# --- User Profile Management (Memory) ---
cmd_profile = on_command("profile", aliases={"记忆", "用户画像"}, priority=5, block=True)

@cmd_profile.handle()
async def _(matcher: Matcher, event: MessageEvent, args: Message = CommandArg()):
    sender_id = event.get_user_id()
    
    arg_text = args.extract_plain_text().strip()
    parts = arg_text.split(maxsplit=1)
    
    sub_cmd = parts[0].lower() if parts else "ls"
    payload = parts[1] if len(parts) > 1 else ""
    
    try:
        if sub_cmd in ["ls", "list", "show", "查看"]:
            memories = await memory_service.get_all(user_id=sender_id)
            
            # Fix: mem0 v1.1 returns {'results': [...]} 
            if isinstance(memories, dict) and "results" in memories:
                memories = memories["results"]
            
            if not memories:
                await matcher.finish("我好像还没记住关于你的什么特别的事情呢... 多和我聊聊天吧！")
            
            # Format list
            msg_lines = ["📋 你的个人档案 (Memory Profile):", "-------------------"]
            for mem in memories:
                # mem0 structure: {'id': '...', 'memory': '...', ...}
                if isinstance(mem, str):
                    m_id = "N/A"
                    m_text = mem
                elif isinstance(mem, dict):
                    m_id = mem.get("id", "N/A")
                    # Support both 'memory' (v1.0) and 'text' (v1.1) keys
                    m_text = mem.get("memory") or mem.get("text") or ""
                else:
                    m_id = "Unknown"
                    m_text = str(mem)

                msg_lines.append(f"🆔 {m_id}\n   {m_text}")
                
            await matcher.finish("\n".join(msg_lines))
            
        elif sub_cmd in ["add", "new", "新增"]:
            if not payload:
                await matcher.finish("要在你的档案里加什么呢？请使用 /profile add <内容>")
                
            await matcher.send("正在写入记忆...")
            # Add memory
            await memory_service.add(payload, user_id=sender_id, metadata={"source": "manual_add"})
            await matcher.finish("已添加到记忆库！")

        elif sub_cmd in ["rm", "del", "delete", "remove", "删除"]:
            if not payload:
                 await matcher.finish("请指定要删除的记忆 ID。你可以先用 /profile ls 查看。" )
            
            await matcher.send(f"正在删除记忆 [{payload}]...")
            await memory_service.delete(payload)
            await matcher.finish("删除完成。" )
            
        else:
            # Default help
            await matcher.finish(
                "🧠 Miku 记忆管理指令:\n"
                "-------------------\n"
                "/profile ls       - 查看你的所有记忆\n"
                "/profile add <内容> - 手动添加一条关于你的记忆\n"
                "/profile rm <ID>  - 删除指定 ID 的记忆"
            )
    except RuntimeError as e:
        await matcher.finish(f"记忆系统暂时不可用 (System Error): {e}")
    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"Error in profile command: {e}")
        await matcher.finish(f"发生未知错误: {e}")


# --- System Status ---
sys_stat = on_command("stat", aliases=PLUGIN_CONFIG.SYS_PREFIX, priority=2, permission=SUPERUSER)
@sys_stat.handle()
async def _(bot: Bot, event: MessageEvent):  # 支持私聊
    # 获取各项状态
    uptime = SystemMonitor.uptime()
    balance = await SystemMonitor.balance() # 记得 await 异步方法
    mem = SystemMonitor.memory()
    cpu = SystemMonitor.cpu()
    vram = SystemMonitor.vram()
    
    # 获取群组信息
    try:
        group_list = await bot.get_group_list()
        total_count = len(group_list)
    except Exception as e:
        logger.error(f"Failed to get group list: {e}")
        total_count = "Unknown"
        
    active_groups = list(LISTENER.group_queues.keys())
    group_stat = f"群总数量: {total_count}"
    if active_groups:
         group_stat += f"\n活跃上下文: {len(active_groups)}\n" + "\n".join(active_groups)
    
    # 拼接消息
    vram_section = f"{vram}\n" if vram else ""

    message = (
        f"Miku 状态报告\n"
        f"------------------\n"
        f"{uptime}\n"
        f"{cpu}\n"
        f"{mem}\n"
        f"{vram_section}"
        f"------------------\n"
        f"{balance}\n"
        f"------------------\n"
        f"{group_stat}"
    )
    await sys_stat.send(message)


# --- Help Manual ---
user_manual = on_command("help")
@user_manual.handle()
async def _(event: MessageEvent, bot: Bot, args: Message = CommandArg()):  # 支持私聊
    arg_text = args.extract_plain_text().strip()
    
    if not arg_text:
        # Show main menu
        await user_manual.finish(get_main_menu_text())
    else:
        # Show specific help
        detail = get_plugin_help_text(arg_text)
        if detail:
            # Check if user wants "all" or specific
            await user_manual.finish(detail)
        else:
             # Fallback: if arg is "all" or "manual", maybe show the full image?
             if arg_text.lower() in ["all", "full", "manual"]:
                try:
                    manual_content = resource_manager.get_manual_content()
                    if manual_content.startswith("Error"):
                         await user_manual.finish("说明书好像弄丢了... (文件读取失败)")
                    img = await md_to_pic(manual_content)
                    await user_manual.finish(MessageSegment.image(img))
                except FinishedException:
                    raise
                except Exception as e:
                    logger.error(f"Failed to render help manual: {e}")
                    await user_manual.finish("说明书渲染失败了...")

             await user_manual.finish(f"未找到关于 '{arg_text}' 的功能说明哦。\n请发送 `/help` 查看列表，或发送 `/help all` 查看完整长图。")
