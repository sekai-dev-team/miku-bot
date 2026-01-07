class SentenceBuffer:
    def __init__(self) -> None:
        self.buffer = ""
        self.in_code_block = False # ``` code ```
        self.in_inline_code = False # `code`
        
        # 强标点：遇到这些通常意味着句子结束
        self.strong_punctuations = set(['?', '!', '\n', '。', '？', '！', '…', '~', '～', '♪'])
        # 弱标点：需要看上下文（比如点号）
        self.weak_punctuations = set(['.'])
        # 闭合符号：如果标点后面紧跟这些，说明标点是在引号/括号里，不应该切分
        self.closing_brackets = set(['"', "'", '”', '’', ')', ']', '}', '）', '】', '’'])
        # 粘性字符：颜文字常用开头，如果标点后面跟了这些，先别切，粘在一起
        self.sticky_chars = set(['(', '[', '{', '*', '^', '<', '_', '—'])
        
    def reset(self) -> None:
        self.buffer = ""
        self.in_code_block = False
        self.in_inline_code = False

    def append(self, char: str) -> str:
        """
        向缓冲区追加字符。
        逻辑：
        1. 检查 '上一个字符' 或 '当前字符' 是否构成了断句条件。
        2. 如果是，则弹出缓冲区内容。
        3. 将当前 'char' 加入缓冲区。
        """
        if not char:
            return None

        result = None
        
        # 1. 尝试进行切分
        if self.buffer:
            last_char = self.buffer[-1]
            should_flush = False

            if self.in_code_block or self.in_inline_code:
                should_flush = False
            else:
                # 情况 A: 换行符是绝对的切分点
                # 如果当前是换行，或者上一个是换行，都直接切
                if char == '\n' or last_char == '\n':
                    should_flush = True
                
                # 情况 B: 强标点 (。！？~～♪)
                elif last_char in self.strong_punctuations:
                    # 防碎逻辑：
                    # 1. 如果当前字符也是强标点 -> 不切 (处理 ?! ！！！ ~~~)
                    # 2. 如果是闭合符号 -> 不切 (处理 ！”)
                    # 3. 如果是粘性字符 -> 不切 (处理 ？！(・∀・) )
                    if char not in self.strong_punctuations and \
                       char not in self.closing_brackets and \
                       char not in self.sticky_chars:
                        should_flush = True
                
                # 情况 C: 弱标点 (.)
                elif last_char in self.weak_punctuations:
                    is_list_marker = len(self.buffer) >= 2 and self.buffer[-2].isdigit()
                    if not char.isdigit() and \
                       char != '.' and \
                       char not in self.closing_brackets and \
                       char not in self.sticky_chars and \
                       not is_list_marker:
                        should_flush = True
                
                # 情况 D: 长度兜底。如果缓冲区太长了且遇到了空格，强制切分
                elif len(self.buffer) > 50 and char.isspace():
                    should_flush = True
            
            # 执行切分
            if should_flush:
                result = self.buffer.strip()
                self.buffer = ""

        # 2. 将当前字符加入缓冲区
        self.buffer += char
        
        # 3. 更新 Markdown 状态
        if self.buffer.endswith("```"):
            self.in_code_block = not self.in_code_block
        
        if char == '`' and not self.in_code_block:
             self.in_inline_code = not self.in_inline_code
             
        return result
    
    def force_flush(self) -> str:
        """强制弹出剩余内容（流结束时调用）"""
        result = self.buffer.strip()
        self.buffer = ""
        return result if result else None