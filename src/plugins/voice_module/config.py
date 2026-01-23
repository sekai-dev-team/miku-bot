import json
from pathlib import Path
from pydantic import BaseModel
from typing import Any

CONFIG_PATH = Path(__file__).parent.parent.parent / "common" / "resources" / "voice_config.json"

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

    def __init__(self, **data: Any):
        super().__init__(**data)
        self.load_from_file()

    def load_from_file(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)
            except Exception as e:
                print(f"Error loading voice config: {e}")

    def save_to_file(self):
        try:
            # exclude=None to save all fields
            data = self.model_dump()
            CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")
        except Exception as e:
            print(f"Error saving voice config: {e}")
