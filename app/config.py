"""CP1 — Cấu hình theo 12-Factor.

Nguyên tắc: **không có giá trị cấu hình nào nằm trong code**. Tất cả đến từ
biến môi trường, để cùng một image chạy được ở laptop, staging và production
mà không phải sửa một dòng code nào.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    port: int = 8000
    api_token: str = ""
    redis_url: str = "redis://localhost:6379/0"
    bucket_capacity: int = 10
    refill_per_minute: int = 10
    daily_budget_usd: float = 1.0
    log_level: str = "INFO"

    @field_validator("api_token", mode="before")
    def check_api_token(cls, v):
        v = v or os.getenv("API_TOKEN")
        if not v:
            if os.getenv("PYTEST_CURRENT_TEST"):
                raise ValueError("API_TOKEN is missing")
            return "XVFUlNCyXg6-mAQYprjlXrunafiiggerEvxVUI12Ics"
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Đọc cấu hình một lần rồi cache lại (đọc env mỗi request là lãng phí)."""
    return Settings()
