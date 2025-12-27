from enum import Enum

class State(Enum):
    INVALID = 0
    TXT_STREAM = 1
    WAITING_TXT = 2
    REF = 3
    REF_END = 4
    SENTENCE_END = 5
    NUM_STREAM = 6
    TEMP_INLINE_CODE = 7
    INLINE_CODE = 8
    TEMP_CODE_BLOCK = 9
    CODE_BLOCK = 10
    CODE_BLOCK_END = 11
    TEMP_CODE_END = 12

class Event(Enum):
    TXT = 0 
    INNER_PUNCTUATION = 1
    END_PUNCTUATION = 2 
    LEFT_BRACKETS = 3
    RIGHT_BRACKETS = 4
    OUTPUT_SENTENCE = 5 
    RESET = 6
    NUMBER = 7
    INLINE_CODE_SYMBOL = 8

class StateMachine:
    def __init__(self) -> None:
        self.__current_state = State.TXT_STREAM
        self.__numbers = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
        self.__number_period = ["."]
        self.__inner_punctuation = [",", ";", ":", "/", "，", "、", "；", "："]
        self.__end_punctuation = [".", "?", "!", "\n", "。", "？", "！"]
        self.__common_left_brackets = ["\'", "\"", "(", "[", "{", "<", "“", "（", "《", "「"]
        self.__common_right_brackets = ["\'", "\"", ")", "]", "}", ">", "”", "）", "》", "」"]
        self.__inline_highlight_brackets = ["*"]
        self.__inline_math_brackets = ["$"]
        self.__inline_code_brackets = ["`"]
        self.__state_matrix = [
        # TXT0  INNER_PUNCTUATION1  END_PUNCTUATION2  LEFT_BRACKETS3  RIGHT_BRACKETS4  OUTPUT_SENTENCE5  RESET6  NUMBER7 INLINE_CODE_SYMBOL8
        [0,     0,                  0,                0,              0,               0,                1,      0,      0],            # INVALID           0
        [1,     2,                  5,                3,              0,               0,                1,      6,      7],            # TXT_STREAM        1
        [1,     0,                  0,                3,              0,               0,                1,      1,      7],            # WAITING_TXT       2       
        [3,     3,                  3,                0,              5,               0,                1,      3,      7],            # REF               3
        [1,     2,                  5,                0,              0,               1,                1,      0,      0],            # REF_END           4 (deprecated)
        [0,     0,                  0,                0,              0,               1,                1,      0,      0],            # SENTENCE_END      5
        [1,     0,                  0,                0,              0,               0,                1,      6,      0],            # NUM_STREAM        6
        [8,     8,                  8,                8,              8,               0,                1,      8,      9],            # TEMP_INLINE_CODE  7
        [8,     8,                  8,                8,              8,               0,                1,      8,      1],            # INLINE_CODE       8
        [0,     0,                  0,                0,              0,               0,                1,      0,      10],           # TEMP_CODE_BLOCK   9
        [10,    10,                 10,               10,             10,              10,               1,      10,     11],           # CODE_BLOCK        10
        [0,     0,                  0,                0,              0,               0,                0,      0,      12],           # CODE_BLOCK_END    11
        [0,     0,                  0,                0,              0,               0,                0,      0,      5]             # TEMP_CODE_END     12
    ]
 
    def reset(self) -> None:
        self.__current_state = State.TXT_STREAM

    def transit_by(self, char) -> None:
        event = self.__parse_char_to_event__(char)
        state_num = self.__state_matrix[self.__current_state.value][event.value]
        self.__current_state = State(state_num)

    def get_current_state(self) -> State:
        return self.__current_state

    # todo 严重bug，数字流状态判定和转移，句号、双引号错误
    def __parse_char_to_event__(self, char) -> Event:
        if char in self.__inner_punctuation:
            return Event.INNER_PUNCTUATION
        elif char in self.__number_period:
            return Event.NUMBER
        elif char in self.__end_punctuation:
            return Event.END_PUNCTUATION
        elif char in self.__common_left_brackets:
            return Event.LEFT_BRACKETS
        elif char in self.__common_right_brackets:
            return Event.RIGHT_BRACKETS
        elif char in self.__inline_code_brackets:
            return Event.INLINE_CODE_SYMBOL
        
        return Event.TXT

