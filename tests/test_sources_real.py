from __future__ import annotations


def test_source_baselines_constant_removed() -> None:
    import axiom.studio.sources as sources

    assert not hasattr(sources, "SOURCE_BASELINES")
