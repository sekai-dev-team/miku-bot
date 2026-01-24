import json
from pathlib import Path
from pydantic import BaseModel
from typing import Any
from src.common.config_manager import config_manager

class Config(BaseModel):
    # TTS 容器的 API 地址
    sovits_api_url: str = "http://tts-infer:3333"

    # 核心模型参数 (注意：这些路径必须是 TTS 容器内部看到的路径)
    ref_audio_path: str = "/app/ref_audio/mika_zh.wav"
    ref_text: str = (
        "万圣节快乐哦~☆听说今天商场有卖一日限定的饰品呢，老师要不要和我一起去购物呀？"
    )
    ref_language: str = "zh"

    # 推理参数
    top_k: int = 15
    top_p: float = 1.0
    temperature: float = 1.0
    speed_factor: float = 1.0
    text_split_method: str = "cut0"  # 默认不切分，由 Bot 控制短文本
    max_segment_length: int = 50
    parallel_infer: bool = False
    
    # 高级推理参数
    batch_size: int = 1
    batch_threshold: float = 0.75
    split_bucket: bool = True
    fragment_interval: float = 0.3
    seed: int = -1
    media_type: str = "wav"
    streaming_mode: bool = False
    repetition_penalty: float = 1.35
    
    # 网络参数
    tts_timeout: float = 120.0

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.load_from_file()

    def load_from_file(self):
        data = config_manager.get_config("voice")
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)

    def save_to_file(self):
        data = self.model_dump()
        config_manager.save_config("voice", data)

config = Config()
