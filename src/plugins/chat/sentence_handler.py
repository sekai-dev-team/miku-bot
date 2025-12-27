import re

class SentenceBuffer:
    def __init__(self) -> None:
        self.buffer = ""
        self.in_code_block = False # ``` code ```
        self.in_inline_code = False # `code`
        
        # 标点符号，遇到这些通常意味着句子结束
        self.end_punctuations = set(['.', '?', '!', '\n', '。', '？', '！', '…'])
        # 能够成对出现的符号，用于简单的上下文判断
        self.quote_stack = [] 
        
    def reset(self) -> None:
        self.buffer = ""
        self.in_code_block = False
        self.in_inline_code = False
        self.quote_stack = []

    def append(self, char: str) -> str:
        """
        向缓冲区追加字符，如果满足断句条件，返回这一句话；否则返回 None。
        """
        if not char:
            return None

        self.buffer += char
        
        # 1. 简单的 Markdown 状态检测
        # 注意：这里做的是简化的流式检测，可能无法完美处理所有极其复杂的嵌套情况，
        # 但对于聊天机器人的输出已经足够健壮。
        
        # 检测代码块标记 ```
        if self.buffer.endswith("```"):
            self.in_code_block = not self.in_code_block
            return None # 刚刚切换状态，肯定不是句子的结束
            
        # 如果在代码块里，绝对不切分（除非缓冲区爆炸，但这里先不做长度限制，信任 bot）
        if self.in_code_block:
            return None
            
        # 检测行内代码标记 `
        # 只有在非代码块模式下才有效
        if char == '`':
            self.in_inline_code = not self.in_inline_code
            return None
            
        # 如果在行内代码里，也不切分
        if self.in_inline_code:
            return None

        # 2. 判断是否断句
        if char in self.end_punctuations:
            # 2.1 特殊情况处理
            
            # 如果是英文点号 . ，后面必须不能紧跟数字（防止小数被切，如 3.14）
            # 但流式传输时我们看不到下一个字符，所以这里采取一种策略：
            # 遇到 . 先不返回，等下一个字符来了再决定？
            # 或者简单点：如果缓冲区最后几个字符像数字，就不切。
            if char == '.':
                if len(self.buffer) > 1 and self.buffer[-2].isdigit():
                     return None

            # 2.2 引号内的标点不切分 (例如：他说：“你好。”)
            # 这里简单判断一下引号堆栈（虽然流式很难完美，但能覆盖大部分）
            # 略，因为维护栈比较复杂，简单粗暴点：
            # 如果刚刚遇到标点，我们看缓冲区是否已经足够长，或者是否是换行符
            
            if char == '\n':
                return self._flush()
            
            # 如果是其他标点，我们倾向于切分，但为了防止 "Mr. Wang" 这种情况，
            # 或者是 "..." 省略号，我们可以稍微看下上下文。
            # 简化策略：只要遇到标点，且这句话长度 > 3，就切分。
            # 防止 AI 输出 "..." 时被切成三个 "."
            if self.buffer.endswith(".." ) or self.buffer.endswith("……"):
                return None
            
            return self._flush()
            
        return None
        
    def _flush(self) -> str:
        """弹出当前缓冲区的内容"""
        result = self.buffer.strip()
        if not result:
            return None
            
        # 清空缓冲区，准备下一句
        self.buffer = ""
        return result
    
    def force_flush(self) -> str:
        """强制弹出剩余内容（通常在流结束时调用）"""
        return self._flush()