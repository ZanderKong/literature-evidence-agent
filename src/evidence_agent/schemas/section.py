"""Section schemas."""

from typing import Any

from pydantic import BaseModel, ValidationInfo, field_validator


class Section(BaseModel):
    section_id: str
    source_id: str
    section_type: str
    heading: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    sequence_number: int
    text: str
    parser_name: str
    parser_version: str
    text_sha256: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty or whitespace-only")
        return v

    @field_validator("page_end")
    @classmethod
    def page_end_ge_page_start(
        cls, v: int | None, info: ValidationInfo
    ) -> int | None:
        page_start: Any = info.data.get("page_start")
        if v is not None and page_start is not None and v < page_start:
            raise ValueError("page_end must be >= page_start")
        return v
