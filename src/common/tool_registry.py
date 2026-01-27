import json
import inspect
from typing import Callable, Dict, Any, List, Optional
from nonebot import logger

class ToolRegistry:
    _tools: Dict[str, Callable] = {}
    _tool_definitions: List[Dict[str, Any]] = []

    @classmethod
    def register(cls, name: str, description: str, parameters: Optional[Dict[str, Any]] = None, strict: bool = True):
        """
        装饰器：注册一个工具函数。
        :param name: 工具名称 (AI 调用的标识符)
        :param description: 工具描述 (告诉 AI 这个工具是干嘛的)
        :param parameters: 参数定义的 JSON Schema。
                           注意：开启 strict=True 时，DeepSeek/OpenAI 要求：
                           1. "additionalProperties": False 必须存在。
                           2. 所有 properties 必须在 required 列表中。
        :param strict: 是否开启 Structured Outputs (Strict Mode)。默认为 True。
        """
        def decorator(func: Callable):
            cls._tools[name] = func
            
            final_params = parameters or {"type": "object", "properties": {}, "required": []}
            
            if strict:
                # 强制要求 additionalProperties 为 False
                if "additionalProperties" not in final_params:
                    final_params["additionalProperties"] = False
                
                # Strict Mode 要求所有字段必须是必填的
                # 如果用户没有显式提供 required，或者漏了一些字段，这里尝试自动补全
                # (注意：这可能会导致原本可选的参数变成必填，需要插件开发者注意)
                props = final_params.get("properties", {})
                reqs = set(final_params.get("required", []))
                for key in props.keys():
                    reqs.add(key)
                final_params["required"] = list(reqs)

            tool_schema = {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": final_params,
                    "strict": strict
                }
            }
            cls._tool_definitions.append(tool_schema)
            logger.info(f"Registered tool: {name} (Strict: {strict})")
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
            # 检查函数是否是异步生成器
            if inspect.isasyncgenfunction(func):
                return func(**arguments)
            # 检查函数是否是异步的
            elif inspect.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} with {arguments}, error: {e}")
            return f"Error executing tool: {e}"

# 全局实例
tool_registry = ToolRegistry
