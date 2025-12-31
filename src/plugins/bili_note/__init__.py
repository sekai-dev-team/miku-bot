from pathlib import Path
import asyncio
import docker
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message, MessageSegment
from nonebot.params import CommandArg, ArgPlainText
from nonebot.log import logger
from nonebot.typing import T_State

# Constants
CONTAINER_NAME = "sekai-bilinote-local"
SHARED_DIR = Path("/app/data/local_bilinote")

# Command definition
bili_note = on_command("笔记", aliases={"bili_note", "summary"}, priority=5, block=True)

@bili_note.handle()
async def handle_note(bot: Bot, event: Event, args: Message = CommandArg()):
    # Pre-check: Is Docker available?
    try:
        docker.from_env().ping()
    except Exception:
        await bili_note.finish("当前环境无法连接 Docker，笔记功能暂时不可用哦 (´；ω；｀)")

    url = args.extract_plain_text().strip()
    if not url:
        await bili_note.finish("请提供 Bilibili 视频链接哦！没有链接 Miku 无法工作呢 (´・ω・`)")

    # Notify user with @
    await bili_note.send("收到请求！正在呼叫笔记助手进行生成，这可能需要一点时间，请耐心等待 ♪", at_sender=True)

    # Record files before execution to identify the new one
    try:
        if not SHARED_DIR.exists():
             await bili_note.finish(f"错误！无法访问共享目录 {SHARED_DIR} 快检查一下 Volume 配置吧 >_<")
        existing_files = set(SHARED_DIR.glob("*.md"))
    except Exception as e:
        logger.error(f"Failed to list files in {SHARED_DIR}: {e}")
        await bili_note.finish(f"读取共享目录出错了，Miku 也很头疼：{e}")
        return

    # Define the docker execution task
    def run_docker_task(video_url: str):
        try:
            client = docker.from_env()
            container = client.containers.get(CONTAINER_NAME)
            # Exec command: python3 main.py "URL"
            # Return tuple (exit_code, output)
            return container.exec_run(f'python3 main.py "{video_url}" --model deepseek', stream=False)
        except docker.errors.NotFound:
            return None, f"找不到 {CONTAINER_NAME} 容器！它是不是还在偷懒没启动？"
        except Exception as e:
            return None, str(e)

    # Run in thread pool to avoid blocking asyncio loop
    try:
        # Use asyncio.to_thread for blocking I/O
        # Set timeout to 15 minutes (900 seconds)
        result = await asyncio.wait_for(
            asyncio.to_thread(run_docker_task, url),
            timeout=900
        )
        
        if result[0] is None:
             # logger.error(f"Docker task failed: {result[1]}") # Log the actual error
             await bili_note.finish(f"调用 Docker 失败了... 呜呜，请检查后台：{result[1]}")
        
        exit_code, output = result
        output_str = output.decode("utf-8") if isinstance(output, bytes) else str(output)

        if exit_code != 0:
            logger.error(f"Bilinote failed: {output_str}")
            # Truncate log for readability
            log_tail = output_str[-200:]
            await bili_note.finish(f"生成失败了！Miku 尽力了，但遇到了错误日志，只有你能修好它了：\n...\n{log_tail}") 
            
    except asyncio.TimeoutError:
        await bili_note.finish("超时啦！已经过了15分钟还没好，Miku 的处理器要过热了，任务强制终止 (T_T)")
    except Exception as e:
        # Avoid catching FinishedException (which inherits from BaseException/Exception depending on NoneBot version, but usually best to ignore if it's the finish signal)
        from nonebot.exception import FinishedException
        if isinstance(e, FinishedException):
            raise e
            
        logger.error(f"Exception during docker execution: {e}")
        await bili_note.finish(f"呜... 执行过程中发生了意料之外的错误：{e}")

    # Check for new files
    current_files = set(SHARED_DIR.glob("*.md"))
    new_files = current_files - existing_files

    if not new_files:
        await bili_note.finish("任务流程结束了，但是没找到新生成的笔记文件... 是不是被吃掉了？请检查后台日志。" )

    # Notify completion with @
    await bili_note.send("久等啦！笔记生成完毕，Miku 这就上传给您~ 🎵", at_sender=True)

    # Send the new file(s)
    for file_path in new_files:
        try:
            # Read file bytes to send directly (works across containers)
            file_content = file_path.read_bytes()
            await bili_note.send(
                MessageSegment.file(
                    file=file_content,
                    name=file_path.name
                )
            )
        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            await bili_note.send(f"哎呀，文件 {file_path.name} 发送失败了... 可能是网络波动？")

# --- Bilinote List Feature ---
bili_doc = on_command("笔记列表", aliases={"bilidoc", "doc_list"}, priority=5, block=True)

@bili_doc.handle()
async def list_files(bot: Bot, event: Event, state: T_State):
    if not SHARED_DIR.exists():
        await bili_doc.finish("呜... 找不到存放笔记的柜子 (目录不存在)，请联系管理员检查 Volume 配置吧！")
    
    # Sort by modification time, newest first
    files = sorted(SHARED_DIR.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    
    if not files:
        await bili_doc.finish("记忆回廊里空空如也... 目前还没有生成过任何笔记哦。(´・ω・`)")
    
    # Store files in state for the next step
    state["file_map"] = {str(i+1): f for i, f in enumerate(files)}
    
    # Build the menu
    msg = "正在翻阅记忆回廊... 找到了以下这些笔记哦！✨\n"
    for i, f in enumerate(files):
        # Limit to 10-15 files to avoid spamming? Let's show all for now or first 20.
        if i >= 20:
             msg += f"\n... 以及其他 {len(files) - 20} 篇\n"
             break
        msg += f"{i+1}. {f.name}\n"
    msg += "\n呐，告诉 Miku 您想复习哪一篇呢？\n（回复序号就好，回复“取消”可以结束哦）"
    
    await bili_doc.send(msg)

@bili_doc.got("choice")
async def handle_choice(bot: Bot, event: Event, state: T_State, choice: str = ArgPlainText("choice")):
    choice = choice.strip()
    
    if choice in ["取消", "算了", "cancel", "exit"]:
        await bili_doc.finish("好哒，那 Miku 先把笔记收起来啦，随时都可以再叫我哦 ♪")
        
    file_map = state.get("file_map", {})
    target_file = file_map.get(choice)
    
    if not target_file:
        # Reject invalid input
        await bili_doc.reject("哎呀，这个序号好像不对呢？请重新告诉 Miku 正确的序号，或者说“取消”结束。")

    # Send the file
    try:
        await bili_doc.send(f"了解！正在为您取出《{target_file.name}》... 给！这是您要的资料 📚")
        # Reuse the byte-reading logic
        file_content = target_file.read_bytes()
        await bili_doc.send(
            MessageSegment.file(
                file=file_content,
                name=target_file.name
            )
        )
    except Exception as e:
        logger.error(f"Failed to read/send file {target_file}: {e}")
        await bili_doc.finish(f"呜... 取出文件的时候发生了意外：{e}")