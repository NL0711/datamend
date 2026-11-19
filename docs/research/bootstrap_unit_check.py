"""Coverage of bootstrap intervals for a recall metric computed over Y years x R regions.
Generated data only: detection probability p[y,r] = logistic(mu + a_y + b_r + c_yr); counts ~ Binomial(n, p).
a_y shared across regions (a wet or dry monsoon year), b_r a region characteristic, c_yr local noise.
Two inferential targets: E1 the same 8 regions with new years and new fault draws; E2 a super-population of regions."""
import sys
import numpy as np

rng = np.random.default_rng(1)
B, REPS = 400, 1200
lg = lambda x: 1 / (1 + np.exp(-x))


def draw(Y, R, n, mu, sy, sr, sc, b=None):
    a = rng.normal(0, sy, (Y, 1))
    c = rng.normal(0, sc, (Y, R))
    if b is None:
        b = rng.normal(0, sr, (1, R))
    p = lg(mu + a + b + c)
    k = rng.binomial(n, p)
    return k, n, p


def intervals(k, n):
    Y, R = k.shape
    rate = k / n
    phat = rate.mean()
    out = {}
    # event-level iid (what qc/metrics.py does for recall): events treated as independent Bernoulli draws
    N = n * Y * R
    boot = rng.binomial(N, phat, B) / N
    out["event_iid"] = np.percentile(boot, [2.5, 97.5])
    # whole years, regions fixed
    iy = rng.integers(0, Y, (B, Y))
    out["years"] = np.percentile(rate[iy].mean(axis=(1, 2)), [2.5, 97.5])
    # whole regions, years fixed
    ir = rng.integers(0, R, (B, R))
    out["regions"] = np.percentile(rate[:, ir].mean(axis=(0, 2)), [2.5, 97.5])
    # crossed (pigeonhole): years and regions resampled independently
    cells = rate[iy[:, :, None], ir[:, None, :]]
    out["crossed"] = np.percentile(cells.mean(axis=(1, 2)), [2.5, 97.5])
    return phat, out


def experiment(Y, R, n, mu, sy, sr, sc, fixed_regions):
    big = 400000
    if fixed_regions:
        b = rng.normal(0, sr, (1, R))
        a = rng.normal(0, sy, (big, 1)); c = rng.normal(0, sc, (big, R))
        target = lg(mu + a + b + c).mean()
    else:
        b = None
        a = rng.normal(0, sy, (big, 1)); bb = rng.normal(0, sr, (big, R)); c = rng.normal(0, sc, (big, R))
        target = lg(mu + a + bb + c).mean()
    cover = {m: 0 for m in ("event_iid", "years", "regions", "crossed")}
    width = {m: 0.0 for m in cover}
    for _ in range(REPS):
        k, nn, _ = draw(Y, R, n, mu, sy, sr, sc, b)
        _, iv = intervals(k, nn)
        for m, (lo, hi) in iv.items():
            cover[m] += (lo <= target <= hi)
            width[m] += hi - lo
    return {m: (cover[m] / REPS, width[m] / REPS) for m in cover}


settings = [("moderate year effect", 0.30, 0.8, 0.30), ("strong year effect", 0.70, 0.8, 0.30), ("weak year effect", 0.10, 0.8, 0.30)]
for label, sy, sr, sc in settings:
    for Y in (5, 8):
        for fixed in (True, False):
            r = experiment(Y, 8, 200, 0.8, sy, sr, sc, fixed)
            tgt = "same 8 regions, new years" if fixed else "super-population of regions"
            print(f"[{label}] Y={Y} R=8 target: {tgt}")
            for m, (cv, w) in r.items():
                print(f"    {m:10s} coverage {cv:5.1%}  mean width {w:.3f}")
        sys.stdout.flush()
