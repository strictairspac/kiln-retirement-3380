import re

from pydantic import BaseModel, Field, field_validator

CERTIFICATE_CODE = re.compile(r"[A-Z0-9][A-Z0-9-]{0,23}")
ASSET_CODE = re.compile(r"[A-Z0-9][A-Z0-9-]{0,23}")


class CorrectionInput(BaseModel):
    asset: str = Field(min_length=1, max_length=24)
    certificate_after: str = Field(min_length=1, max_length=48)
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("asset", "certificate_after")
    @classmethod
    def check_code(cls, value):
        value = value.strip()
        if not ASSET_CODE.fullmatch(value):
            raise ValueError("炉号和证书号只允许大写字母、数字及连字符")
        return value

    @field_validator("reason")
    @classmethod
    def check_reason(cls, reason):
        if len(reason.strip()) < 3:
            raise ValueError("更正原因至少需要三个字符")
        return reason.strip()


class RevisionOpen(BaseModel):
    note: str = Field(default="", max_length=200)


class IssueInput(BaseModel):
    note: str = Field(min_length=3, max_length=500)

    @field_validator("note")
    @classmethod
    def check_note(cls, note):
        if len(note.strip()) < 3:
            raise ValueError("签发意见至少需要三个字符")
        return note.strip()


class RevisionEntry(BaseModel):
    id: int
    run_id: int
    asset: str
    certificate_before: str
    certificate_after: str
    reason: str
    status: str
    base_serial: int
    actor: str
    created_at: int
    opened_at: int | None
    opened_by: str | None
    signed_at: int | None
    signed_by: str | None
    sign_note: str | None
    returned_at: int | None
    return_note: str | None
    issue_id: int | None
    issue_serial: int | None
    snapshot: dict | None


class IssueEntry(BaseModel):
    id: int
    run_id: int
    version: int
    digest: str
    snapshot: dict
    actor: str
    note: str
    created_at: int


class CertificateBundle(BaseModel):
    run_id: int
    # 最后一次签发的原件；首次更正待签期间仍是批次原始结果。
    current_issue: IssueEntry | None
    pending_serial: int | None
    pending_revisions: list[RevisionEntry]
    revisions: list[RevisionEntry]
    issues: list[IssueEntry]
