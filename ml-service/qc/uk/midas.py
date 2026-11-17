"""Read MIDAS Open daily-rainfall station files and decide what each change between the original and the
current-best record means.

File layout (see ``scripts/download_midas.py`` and ``docs/research/uk-midas-open-daily-rain-qc-flags-and-counts.md``):
``<county>/<station>/qc-version-0/*_qcv-0_<year>.csv`` (originals, kept only where QC changed something) and
``<county>/<station>/qc-version-1/*_qcv-1_<year>.csv`` (current best). BADC-CSV: metadata header lines
``key,G,value``, a line ``data``, the table, a line ``end data``. Columns used: ob_end_time, src_id,
prcp_amt, ob_day_cnt, prcp_amt_q, rec_st_ind, met_domain_name.

UNVERIFIED AGAINST REAL FILES: this reader was written from the documented columns and tested on generated files
that follow the documented layout. Station coordinates are read from a header line ``location,G,<lat>,<lon>`` in
any of a station's files, else from ``<midas>/stations.csv`` (columns station_id,lat,lon). If neither exists the
reader stops with a message instead of guessing. Check this against the first real Devon files.

Categories of a changed record (matched on date, station and message type):
  manual_correction  status 5, estimate 2, query 7: a person corrected a value the neighbour check failed. THE LABEL.
  auto_estimate      status 2, estimate 1: an automatic estimate replacing a placeholder. Not an error label.
  unflagged_change   the amount changed and no status or estimate flag is set. Not an error label.
  other_change       any other changed amount.
  multiday_split     the original was a multi-day total, now split into days. Not an error label.
  flag_only          the amount is unchanged; only flags changed. No effect on values.
  missing_change     value to missing or missing to value.
  unmatched          an original with no current-best record. Counted only.
Only manual_correction is an error label. Every other changed record is excluded from scoring and counted.

Multi-day totals: an original total covering n days gives no daily value for any of its n days (the original
daily series is missing there). A current-best record that is itself a multi-day total is not a daily value in
either series.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

CATEGORIES = ("manual_correction", "auto_estimate", "unflagged_change", "other_change", "multiday_split",
              "flag_only", "missing_change", "unmatched")
LABEL = "manual_correction"
EXCLUDED = ("auto_estimate", "unflagged_change", "other_change", "multiday_split", "missing_change")
CHANGE_TOL = 1e-6
_YEAR = re.compile(r"_qcv-[01]_(\d{4})\.csv$")
KEY = ["date", "station", "domain"]


class MidasError(RuntimeError):
    pass


def read_badc_csv(path: Path) -> Tuple[Dict[str, List[str]], pd.DataFrame]:
    """(metadata, table). Metadata maps a key to the fields after ``G``; the table has the file's column names."""
    meta: Dict[str, List[str]] = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rows = list(csv.reader(f))
    start = next((i for i, r in enumerate(rows) if r and r[0].strip().lower() == "data"), None)
    if start is None:
        raise MidasError(f"{path}: no 'data' line; not a BADC-CSV file")
    for r in rows[:start]:
        if len(r) >= 3 and r[1].strip() == "G":
            meta.setdefault(r[0].strip().lower(), []).append(",".join(x.strip() for x in r[2:]))
    end = next((i for i, r in enumerate(rows) if i > start and r and r[0].strip().lower() == "end data"), len(rows))
    header = [h.strip() for h in rows[start + 1]]
    return meta, pd.DataFrame([r[:len(header)] for r in rows[start + 2:end]], columns=header)


def decode_q(q) -> Dict[str, int]:
    """prcp_amt_q: five digits, marker, estimate, status, query, level (leading zeros are dropped in the file)."""
    try:
        s = str(abs(int(float(q)))).zfill(5)[-5:]
    except (TypeError, ValueError):
        s = "00000"
    return {"marker": int(s[0]), "estimate": int(s[1]), "status": int(s[2]), "query": int(s[3]), "level": int(s[4])}


def _tidy(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    need = ["ob_end_time", "prcp_amt", "prcp_amt_q", "ob_day_cnt"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise MidasError(f"{path}: missing columns {miss}; found {list(df.columns)[:12]}")
    sid = "src_id" if "src_id" in df else "id"
    out = pd.DataFrame({
        "date": pd.to_datetime(df["ob_end_time"], errors="coerce").dt.normalize(),
        "station": df[sid].astype(str).str.strip(),
        "domain": df["met_domain_name"].astype(str).str.strip() if "met_domain_name" in df else "",
        "amount": pd.to_numeric(df["prcp_amt"], errors="coerce"),
        "days": pd.to_numeric(df["ob_day_cnt"], errors="coerce").fillna(1).astype(int),
        "q": pd.to_numeric(df["prcp_amt_q"], errors="coerce").fillna(0).astype(int),
    })
    out = out[out["date"].notna() & (out["station"] != "99999")]        # 99999 = commissioning trial records: ignore
    return out.reset_index(drop=True)


def classify(v0: pd.DataFrame, v1: pd.DataFrame) -> pd.DataFrame:
    """Match originals to current-best records on (date, station, domain) and label every pair.

    One row per original: the original's columns with suffix ``_0``, the matched current-best columns with
    suffix ``_1`` (NaN if unmatched) and ``category``.
    """
    m = v0.merge(v1, on=KEY, how="left", suffixes=("_0", "_1"), indicator=True)
    matched = (m["_merge"] == "both").to_numpy()
    a0, a1 = m["amount_0"].to_numpy(float), m["amount_1"].to_numpy(float)
    d0 = m["days_0"].to_numpy()
    marker0 = np.array([decode_q(q)["marker"] for q in m["q_0"]])
    f1 = [decode_q(q) if ok else None for q, ok in zip(m["q_1"], matched)]
    cat = []
    for i in range(len(m)):
        if not matched[i]:
            cat.append("unmatched")
        elif d0[i] > 1 or marker0[i] in (2, -2):
            cat.append("multiday_split")
        elif np.isnan(a0[i]) != np.isnan(a1[i]):
            cat.append("missing_change")
        elif (np.isnan(a0[i]) and np.isnan(a1[i])) or abs(a0[i] - a1[i]) <= CHANGE_TOL:
            cat.append("flag_only")
        elif f1[i]["status"] == 5 and f1[i]["estimate"] == 2 and f1[i]["query"] == 7:
            cat.append("manual_correction")
        elif f1[i]["status"] == 2 and f1[i]["estimate"] == 1:
            cat.append("auto_estimate")
        elif f1[i]["status"] == 0 and f1[i]["estimate"] == 0:
            cat.append("unflagged_change")
        else:
            cat.append("other_change")
    m["category"] = cat
    return m.drop(columns=["_merge"])


@dataclass
class StationData:
    """Per station and day over the study years, ready for gridding."""
    ids: List[str]
    lat: np.ndarray
    lon: np.ndarray
    daily: pd.DataFrame                # date, station, corrected, original (mm; NaN = no daily value)
    manual: pd.DataFrame               # date, station: hand-corrected (the label)
    excluded: pd.DataFrame             # date, station: changed for another reason
    counts: Dict[str, int] = field(default_factory=dict)
    subset_note: str = ""


def _coords(meta: Dict[str, List[str]]) -> Optional[Tuple[float, float]]:
    for v in meta.get("location", []):
        nums = re.findall(r"-?\d+\.\d+|-?\d+", v)
        if len(nums) >= 2:
            a, b = float(nums[0]), float(nums[1])
            return (a, b) if abs(a) <= 90 else (b, a)
    return None


def load_midas(midas_dir: Path, counties: Iterable[str], years: Iterable[int]) -> StationData:
    """Read every station file of ``counties`` for ``years``. ``midas_dir`` holds the county folders
    (``.../uk-daily-rain-obs/dataset-version-202607``)."""
    midas_dir, years = Path(midas_dir), set(int(y) for y in years)
    extra: Dict[str, Tuple[float, float]] = {}
    sfile = midas_dir / "stations.csv"
    if sfile.is_file():
        s = pd.read_csv(sfile, dtype={"station_id": str})
        extra = {r.station_id.strip(): (float(r.lat), float(r.lon)) for r in s.itertuples()}
    v0s, v1s, coord = [], [], {}
    for county in counties:
        cdir = midas_dir / county
        if not cdir.is_dir():
            raise MidasError(f"{cdir} not found. Download it with: python scripts/download_midas.py --county {county} --mode full")
        for sdir in sorted(p for p in cdir.iterdir() if p.is_dir()):
            for ver, bucket in (("qc-version-1", v1s), ("qc-version-0", v0s)):
                vdir = sdir / ver
                for f in (sorted(vdir.glob("*.csv")) if vdir.is_dir() else []):
                    y = _YEAR.search(f.name)
                    if not y or int(y.group(1)) not in years:
                        continue
                    meta, df = read_badc_csv(f)
                    t = _tidy(df, f)
                    bucket.append(t)
                    c = _coords(meta)
                    if c:
                        for sid in t["station"].unique():
                            coord.setdefault(sid, c)
    if not v1s:
        raise MidasError(f"no qc-version-1 files for the study years under {midas_dir}; download with --mode full "
                         "(the default pairs mode is enough to count changes but not to grid)")
    v1 = pd.concat(v1s, ignore_index=True).drop_duplicates(KEY, keep="last")
    v0 = pd.concat(v0s, ignore_index=True).drop_duplicates(KEY, keep="last") if v0s else v1.iloc[0:0].copy()
    coord = {**extra, **coord}
    ids = sorted(v1["station"].unique())
    missing = [s for s in ids if s not in coord]
    if missing:
        raise MidasError(f"no coordinates for {len(missing)} stations (e.g. {missing[:3]}). Put them in {sfile} "
                         "(columns station_id,lat,lon) or check the header format; see qc/uk/midas.py")
    pairs = classify(v0, v1)
    counts = {c: int((pairs["category"] == c).sum()) for c in CATEGORIES}
    counts.update({"current_best_records": int(len(v1)), "originals_kept": int(len(v0))})

    daily = v1[v1["days"] == 1].drop_duplicates(["date", "station"], keep="last").copy()
    daily = daily.rename(columns={"amount": "corrected"})[["date", "station", "domain", "corrected"]]
    daily["original"] = daily["corrected"]
    kept = pairs[pairs["category"] != "unmatched"]
    single = kept[kept["days_0"] == 1].drop_duplicates(["date", "station"], keep="last").set_index(["date", "station"])["amount_0"]
    idx = pd.MultiIndex.from_frame(daily[["date", "station"]])
    hit = idx.isin(single.index)
    daily.loc[hit, "original"] = single.loc[idx[hit]].to_numpy(float)
    gone = {(r.date - pd.Timedelta(days=k), r.station) for r in kept[kept["days_0"] > 1].itertuples()
            for k in range(int(r.days_0))}
    if gone:
        daily.loc[idx.isin(list(gone)), "original"] = np.nan
    man = pairs[pairs["category"] == LABEL][["date", "station"]].drop_duplicates()
    excl = pairs[pairs["category"].isin(EXCLUDED)][["date", "station"]].drop_duplicates()
    return StationData(ids, np.array([coord[s][0] for s in ids]), np.array([coord[s][1] for s in ids]),
                       daily[["date", "station", "corrected", "original"]].reset_index(drop=True), man, excl, counts,
                       "subset: only station-years where QC changed something have a qc-version-0 file, and only the "
                       "downloaded counties are included; originals overwritten by station correction messages are missing")
