import json
import inspect
from typing import Callable, Dict, Any, List, Optional
from nonebot import logger

class ToolRegistry:
    _tools: Dict[str, Callable] = {}
    _tool_definitions: List[Dict[str, Any]] = []

    @classmethod
    def register(cls, name: str, description: str, parameters: Optional[Dict[str, Any]] = None):
        """
        装饰器：注册一个工具函数。
        :param name: 工具名称 (AI 调用的标识符)
        :param description: 工具描述 (告诉 AI 这个工具是干嘛的)
        :param parameters: 参数定义的 JSON Schema (如果为 None，自动推导简单的类型，但建议手动提供更精准的 schema)
        """
        def decorator(func: Callable):
            cls._tools[name] = func
            
            # 如果没有提供 parameters，尝试简单的自动推导（仅限无参或简单参数，复杂建议手写）
            # 这里为了稳健，如果未提供且函数有参数，建议还是手动传入 schema
            tool_schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters or {"type": "object", "properties": {}, "required": []}
                }
            }
            cls._tool_definitions.append(tool_schema)
            logger.info(f"Registered tool: {name}")
            return func
        return decorator

    @classmethod
    def get_tools(cls) -> List[Dict[str, Any]]:
        """获取所有注册的工具定义 (OpenAI 格式)"""
        return cls._tool_definitions

    @classmethod
    async def dispatch(cls, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """分发并执行工具"""
        if tool_name not in cls._tools:
            return f"Error: Tool '{tool_name}' not found."
        
        func = cls._tools[tool_name]
        try:
            # 检查函数是否是异步的
            if inspect.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} with {arguments}, error: {e}")
            return f"Error executing tool: {e}"

# 全局实例
tool_registry = ToolRegistry
