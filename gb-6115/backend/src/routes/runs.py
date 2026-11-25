from fastapi import APIRouter, Depends, HTTPException, Response

from src.config.resources import engine
from src.constants.job_state import JobState
from src.controllers.access import identity, operator, reviewer
from src.controllers.workbench import (
    certificate_bundle, correction, issue_revision, new_review, open_revision,
)
from src.schemas.certificates import CertificateBundle, CorrectionInput, IssueInput
from src.schemas.reviews import ReviewEntry, ReviewInput
from src.schemas.runs import RunEntry
from src.services import certificates, reviews, runs
from src.utils.serial import canonical_json

router = APIRouter(prefix="/runs", tags=["Execution"])


@router.get("", response_model=list[RunEntry], dependencies=[Depends(identity)])
def list_runs():
    with engine.connect() as db:
        return runs.list_entries(db)


@router.get("/{run_id}", response_model=RunEntry, dependencies=[Depends(identity)])
def run_detail(run_id: int):
    with engine.connect() as db:
        return runs.get(db, run_id)


@router.get("/{run_id}/review", response_model=ReviewEntry | None, dependencies=[Depends(identity)])
def review_detail(run_id: int):
    with engine.connect() as db:
        runs.get(db, run_id)
        return reviews.get(db, run_id)


@router.post("/{run_id}/review", response_model=ReviewEntry, status_code=201)
def sign(run_id: int, form: ReviewInput, user=Depends(reviewer)):
    return new_review(run_id, form, user)


@router.get("/{run_id}/certificates", response_model=CertificateBundle,
            dependencies=[Depends(identity)])
def certificate_detail(run_id: int):
    return certificate_bundle(run_id)


@router.post("/{run_id}/certificates/corrections", response_model=CertificateBundle,
             status_code=201)
def add_correction(run_id: int, form: CorrectionInput, user=Depends(operator)):
    return correction(run_id, form, user)


@router.post("/{run_id}/certificates/open", response_model=CertificateBundle)
def open_correction(run_id: int, user=Depends(reviewer)):
    return open_revision(run_id, user)


@router.post("/{run_id}/certificates/issue", response_model=CertificateBundle)
def issue_correction(run_id: int, form: IssueInput, user=Depends(reviewer)):
    return issue_revision(run_id, form, user)


@router.get("/{run_id}/export", dependencies=[Depends(identity)])
def export(run_id: int):
    with engine.connect() as db:
        run = runs.get(db, run_id)
        if run["status"] != JobState.DONE:
            raise HTTPException(409, "没有可导出的执行结果")
        run["review"] = reviews.get(db, run_id)
        run["certificates"] = certificates.bundle(db, run_id)
    return Response(canonical_json(run), media_type="application/json", headers={
        "Content-Disposition": f"attachment; filename=evidence-{run_id}.json",
    })
