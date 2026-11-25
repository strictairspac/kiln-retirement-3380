from sqlalchemy import JSON, BigInteger, Column, ForeignKey, Integer, String, Table
from .base import metadata


# 历次签发件：每次更正签字后生成新版本，原件明细与签字永久留存，不覆盖不删除。
certificate_issues = Table(
    "certificate_issues", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("version", Integer, nullable=False),
    Column("digest", String(64), nullable=False),
    Column("snapshot", JSON, nullable=False),
    Column("actor", String(48), nullable=False),
    Column("note", String(500), nullable=False),
    Column("created_at", BigInteger, nullable=False),
)
