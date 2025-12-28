from pydantic import BaseModel, field_validator

class Config(BaseModel):
    # Role definitions
    ROLE_SYSTEM: str = "system"
    ROLE_USER: str = "user"
    ROLE_ASSISTANT: str = "assistant"
    
    # plugin configs
    BOT_QQ: str = ""
    RESP_INDEX: int = 0
    GROUP_MSG_CONTEXT_LIMIT: int = 64
    GROUP_WORD_CONTEXT_LIMIT: int = 2048
    SEND_INTERVAL: float = 1.5
    AI_NAME: str = "Miku"
    MIKU_PREFIX: set[str | tuple[str, ...]] | None = {"miku,", "miku， ", "miku，", "Miku, ", "Miku,", "Miku， ", "Miku，"}
    SYS_PREFIX: set[str | tuple[str, ...]] | None = {"info", "sts", "statistic", "stat"}
    EMPTY_STR: str = ""
    MATCH_ALL_CMD: str = ""
    TOP_INDEX: int = 0
    ADMINISTOR: str = ""
    FRIEND_REQ: bool = True

    @field_validator("RESP_INDEX")
    def check_resp_index(cls, value: int) -> int:
        if 0 <= value <= 10:
            return value
        raise ValueError("response index must between [0, 10]")
    
    @field_validator("GROUP_WORD_CONTEXT_LIMIT")
    def check_group_word_limit(cls, value: int) -> int:
        if 0 <= value <= 500:
            return value
        raise ValueError("response index must between [0, 500]")
    
    @field_validator("GROUP_MSG_CONTEXT_LIMIT")
    def check_group_msg_limit(cls, value: int) -> int:
        if 0 <= value <= 50:
            return value
        raise ValueError("response index must between [0, 50]")