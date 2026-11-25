from time import time

from fastapi import HTTPException
from sqlalchemy import and_, desc, insert, select, update
from sqlalchemy.exc import IntegrityError

from src.constants.job_state import JobState
from src.models.certificate_issues import certificate_issues
from src.models.certificates import certificate_revisions
from src.models.runs import runs
from src.utils.serial import content_digest
from . import audit, runs as run_service

PENDING = "pending"
ISSUED = "issued"
RETURNED = "returned"


def _run_locked(db, run_id):
    """锁定批次行，保证同一底稿上的更正提交与签字切换串行化。

    PostgreSQL 用行锁串行化同一批次的并发更正；SQLite 写事务本身即库级互斥。
    """
    statement = select(runs).where(runs.c.id == run_id).with_for_update()
    run = db.execute(statement).mappings().first()
    if run is None:
        raise HTTPException(404, "执行批次不存在")
    if run["status"] != JobState.DONE:
        raise HTTPException(409, "批次执行成功后才能办理证书更正")
    return dict(run)


def _certificate_index(run):
    """当前批次原件的炉体 -> 证书号映射，只处理真正写出退役证书的炉体。"""
    index = {}
    for row in (run["result"] or {}).get("rows", []):
        certificate = row.get("退役证书")
        if certificate is not None:
            index[row["炉体"]] = certificate
    return index


def _pending(db, run_id):
    return db.execute(
        select(certificate_revisions)
        .where(and_(certificate_revisions.c.run_id == run_id,
                    certificate_revisions.c.status == PENDING))
        .order_by(certificate_revisions.c.id)
    ).mappings().all()


def _next_serial(db, run_id):
    serial = db.execute(
        select(certificate_revisions.c.base_serial)
        .where(certificate_revisions.c.run_id == run_id)
        .order_by(desc(certificate_revisions.c.base_serial)).limit(1)
    ).scalar_one_or_none()
    return (serial or 0) + 1

def _effective_certificate(db, run, asset, original):
    """叠加已签发更正，得到该炉体当前最后签发的证书号。"""
    rows = db.execute(
        select(certificate_revisions.c.certificate_after)
        .where(and_(certificate_revisions.c.run_id == run["id"],
                    certificate_revisions.c.asset == asset,
                    certificate_revisions.c.status == ISSUED))
        .order_by(certificate_revisions.c.issue_serial, certificate_revisions.c.id)
    ).scalars().all()
    return rows[-1] if rows else original


def _build_snapshot(db, run):
    """按最后签发原件 + 待签更正之外的已签发件，生成整批证书快照。"""
    originals = _certificate_index(run)
    rows = []
    for row in (run["result"] or {}).get("rows", []):
        asset = row["炉体"]
        certificate = row.get("退役证书")
        effective = _effective_certificate(db, run, asset, certificate) if certificate is not None else None
        rows.append({**row, "退役证书": effective, "原件证书号": certificate})
    result = {**(run["result"] or {}), "rows": rows}
    return {"run_id": run["id"], "rows": rows, "summary": result.get("summary"),
            "metrics": result.get("metrics")}


def submit_correction(db, run_id, data, actor):
    run = _run_locked(db, run_id)
    originals = _certificate_index(run)
    if data.asset not in originals:
        raise HTTPException(422, "该炉体没有可更正的退役证书（已撤销退役或炉号不存在）")

    pending_rows = _pending(db, run_id)
    effective_before = _effective_certificate(db, run, data.asset, originals[data.asset])

    # 同一份待签稿里，同一炉体只允许一条更正；后到方必须重新核对后再入稿。
    if any(row["asset"] == data.asset for row in pending_rows):
        raise HTTPException(
            409, f"炉体 {data.asset} 已有待签更正，请取回最新待签稿重新核对后再提交"
        )
    if data.certificate_after == effective_before:
        raise HTTPException(422, "新证书号与当前最后签发的原件一致，无需更正")
    # 更正后的证书号不得与同批其他炉体的现行证书号冲突。
    taken = {
        _effective_certificate(db, run, asset, certificate)
        for asset, certificate in originals.items() if asset != data.asset
    }
    taken |= {row["certificate_after"] for row in pending_rows if row["asset"] != data.asset}
    if data.certificate_after in taken:
        raise HTTPException(422, "新证书号与同批次其他炉体的证书号重复")

    now = int(time())
    serial = _next_serial(db, run_id)
    # 复核员已打开过待签稿：新入稿使旧稿失效，已落的签字随旧稿退回并留存。
    for row in pending_rows:
        if row["opened_at"] is not None or row["signed_at"] is not None:
            db.execute(update(certificate_revisions)
                       .where(certificate_revisions.c.id == row["id"])
                       .values(status=RETURNED, returned_at=now,
                               return_note=f"炉体 {data.asset} 新更正入稿，原待签稿退回重签"))
    try:
        db.execute(insert(certificate_revisions).values(
            run_id=run_id, asset=data.asset,
            certificate_before=effective_before, certificate_after=data.certificate_after,
            reason=data.reason, status=PENDING, base_serial=serial,
            actor=actor, created_at=now,
        ))
    except IntegrityError as exc:
        # 并发下另一事务已为同一炉体入稿，唯一索引兜底；后到方需重新核对。
        raise HTTPException(
            409, f"炉体 {data.asset} 的更正刚被他人入稿，请取回最新待签稿重新核对后再提交"
        ) from exc
    audit.record(db, "certificate_correction", actor, "run", run_id)
    return bundle(db, run_id)


def open_pending(db, run_id, actor):
    run = _run_locked(db, run_id)
    now = int(time())
    pending_rows = _pending(db, run_id)
    if not pending_rows:
        raise HTTPException(409, "当前没有待签的更正稿")
    ids = [row["id"] for row in pending_rows]
    db.execute(update(certificate_revisions)
               .where(and_(certificate_revisions.c.id.in_(ids),
                           certificate_revisions.c.opened_at.is_(None)))
               .values(opened_at=now, opened_by=actor))
    audit.record(db, "certificate_open", actor, "run", run_id)
    return bundle(db, run_id)


def sign_issue(db, run_id, data, actor):
    run = _run_locked(db, run_id)
    pending_rows = _pending(db, run_id)
    if not pending_rows:
        raise HTTPException(409, "当前没有待签的更正稿，若旧稿已被新入更正退回请重新打开")
    now = int(time())
    # 安全兜底：待签记录若在打开后被新入稿退回，则不能再签字，必须重新打开最新稿。
    if any(row["returned_at"] is not None for row in pending_rows):
        raise HTTPException(409, "待签稿已被新入的更正退回，请重新打开最新待签稿")

    latest_version = db.execute(
        select(certificate_issues.c.version).where(certificate_issues.c.run_id == run_id)
        .order_by(desc(certificate_issues.c.version)).limit(1)
    ).scalar_one_or_none()
    version = (latest_version or 0) + 1
    # 先按已签发更正生成最后签发原件，再叠加本份待签稿；签字后一次性切换。
    base_snapshot = _build_snapshot(db, run)
    snapshot = _apply_pending(base_snapshot, pending_rows)
    digest = content_digest(snapshot)
    result = db.execute(insert(certificate_issues).values(
        run_id=run_id, version=version, digest=digest, snapshot=snapshot,
        actor=actor, note=data.note, created_at=now,
    ))
    issue_id = result.inserted_primary_key[0]
    db.execute(update(certificate_revisions)
               .where(certificate_revisions.c.id.in_([row["id"] for row in pending_rows]))
               .values(status=ISSUED, signed_at=now, signed_by=actor, sign_note=data.note,
                       issue_id=issue_id, issue_serial=version, snapshot=snapshot))
    audit.record(db, "certificate_issue", actor, "run", run_id)
    return bundle(db, run_id)


def _apply_pending(snapshot, pending_rows):
    pending = {row["asset"]: row["certificate_after"] for row in pending_rows}
    rows = []
    for row in snapshot["rows"]:
        updated = dict(row)
        if row["炉体"] in pending:
            updated["退役证书"] = pending[row["炉体"]]
        rows.append(updated)
    return {**snapshot, "rows": rows}


def bundle(db, run_id):
    run = run_service.get(db, run_id)
    revisions = [dict(row) for row in db.execute(
        select(certificate_revisions).where(certificate_revisions.c.run_id == run_id)
        .order_by(certificate_revisions.c.id)
    ).mappings().all()]
    issues = [dict(row) for row in db.execute(
        select(certificate_issues).where(certificate_issues.c.run_id == run_id)
        .order_by(certificate_issues.c.version)
    ).mappings().all()]
    pending_rows = [row for row in revisions if row["status"] == PENDING]
    return {
        "run_id": run_id,
        "current_issue": issues[-1] if issues else None,
        "pending_serial": max((row["base_serial"] for row in pending_rows), default=None),
        "pending_revisions": pending_rows,
        "revisions": revisions,
        "issues": issues,
    }
