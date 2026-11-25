from sqlalchemy import JSON, BigInteger, Column, ForeignKey, Index, Integer, String, Table, text
from .base import metadata


# 证书更正稿：同一批次的每次更正入稿都留存，待签稿签署后一次性切换为签发件。
certificate_revisions = Table(
    "certificate_revisions", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", ForeignKey("runs.id"), nullable=False, index=True),
    Column("asset", String(24), nullable=False),
    Column("certificate_before", String(48), nullable=False),
    Column("certificate_after", String(48), nullable=False),
    Column("reason", String(300), nullable=False),
    Column("status", String(16), nullable=False, index=True),
    # 更正提交时所依据的待签代次：两人同拿一份底稿时，代次靠后的同炉体更正需重新核对。
    Column("base_serial", Integer, nullable=False),
    Column("actor", String(48), nullable=False),
    Column("created_at", BigInteger, nullable=False),
    # 复核员打开待签稿的时刻；打开后若又有更正入稿，旧稿签字即被退回。
    Column("opened_at", BigInteger, nullable=True),
    Column("opened_by", String(48), nullable=True),
    Column("signed_at", BigInteger, nullable=True),
    Column("signed_by", String(48), nullable=True),
    Column("sign_note", String(500), nullable=True),
    # 待签稿被新入稿顶下时保留退回原因，签字记录一并留存。
    Column("returned_at", BigInteger, nullable=True),
    Column("return_note", String(300), nullable=True),
    Column("issue_id", Integer, ForeignKey("certificate_issues.id"), nullable=True),
    Column("issue_serial", Integer, nullable=True),
    Column("snapshot", JSON(none_as_null=True), nullable=True),
    # 同一炉体同时只能有一条待签更正；不同炉体可并存于同一份待签稿。
    Index("uq_revision_pending_asset", "run_id", "asset", unique=True,
          postgresql_where=text("status = 'pending'"),
          sqlite_where=text("status = 'pending'")),
)
