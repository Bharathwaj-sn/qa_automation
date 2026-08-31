from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ValidationSQLCreate(BaseModel):
    test_case_id: str
    target_table: str
    payor: str
    file_type: str
    generated_sql: str
    genie_space_id: str
    conversation_id: str
    message_id: str


class ValidationSQL(ValidationSQLCreate):
    created_at: datetime
    status: str = "SAVED"