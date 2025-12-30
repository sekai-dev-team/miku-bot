from pathlib import Path
import asyncio
import docker
from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, GroupMessageEvent, Message
from nonebot.params import CommandArg
from nonebot.log import logger

# Constants
CONTAINER_NAME = "sekai-bilinote-local"
SHARED_DIR = Path("/app/data/local_bilinote")

# Command definition
bili_note = on_command("笔记", aliases={"bili_note", "summary"}, priority=5, block=True)

@bili_note.handle()
async def handle_note(bot: Bot, event: Event, args: Message = CommandArg()):
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
            return container.exec_run(f'python3 main.py "{video_url}"', stream=False)
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
            if isinstance(event, GroupMessageEvent):
                await bot.upload_group_file(
                    group_id=event.group_id,
                    file=str(file_path),
                    name=file_path.name
                )
            else:
                await bot.upload_private_file(
                    user_id=event.user_id,
                    file=str(file_path),
                    name=file_path.name
                )
        except Exception as e:
            logger.error(f"Failed to upload file {file_path}: {e}")
            await bili_note.send(f"哎呀，文件 {file_path.name} 发送失败了... 可能是网络波动？")