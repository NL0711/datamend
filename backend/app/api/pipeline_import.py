"""Import step: bring bulk station data in from a user-supplied Amazon S3 link or a Kaggle dataset (routes are added by the import work)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/pipeline", tags=["pipeline-import"])
