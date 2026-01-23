import re
from typing import List, Generator

def split_text_into_segments(text: str, max_length: int = 50) -> List[str]:
    """
    Split text into segments shorter than max_length, respecting sentence boundaries.
    """
    if not text:
        return []

    # Pre-clean: remove excessive whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Delimiters for splitting:
    # 1. Strong: 。！？\n (Full stop, Exclamation, Question, Newline)
    # 2. Weak: ，、； (Comma, Pause, Semicolon) - used if segments are still too long
    
    segments = []
    current_segment = ""
    
    # Initial split by strong delimiters
    # using regex to keep the delimiter attached to the end of the sentence
    # (.*?[:;?!。！？\n]) matches non-greedy until a delimiter
    
    # Better approach: Iterate characters or use a smart regex split
    # Split by strong delimiters, keeping them.
    # Pattern: Split after 。！？\n
    raw_sentences = re.split(r'([。！？\n])', text)
    
    # Re-assemble delimiters to sentences
    sentences = []
    temp_sent = ""
    for part in raw_sentences:
        temp_sent += part
        if re.match(r'[。！？\n]', part):
            sentences.append(temp_sent)
            temp_sent = ""
    if temp_sent:
        sentences.append(temp_sent)

    # Now merge sentences into segments up to max_length
    current_chunk = ""
    
    for sentence in sentences:
        if len(current_chunk) + len(sentence) <= max_length:
            current_chunk += sentence
        else:
            # Current chunk is full-ish, push it
            if current_chunk:
                segments.append(current_chunk)
                current_chunk = ""
            
            # If the single sentence itself is too long, we need to split it further (by weak delimiters)
            if len(sentence) > max_length:
                # Try splitting by commas/semicolons
                sub_parts = re.split(r'([，、；])', sentence)
                sub_sentences = []
                temp_sub = ""
                for sub in sub_parts:
                    temp_sub += sub
                    if re.match(r'[，、；]', sub):
                        sub_sentences.append(temp_sub)
                        temp_sub = ""
                if temp_sub:
                    sub_sentences.append(temp_sub)
                
                # Add sub-sentences
                for sub in sub_sentences:
                    if len(current_chunk) + len(sub) <= max_length:
                        current_chunk += sub
                    else:
                        if current_chunk:
                            segments.append(current_chunk)
                        current_chunk = sub
            else:
                current_chunk = sentence
    
    if current_chunk:
        segments.append(current_chunk)
        
    return segments
