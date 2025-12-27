import psutil
import requests
import json
from nonebot import get_plugin_config
from .config import Config

# constant
CONFIG = get_plugin_config(Config)
class SystemMonitor:
    @classmethod
    def memory(cls):
        mem_info = []
        mem = psutil.virtual_memory()
        mem_info.append(f"总内存: {(mem.total / 1024 / 1024):.2f}MB\n")
        mem_info.append(f"已使用: {(mem.used / 1024 / 1024):.2f}MB\n")
        mem_info.append(f"空闲: {(mem.available / 1024 / 1024):.2f}MB\n")
        mem_info.append(f"使用率: {(mem.percent):.2f}%")
        return "".join(mem_info)
    
    @classmethod
    def cpu(cls):
        cpu_percent = psutil.cpu_percent(interval=1)
        return f"CPU占用率: {cpu_percent}%"
    
    @classmethod
    def balance(cls):
        BALANCE_URL = f"{CONFIG.BASE_URL}/user/balance"
        payload={}
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {CONFIG.API_KEY}'
        }
        response = requests.request("GET", BALANCE_URL, headers=headers, data=payload)
        parsed = json.loads(response.text)
        string_builder = []
        string_builder.append(f"是否可调用API: {parsed['is_available']}\n")
        balance_info = parsed['balance_infos'][0]
        string_builder.append(f"充值货币: {balance_info['currency']}\n")
        string_builder.append(f"可用余额（包括赠金和充值余额）: {balance_info['total_balance']}\n")
        string_builder.append(f"可用赠金: {balance_info['granted_balance']}\n")
        string_builder.append(f"充值余额: {balance_info['topped_up_balance']}")

        return CONFIG.EMPTY_STR.join(string_builder)