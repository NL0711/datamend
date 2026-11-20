"""Create a messy 'production' file and a clean 'training' file for the demo.

    python -m datamend_mcp.examples.make_sample_data
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    ws = Path(os.environ.get("DATAMEND_MCP_WORKSPACE", "mcp_workspace")).resolve()
    ws.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    n = 1000

    train = pd.DataFrame(
        {
            "age": rng.integers(21, 65, n),
            "income": rng.normal(60_000, 12_000, n).round(0),
            "city": rng.choice(["Mumbai", "Pune", "Nashik", "Nagpur"], n),
            "plan": rng.choice(["basic", "plus", "pro"], n, p=[0.5, 0.3, 0.2]),
        }
    )

    prod = pd.DataFrame(
        {
            "age": rng.integers(21, 65, n).astype(float),
            "income": rng.normal(78_000, 15_000, n).round(0),  # drifted upwards
            "city": rng.choice(["Mumbai", "Pune", "Nashik", "Nagpur"], n),
            "plan": rng.choice(["basic", "plus", "pro"], n, p=[0.3, 0.3, 0.4]),  # drifted mix
        }
    )
    prod.loc[rng.choice(n, 80, replace=False), "age"] = np.nan          # nulls
    prod.loc[rng.choice(n, 15, replace=False), "income"] = 9_999_999    # outliers
    prod["city"] = prod["city"].where(rng.random(n) > 0.1, "  " + prod["city"] + " ")  # whitespace
    prod = pd.concat([prod, prod.sample(40, random_state=1)], ignore_index=True)  # duplicates

    train.to_csv(ws / "train.csv", index=False)
    prod.to_csv(ws / "prod.csv", index=False)
    print(f"Wrote {ws / 'train.csv'} and {ws / 'prod.csv'}")


if __name__ == "__main__":
    main()
