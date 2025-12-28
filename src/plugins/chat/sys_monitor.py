import psutil
import httpx
import json
import time
from datetime import timedelta
from nonebot import get_plugin_config
from .config import Config

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
        return f"⏳ 已运行: {delta}"

    @classmethod
    def memory(cls) -> str:
        mem = psutil.virtual_memory()
        percent = mem.percent
        used_mb = mem.used / 1024 / 1024
        total_mb = mem.total / 1024 / 1024
        
        bar = cls._progress_bar(percent)
        return (
            f"🧠 内存: {percent}%\n"
            f"{bar}\n"
            f"   {used_mb:.0f}MB / {total_mb:.0f}MB"
        )
    
    @classmethod
    def cpu(cls) -> str:
        # interval=0 非阻塞获取，虽然第一次调用可能不准，但在长期运行中足够参考
        # 或者可以保存上一次的状态，这里简单处理
        cpu_percent = psutil.cpu_percent(interval=None) 
        bar = cls._progress_bar(cpu_percent)
        return (
            f"🖥️ CPU: {cpu_percent}%\n"
            f"{bar}"
        )
    
    @classmethod
    async def balance(cls) -> str:
        """异步获取余额信息"""
        if not CONFIG.API_KEY:
            return "💳 API: 未配置 Key"

        # 注意：DeepSeek 的 balance API 路径可能需要根据实际情况调整
        # 这里假设 base_url 是标准的 OpenAI 格式，DeepSeek 可能有不同的 endpoint
        # 如果是 DeepSeek，官方通常没有标准的 OpenAI balance 接口，这里保留原逻辑，
        # 但要注意 URL 拼接风险。假设 CONFIG.BASE_URL 结尾没有 /
        
        # 很多兼容 OpenAI 的中转商使用 /dashboard/billing/credit_grants 或自定义接口
        # 这里沿用原代码的 /user/balance 路径，只改为异步
        
        balance_url = f"{CONFIG.BASE_URL}/user/balance"
        # 移除末尾多余的斜杠以防万一
        if CONFIG.BASE_URL.endswith("/"):
             balance_url = f"{CONFIG.BASE_URL}user/balance"

        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {CONFIG.API_KEY}'
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(balance_url, headers=headers, timeout=5.0)
                
            if response.status_code != 200:
                return f"💳 API余额: 查询失败 ({response.status_code})"

            parsed = response.json()
            
            # 简单保护，防止字段不存在报错
            if 'balance_infos' not in parsed:
                return f"💳 API余额: 格式无法解析"

            balance_info = parsed['balance_infos'][0]
            currency = balance_info.get('currency', 'CNY')
            total = balance_info.get('total_balance', '0')
            
            return (
                f"💳 API余额: {total} {currency}\n"
                f"   (可用: {parsed.get('is_available', False)})"
            )
            
        except Exception as e:
            return f"💳 API余额: 查询出错"