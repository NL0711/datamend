"""Intake: how an upload or a dataset link becomes a run. The routes only translate the typed errors below into HTTP answers.

Owns the input contract (accepted file types, upload options) and the choice of fetcher for a link (a public S3 link is anonymous and never
gets a token; anything else is a Kaggle dataset). The run itself is the Run module's job (``runs.execute_run``).
"""
from __future__ import annotations

from typing import Optional, Tuple

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.validation import kaggle_import, s3_import
from backend.app.validation import runs as svc
from backend.app.validation.ingest import UploadOptions
from backend.app.validation.models import ValidationRun

ACCEPTED_TYPES = ("csv", "json")


class UnsupportedFile(ValueError):
    """The file type is not one intake reads."""


class LinkNeedsToken(Exception):
    """The dataset is private: a Kaggle API token is needed for this one call."""


class LinkRejected(Exception):
    """The link cannot be used (bad link, not public, no usable file, too large); the message says what to do."""


class LinkUnreachable(Exception):
    """The data host could not be reached."""


def upload_options(name: str, profile: str, accumulation_mode: Optional[str] = None, timezone: Optional[str] = None,
                   interval_minutes: Optional[float] = None) -> UploadOptions:
    """The options for a named file; the type comes from its extension."""
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ACCEPTED_TYPES:
        raise UnsupportedFile(f"unsupported file type .{ext}: use .csv or .json (parquet is NOT IMPLEMENTED)")
    return UploadOptions(profile=profile, fmt=ext, accumulation_mode=accumulation_mode or None, timezone=timezone or None,
                         interval_minutes=interval_minutes)


async def fetch_link(url: str, token: Optional[str] = None, file: Optional[str] = None) -> Tuple[str, bytes]:
    """``(file name, bytes)`` of one CSV or JSON file behind a Kaggle dataset link or a public S3 link."""
    try:
        if s3_import.looks_like_s3(url):
            return await s3_import.fetch(url, file)
        return await kaggle_import.fetch(url, token, file)
    except kaggle_import.NeedsToken as e:
        raise LinkNeedsToken(str(e)) from e
    except (kaggle_import.KaggleError, s3_import.S3Error) as e:
        raise LinkRejected(str(e)) from e
    except httpx.HTTPError as e:
        raise LinkUnreachable("Could not reach the data host. Try again later.") from e


async def run_file(session: AsyncSession, content: bytes, name: str, profile: str, accumulation_mode: Optional[str] = None,
                   timezone: Optional[str] = None, interval_minutes: Optional[float] = None, synthetic: bool = False) -> ValidationRun:
    """Validate one file as a run. Raises UnsupportedFile before anything is stored, and runs.RunRejected for a rejected file (stored as a failed run)."""
    opts = upload_options(name, profile, accumulation_mode, timezone, interval_minutes)
    return (await svc.run_upload(session, content, name, opts, synthetic=synthetic)).run
