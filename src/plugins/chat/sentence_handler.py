class SentenceBuffer:
    def __init__(self) -> None:
        self.buffer = ""
        self.in_code_block = False # ``` code ```
        self.in_inline_code = False # `code`
        
        # 强标点：遇到这些通常意味着句子结束
        self.strong_punctuations = set(['?', '!', '\n', '。', '？', '！', '…'])
        # 弱标点：需要看上下文（比如点号）
        self.weak_punctuations = set(['.'])
        # 闭合符号：如果标点后面紧跟这些，说明标点是在引号/括号里，不应该切分
        self.closing_brackets = set(['"', "'", '”', '’', ')', ']', '}', '）', '】', '’'])
        
    def reset(self) -> None:
        self.buffer = ""
        self.in_code_block = False
        self.in_inline_code = False

    def append(self, char: str) -> str:
        """
        向缓冲区追加字符。
        逻辑：
        1. 检查 '上一个字符' 是否构成了断句条件。
        2. 如果是，则弹出 '上一个字符之前的所有内容' 作为一句话。
        3. 将当前 'char' 加入缓冲区。
        """
        if not char:
            return None

        result = None
        
        # 1. 尝试基于“上一刻的状态”进行切分
        # 我们只有在缓冲区非空时才能判断是否要切分之前的内容
        if self.buffer:
            last_char = self.buffer[-1]
            should_flush = False

            # 如果在代码块里，仅当遇到换行且可能结束代码块时才考虑（太复杂，这里简化：代码块内完全由 ``` 控制）
            # 简单策略：代码块内不因标点切分
            if self.in_code_block or self.in_inline_code:
                should_flush = False
            else:
                # 情况 A: 换行符通常是绝对的切分点 (除非是在处理 Markdown 列表等，但在聊天中通常换行就是新一句)
                if last_char == '\n':
                    should_flush = True
                
                # 情况 B: 强标点 (。！？)
                elif last_char in self.strong_punctuations:
                    # 防碎逻辑：如果当前字符和上一个一样（比如 ！！ ？？），不切
                    # 也可以防止 ... 被切（如果 … 算强标点）
                    if char != last_char and char not in self.closing_brackets:
                        should_flush = True
                
                # 情况 C: 弱标点 (.)
                elif last_char in self.weak_punctuations:
                    # 防碎逻辑：
                    # 1. 如果是数字 (3.14) -> 不切
                    # 2. 如果还是点 (省略号 ...) -> 不切
                    # 3. 如果是闭合引号 ("Ok.") -> 不切
                    if not char.isdigit() and char != '.' and char not in self.closing_brackets:
                        should_flush = True
            
            # 执行切分
            if should_flush:
                result = self.buffer.strip()
                # 切分后，旧 buffer 被清空（实际上是替换为当前 char，因为当前 char 属于下一句）
                # 但这里要注意：result 拿走了 buffer，当前 char 应该成为新 buffer 的开始
                self.buffer = ""

        # 2. 将当前字符加入缓冲区 (这一步必须在切分逻辑之后)
        self.buffer += char
        
        # 3. 更新 Markdown 状态 (为下一次判断做准备)
        # 注意：这里简单的 endswith 检测可能在 flush 后失效，但在聊天场景下，
        # ``` 通常独占一行或在句尾，配合上面的 \n 切分逻辑，通常能工作。
        # 如果 ``` 被切分了（比如 `\n` 切分了），buffer 里可能只有 ```，这也能正确触发。
        if self.buffer.endswith("```"):
            self.in_code_block = not self.in_code_block
        
        # 行内代码检测 (仅在非代码块时)
        if char == '`' and not self.in_code_block:
             # 如果 buffer 只有 ` 或者前面不是转义符... 简单处理
             self.in_inline_code = not self.in_inline_code
             
        return result
    
    def force_flush(self) -> str:
        """强制弹出剩余内容（流结束时调用）"""
        result = self.buffer.strip()
        self.buffer = ""
        return result if result else None
