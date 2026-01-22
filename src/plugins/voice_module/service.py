import httpx
import uuid
import os
import subprocess
from pathlib import Path
from nonebot import logger
from .config import Config
from src.common.tool_registry import tool_registry

config = Config()

class VoiceService:
    @staticmethod
    async def synthesize(text: str, **kwargs) -> str:
        """
        调用 TTS API 合成语音，返回本地文件路径。
        """
        url = config.sovits_api_url
        
        # 构造请求体
        payload = {
            "text": text,
            "text_lang": kwargs.get("lang", "zh"),
            "ref_audio_path": kwargs.get("ref_path", config.ref_audio_path),
            "prompt_text": kwargs.get("prompt", config.ref_text),
            "prompt_lang": kwargs.get("ref_language", config.ref_language),
            "top_k": kwargs.get("top_k", config.top_k),
            "top_p": kwargs.get("top_p", config.top_p),
            "temperature": kwargs.get("temperature", config.temperature),
            "text_split_method": kwargs.get("split", config.text_split_method),
            "batch_size": 1,
            "batch_threshold": 0.75,
            "split_bucket": True,
            "speed_factor": kwargs.get("speed", config.speed_factor),
            "fragment_interval": 0.3,
            "seed": -1,
            "media_type": "wav",
            "streaming_mode": False,
            "parallel_infer": True,
            "repetition_penalty": 1.35
        }
        
        try:
            async with httpx.AsyncClient() as client:
                # 优先尝试 POST (功能更全)
                # 增加超时时间，因为 TTS 可能较慢
                resp = await client.post(f"{url}/tts", json=payload, timeout=60.0)
                
                # 如果 POST 失败 (405 Method Not Allowed)，尝试 GET
                if resp.status_code == 405:
                    logger.warning("POST /tts not allowed, falling back to GET.")
                    # 构造 GET 参数 (仅包含基础参数)
                    params = {
                        "text": payload["text"],
                        "text_lang": payload["text_lang"],
                        "ref_audio_path": payload["ref_audio_path"],
                        "prompt_text": payload["prompt_text"],
                        "prompt_lang": payload["prompt_lang"],
                        "media_type": payload["media_type"]
                        # 注意：GET 模式下通常无法传递复杂的推理参数 (如 speed_factor, top_k 等)，视服务端实现而定
                    }
                    resp = await client.get(f"{url}/tts", params=params, timeout=60.0)

                resp.raise_for_status()
                
                # 保存临时 WAV
                # 优先使用相对路径 data/voice_temp
                temp_dir = Path("data/voice_temp")
                temp_dir.mkdir(parents=True, exist_ok=True)
                
                raw_filename = f"{uuid.uuid4()}.wav"
                raw_path = temp_dir / raw_filename
                
                with open(raw_path, "wb") as f:
                    f.write(resp.content)
                
                # 转换格式 (MP3)
                output_filename = f"{uuid.uuid4()}.mp3"
                output_path = temp_dir / output_filename
                
                # ffmpeg command
                try:
                    subprocess.run([
                        "ffmpeg", "-y", "-i", str(raw_path),
                        "-acodec", "libmp3lame", "-q:a", "2",
                        str(output_path)
                    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except (FileNotFoundError, subprocess.CalledProcessError) as e:
                    logger.warning(f"FFmpeg conversion failed: {e}. Returning WAV.")
                    output_path = raw_path
                    return str(raw_path.absolute())
                
                # Clean up raw file
                if output_path != raw_path and raw_path.exists():
                    os.remove(raw_path)
                
                return str(output_path.absolute())
                
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise e

    @staticmethod
    async def set_gpt_weights(weights_path: str):
        """切换 GPT 模型权重"""
        url = config.sovits_api_url
        params = {"weights_path": weights_path}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/set_gpt_weights", params=params, timeout=10.0)
            resp.raise_for_status()
            return resp.text

    @staticmethod
    async def set_sovits_weights(weights_path: str):
        """切换 SoVITS 模型权重"""
        url = config.sovits_api_url
        params = {"weights_path": weights_path}
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{url}/set_sovits_weights", params=params, timeout=10.0)
            resp.raise_for_status()
            return resp.text

    @staticmethod
    def update_config(key: str, value: str):
        """动态更新配置 (暂存内存)"""
        if hasattr(config, key):
            # 类型转换
            field_type = type(getattr(config, key))
            try:
                if field_type == int:
                    new_val = int(value)
                elif field_type == float:
                    new_val = float(value)
                else:
                    new_val = value
                setattr(config, key, new_val)
                return True
            except ValueError:
                return False
        return False

@tool_registry.register(
    name="speak_text",
    description="将文本转换为语音发送。当用户要求'念出来'、'说这句'，或者你觉得用语音表达更合适时使用。不要在每一句话都使用，仅在特定情境下使用。",
    parameters={
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "需要朗读的文本内容"
            },
             "emotion": {
                "type": "string",
                "description": "情感风格 (目前通过 prompt text 控制，暂未直接映射，可保留接口)",
                "enum": ["neutral", "happy", "sad", "angry"]
            }
        },
        "required": ["text"]
    }
)
async def speak_text(text: str, emotion: str = "neutral") -> str:
    """
    TTS 工具入口
    """
    try:
        file_path = await VoiceService.synthesize(text)
        return f"[VOICE:{file_path}]"
    except Exception as e:
        return f"语音合成失败: {str(e)}"
