import psutil
import httpx
import json
import time
import subprocess
import shutil
from datetime import timedelta
from nonebot import get_plugin_config
from .config import Config
from src.common.config import GLOBAL_AI_CONFIG

# constant
CONFIG = get_plugin_config(Config)

class SystemMonitor:
    _start_time = time.time()

    @staticmethod
    def _progress_bar(percent: float, length: int = 10) -> str:
        """生成文本进度条 [■■■□□□□□□□]"""
        filled = int(length * percent / 100)
        bar = "■" * filled + "□" * (length - filled)
        return f"[{bar}]"

    @classmethod
    def uptime(cls) -> str:
        """获取运行时间"""
        delta = timedelta(seconds=int(time.time() - cls._start_time))
        return f"已运行: {delta}"

    @classmethod
    def memory(cls) -> str:
        mem = psutil.virtual_memory()
        percent = mem.percent
        used_mb = mem.used / 1024 / 1024
        total_mb = mem.total / 1024 / 1024
        
        bar = cls._progress_bar(percent)
        return (
            f"内存: {percent}%\n"
            f"{bar}\n"
            f"   {used_mb:.0f}MB / {total_mb:.0f}MB"
        )

    @classmethod
    def vram(cls) -> str:
        """尝试获取显存状态 (NVIDIA only)"""
        if not shutil.which("nvidia-smi"):
            # 如果没有 nvidia-smi，静默返回 None 或简短提示，避免刷屏
            # 这里返回 None 让调用者决定是否显示
            return None
        
        try:
            # Query memory.used and memory.total in MB
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                return None

            output = result.stdout.strip()
            lines = output.split('\n')
            if not lines or not output:
                return None

            info_str = ""
            for i, line in enumerate(lines):
                try:
                    parts = line.split(',')
                    if len(parts) == 2:
                        used = float(parts[0].strip())
                        total = float(parts[1].strip())
                        percent = (used / total) * 100 if total > 0 else 0
                        
                        bar = cls._progress_bar(percent)
                        # If multiple GPUs, prefix with index
                        prefix = f"GPU{i}: " if len(lines) > 1 else "显存: "
                        
                        # Add newline only if it's not the first item
                        if info_str: 
                            info_str += "\n"
                            
                        info_str += (
                            f"{prefix}{percent:.1f}%\n"
                            f"{bar}\n"
                            f"   {used:.0f}MB / {total:.0f}MB"
                        )
                except ValueError:
                    continue
                    
            return info_str if info_str else None

        except Exception:
            return None
    
    @classmethod
    def cpu(cls) -> str:
        # interval=0 非阻塞获取，虽然第一次调用可能不准，但在长期运行中足够参考
        # 或者可以保存上一次的状态，这里简单处理
        cpu_percent = psutil.cpu_percent(interval=None) 
        bar = cls._progress_bar(cpu_percent)
        return (
            f"CPU: {cpu_percent}%\n"
            f"{bar}"
        )
    
    @classmethod
    async def balance(cls) -> str:
        """异步获取余额信息"""
        if not GLOBAL_AI_CONFIG.API_KEY:
            return "API: 未配置 Key"

        # 使用全局配置的 BASE_URL
        base_url = GLOBAL_AI_CONFIG.BASE_URL
        if base_url.endswith("/"):
             balance_url = f"{base_url}user/balance"
        else:
             balance_url = f"{base_url}/user/balance"

        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {GLOBAL_AI_CONFIG.API_KEY}'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(balance_url, headers=headers, timeout=5.0)
                
            if response.status_code != 200:
                return f"API余额: 查询失败 ({response.status_code})"

            parsed = response.json()
            
            # 简单保护，防止字段不存在报错
            if 'balance_infos' not in parsed:
                return f"API余额: 格式无法解析"

            balance_info = parsed['balance_infos'][0]
            currency = balance_info.get('currency', 'CNY')
            total = balance_info.get('total_balance', '0')
            
            return (
                f"API余额: {total} {currency}\n"
                f"   (可用: {parsed.get('is_available', False)})"
            )
            
        except Exception as e:
            return f"API余额: 查询出错"