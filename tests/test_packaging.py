"""Package data that must ship with every install."""

from __future__ import annotations

from importlib import resources

import neon_pursuit


def test_bundled_resources_exist() -> None:
    root = resources.files("neon_pursuit")
    assert root.joinpath("py.typed").is_file()
    assert root.joinpath("ai", "fuzzy", "tuned.json").is_file()
    for font in ("Orbitron.ttf", "Rajdhani-Medium.ttf", "Rajdhani-Bold.ttf", "JetBrainsMono.ttf"):
        assert root.joinpath("assets", "fonts", font).is_file(), font


def test_tuned_genomes_load() -> None:
    from neon_pursuit.ai.fuzzy.genome import tuned_genomes

    genomes = tuned_genomes()
    assert set(genomes) == {"survivor", "hunter"}


def test_version_is_consistent() -> None:
    from importlib.metadata import version

    assert neon_pursuit.__version__ == version("neon-pursuit")
