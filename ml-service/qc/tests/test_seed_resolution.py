"""Every subcommand that takes --seed must follow train.seeds[0] of the config when --seed is not given,
so a run trained with seeds [42, ...] never silently looks for seed-0 scores."""
import pytest

from qc import __main__ as m

SEED_COMMANDS = {
    "cross-scale": [], "regions-report": [], "cross-scale-test": [], "paper": [], "ablate": [], "calibrate": [],
    "set-budgets": ["--final", "1.0", "--review", "5.0"],
}


@pytest.mark.parametrize("cmd", sorted(SEED_COMMANDS))
def test_default_seed_follows_config(cmd, monkeypatch):
    seen = {}
    monkeypatch.setitem(m.COMMANDS, cmd, lambda cfg, args: seen.setdefault("seed", args.seed) and 0 or 0)
    rc = m.main([cmd, *SEED_COMMANDS[cmd], "--set", "train.seeds=[42,43,44]"])
    assert rc == 0 and seen["seed"] == 42


@pytest.mark.parametrize("cmd", sorted(SEED_COMMANDS))
def test_explicit_seed_wins(cmd, monkeypatch):
    seen = {}
    monkeypatch.setitem(m.COMMANDS, cmd, lambda cfg, args: seen.setdefault("seed", args.seed) and 0 or 0)
    m.main([cmd, *SEED_COMMANDS[cmd], "--seed", "7", "--set", "train.seeds=[42,43,44]"])
    assert seen["seed"] == 7
