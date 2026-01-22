from pydantic import BaseModel


class Config(BaseModel):
    # TTS 容器的 API 地址
    sovits_api_url: str = "http://tts-infer:3333"

    # 核心模型参数 (注意：这些路径必须是 TTS 容器内部看到的路径)
    ref_audio_path: str = "/app/ref_audio/mika_zh.wav"
    ref_text: str = ""
    ref_language: str = "zh"

    # 推理参数
    top_k: int = 15
    top_p: float = 1.0
    temperature: float = 1.0
    speed_factor: float = 1.0
    text_split_method: str = "cut0"  # 默认不切分，由 Bot 控制短文本
