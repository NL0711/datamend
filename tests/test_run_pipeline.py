"""The Run module (runs.execute_run): one pipeline for every input source. Generated data only. A throwaway SQLite file (see conftest)."""
from datetime import date, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from backend.app.db.database import async_session_factory
from backend.app.validation import runs as svc
from backend.app.validation.ingest import InputRejected, ParsedInput
from backend.app.validation.models import Explanation, Review, ValidationCheckHit, ValidationResult, ValidationRun
from backend.app.validation.records import DailyTotal


@pytest_asyncio.fixture(autouse=True)
async def _clean_runs():
    async with async_session_factory() as s:
        for m in (Review, Explanation, ValidationCheckHit, ValidationResult, ValidationRun):
            await s.execute(delete(m))
        await s.commit()
    yield


def totals(n: int = 12, station: str = "S1", start: date = date(2026, 7, 1), mm: float = 3.0):
    return [DailyTotal(source="test", station_id=station, day=start + timedelta(days=i), mm=mm + (i % 3), row_ref=i + 1, units_confirmed=True)
            for i in range(n)]


def spec(**kw):
    base = dict(profile="daily", source="upload", label="t.csv", settings=svc.check_settings("daily", None, None))
    base.update(kw)
    return svc.RunSpec(**base)


async def count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_execute_run_stores_a_completed_run_and_returns_a_result():
    async with async_session_factory() as s:
        res = await svc.execute_run(s, spec(input_sha256="abc"), lambda: ParsedInput("daily", totals()))
        assert res.run.status == "completed" and res.run.n_rows == 12 and res.run.n_stations == 1
        assert res.run.input_sha256 == "abc" and res.run.duration_ms is not None
        assert set(res.hits) == {str(i) for i in range(1, 13)}          # one entry per row, keyed by the stored row_ref
        assert await count(s, ValidationResult) == 12


@pytest.mark.asyncio
async def test_a_loader_rejection_is_stored_as_a_failed_run_and_raised_with_its_id():
    def load():
        raise InputRejected("no usable rows")
    async with async_session_factory() as s:
        with pytest.raises(svc.RunRejected) as ei:
            await svc.execute_run(s, spec(), load)
        assert isinstance(ei.value, InputRejected) and "no usable rows" in str(ei.value)
        failed = await s.get(ValidationRun, ei.value.run_id)
        assert failed.status == "failed" and failed.error == "no usable rows" and await count(s, ValidationResult) == 0


@pytest.mark.asyncio
async def test_loader_may_supply_the_input_hash():
    async with async_session_factory() as s:
        res = await svc.execute_run(s, spec(), lambda: ParsedInput("daily", totals(), input_sha256="from-loader"))
        assert res.run.input_sha256 == "from-loader"


@pytest.mark.asyncio
async def test_replaces_rain_day_rescores_one_open_run_in_place_and_closes_older_ones():
    async with async_session_factory() as s:
        live = dict(profile="daily", source="live")
        a = await svc.execute_run(s, spec(replaces_rain_day="2026-07-02", **live), lambda: ParsedInput("daily", totals(5)))
        b = await svc.execute_run(s, spec(replaces_rain_day="2026-07-02", **live), lambda: ParsedInput("daily", totals(8)))
        assert a.run.id == b.run.id and b.run.status == "open" and b.run.n_rows == 8
        assert await count(s, ValidationResult) == 8                   # replaced, not appended
        c = await svc.execute_run(s, spec(replaces_rain_day="2026-07-03", **live), lambda: ParsedInput("daily", totals(2)))
        assert c.run.id != a.run.id and c.run.status == "open"
        assert (await s.get(ValidationRun, a.run.id)).status == "completed"
