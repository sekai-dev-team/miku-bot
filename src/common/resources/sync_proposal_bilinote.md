# 笔记同步方案：服务器 Docker -> 本地 Mac 知识库

## 1. 背景与目标
*   **现状**：
    *   Miku Bot 运行在远程服务器的 Docker 容器中。
    *   通过指令触发 `sekai-bilinote` 容器生成 B站视频总结笔记（Markdown 格式）。
    *   生成的笔记存储在服务器的宿主机目录（Docker Volume 挂载路径，例如 `./data/bilinote_shared`）。
*   **目标**：
    *   实现服务器端生成的 `.md` 笔记自动同步/传输到本地 Mac 的 KnowledgeBase 目录中，以便进行后续整理和归档。

---

## 2. 待选方案详细评估

### 方案 A：服务器主动推送 (Watchdog + SCP)
这是你最初构想的方案。在服务器上运行监控脚本，一旦发现新文件，立即推送到 Mac。

*   **工作原理**：
    1.  服务器运行一个 Python 脚本（使用 `watchdog` 库）监听笔记目录。
    2.  检测到 `on_created` 事件。
    3.  脚本执行系统命令：`scp /path/to/note.md user@your_mac_ip:/path/to/kb/`。
*   **前置条件（关键难点）**：
    *   **网络通路**：服务器必须能直接连接到你的 Mac。由于 Mac 通常位于家庭/公司内网，**没有公网 IP**，这通常需要配置 **FRP/Ngrok 内网穿透** 或 **IPv6**。
    *   **SSH 服务**：Mac 需要在“系统设置 -> 通用 -> 共享”中开启“远程登录”。
    *   **免密认证**：需要将服务器的 SSH 公钥 (`id_rsa.pub`) 添加到 Mac 的 `~/.ssh/authorized_keys` 中。
*   **优点**：
    *   实时性最高（毫秒级响应）。
    *   符合“事件驱动”的编程直觉。
*   **缺点**：
    *   网络配置极其繁琐（解决内网穿透问题）。
    *   安全性风险（Mac 需要向公网暴露 SSH 端口）。

### 方案 B：Mac 主动拉取 (Rsync + Crontab) 【最简便】
转变思路，由网络环境较好的 Mac 主动去服务器“取”文件。

*   **工作原理**：
    *   在 Mac 本地设置一个定时任务（Crontab）。
    *   每隔一段时间（如 1 分钟或 5 分钟）运行一次 `rsync` 命令。
    *   命令示例：
        ```bash
        rsync -avz --ignore-existing -e ssh user@your_server_ip:/path/to/server/notes/ /Users/Asuna/KnowledgeBase/Inbox/
        ```
*   **优点**：
    *   **极易实现**：无需任何额外的网络配置，只要 Mac 能连上服务器即可。
    *   **安全**：不需要 Mac 暴露端口。
    *   **增量同步**：`rsync` 非常高效，只会传输新文件。
*   **缺点**：
    *   非实时：会有几分钟的延迟（取决于定时任务频率）。

### 方案 C：使用同步软件 (Syncthing) 【最推荐 / 优雅】
使用专门的 P2P 文件同步工具，像 Dropbox 一样无感同步。

*   **工作原理**：
    1.  在 **服务器** 和 **Mac** 上各安装一个 Syncthing（开源免费）。
    2.  在 Web 界面中互相添加“设备 ID”。
    3.  指定同步文件夹：服务器的 `bilinote_shared` <-> Mac 的 `Inbox`。
*   **优点**：
    *   **自带穿透**：Syncthing 拥有强大的 P2P 发现机制，无需公网 IP 也能穿透内网直连。
    *   **实时同步**：文件生成后几秒内自动同步。
    *   **双向/单向**：配置灵活，且不仅限于笔记，以后有其他文件想互传也很方便。
    *   **零代码**：不需要写脚本，不需要维护 Crontab。
*   **缺点**：
    *   需要在服务器和 Mac 上各运行一个后台服务。

---

## 3. 实施建议

### 如果你追求“代码实现的快感”且**已有内网穿透**：
-> 选择 **方案 A (Watchdog + SCP)**。
我们可以编写一个 `sync_watchdog.py` 放在服务器运行。

### 如果你追求“最快搞定”且**不介意非实时**：
-> 选择 **方案 B (Rsync 拉取)**。
只需在 Mac 终端执行 `crontab -e` 添加一行即可。

### 如果你追求“长期稳定与优雅”：
-> 选择 **方案 C (Syncthing)**。
这是最符合“构建系统”思维的方案，一劳永逸。

---

## 4. 附录：方案 A (Watchdog) 代码草稿
如果你决定克服网络困难采用方案 A，这是你需要的脚本核心逻辑：

```python
import time
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class NewNoteHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory or not event.src_path.endswith(".md"):
            return
        
        print(f"检测到新笔记: {event.src_path}")
        # 这里需要替换为你的 Mac 实际访问地址（可能通过 FRP 映射的端口）
        cmd = [
            "scp", "-P", "2222",  # 假设 FRP 映射端口为 2222
            event.src_path, 
            "asuna@your.mac.address:/Users/Asuna/KnowledgeBase/Inbox/"
        ]
        try:
            subprocess.run(cmd, check=True)
            print("同步成功！")
        except subprocess.CalledProcessError as e:
            print(f"同步失败: {e}")

if __name__ == "__main__":
    path = "/path/to/server/bilinote_shared"
    observer = Observer()
    observer.schedule(NewNoteHandler(), path, recursive=False)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
```
