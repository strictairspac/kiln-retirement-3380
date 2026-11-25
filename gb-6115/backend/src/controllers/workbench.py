from redis.exceptions import RedisError
from src.config.resources import cache, engine
from src.services import cases, certificates, runs, reviews


def new_case(data, user):
    with engine.begin() as db:
        return cases.create(db, data, user["username"])


def new_run(case_id, data, user):
    with engine.begin() as db:
        run = runs.enqueue(db, case_id, data.parameter, user["username"])
    try:
        cache.lpush("workbench:wake", str(run["id"]))
        cache.ltrim("workbench:wake", 0, 99)
    except RedisError:
        # The database holds the durable queue. The worker also polls it.
        pass
    return run


def new_review(run_id, data, user):
    with engine.begin() as db:
        return reviews.sign(db, run_id, data, user["username"])


def correction(run_id, data, user):
    with engine.begin() as db:
        return certificates.submit_correction(db, run_id, data, user["username"])


def open_revision(run_id, user):
    with engine.begin() as db:
        return certificates.open_pending(db, run_id, user["username"])


def issue_revision(run_id, data, user):
    with engine.begin() as db:
        return certificates.sign_issue(db, run_id, data, user["username"])


def certificate_bundle(run_id):
    with engine.connect() as db:
        return certificates.bundle(db, run_id)
