from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class KeywordFetchStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    AUTH_ERROR = "auth_error"
    UPSTREAM_ERROR = "upstream_error"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"

class KeywordItemResult(BaseModel):
    keyword: str
    status: KeywordFetchStatus
    data: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_message: Optional[str] = None

class KeywordBatchResult(BaseModel):
    success: bool
    overall_status: str # "success", "partial", "failed"
    keywords: List[str]
    start_date: str
    end_date: str
    dates: List[str]
    results: Dict[str, KeywordItemResult] = Field(default_factory=dict)
    # 兼容现有格式的纯数据字典，但仅包含 success 和 empty 的真实数据，failed 词不填充为 0
    data: Dict[str, Dict[str, Dict[str, Any]]] = Field(default_factory=dict)
    successful_keywords: List[str] = Field(default_factory=list)
    empty_keywords: List[str] = Field(default_factory=list)
    failed_keywords: List[str] = Field(default_factory=list)
    error_summary: Optional[str] = None

class ProviderFetchStatus(str, Enum):
    SUCCESS = "success"
    EMPTY = "empty"
    AUTH_ERROR = "auth_error"
    UPSTREAM_ERROR = "upstream_error"
    TIMEOUT = "timeout"

class ProviderFetchResult(BaseModel):
    status: ProviderFetchStatus
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    pages_fetched: int = 0
    expected_pages: int = 0
    error: Optional[str] = None

    def __iter__(self):
        return iter(self.rows)

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, item):
        return self.rows[item]
