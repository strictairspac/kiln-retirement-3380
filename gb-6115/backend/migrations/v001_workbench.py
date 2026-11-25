from src.models import (  # noqa: F401
    audit,
    cases,
    certificate_issues,
    certificates,
    reviews,
    runs,
    users,
)
from src.models.base import metadata


def upgrade(connection):
    # Version 1 is additive and fully declarative.
    metadata.create_all(connection)
