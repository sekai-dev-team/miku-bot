import math
from typing import List, Dict

def estimate_token(text: str) -> int:
    """
    估算文本的 Token 数量。
    由于没有本地 Tokenizer，采用保守的启发式算法：
    - 中文字符 (CJK): ~0.7 token (DeepSeek 官方数据偏向 0.6，取 0.7 更安全)
    - 英文字符/数字: ~0.4 token (标准单词约为 1.3 字符，0.3-0.4 token)
    - 其他: ~0.5 token
    """
    if not text:
        return 0
        
    token_count = 0.0
    for char in text:
        if '\u4e00' <= char <= '\u9fff':  # CJK Unified Ideographs
            token_count += 0.7
        elif char.isascii():
            token_count += 0.4
        else:
            token_count += 0.5
            
    return math.ceil(token_count)

def estimate_messages_token(messages: List[Dict[str, str]]) -> int:
    """
    估算整个消息列表的 Token 数量，包含 JSON 结构开销。
    
    OpenAI/DeepSeek 格式通常每条消息有 3-4 token 的结构开销：
    <|im_start|>role\ncontent<|im_end|>\n
    """
    total_tokens = 0
    # 基础开销，整个列表的引导
    total_tokens += 3
    
    for msg in messages:
        # 每条消息的结构开销 (role + content + tags)
        total_tokens += 4 
        
        # 内容 Token
        content = msg.get("content", "")
        total_tokens += estimate_token(str(content))
        
        # Role Token (虽然很短，也算上)
        role = msg.get("role", "")
        total_tokens += estimate_token(role)
        
    return total_tokens
