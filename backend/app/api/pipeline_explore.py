"""Explore step: dynamic validation tables, the assistant, auto-cleaning proposals, stations with locations, and the model card (routes are added by the explore work)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/pipeline", tags=["pipeline-explore"])
