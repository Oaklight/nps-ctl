"""Tests for CLI edge target resolution."""

from __future__ import annotations

import argparse

from nps_ctl.cli.helpers import resolve_write_edges


def _args(**kwargs) -> argparse.Namespace:
    values = {"edge": None, "all": False}
    values.update(kwargs)
    return argparse.Namespace(**values)


def test_writes_require_explicit_target(capsys):
    targets, code = resolve_write_edges(_args(), ["nps-america", "nps-america2"])

    assert targets is None
    assert code == 2
    out = capsys.readouterr().out
    assert "Configured edges: nps-america, nps-america2" in out


def test_writes_accept_one_edge():
    assert resolve_write_edges(_args(edge="b"), ["a", "b"]) == (["b"], 0)


def test_writes_accept_all_edges():
    assert resolve_write_edges(_args(all=True), ["a", "b"]) == (["a", "b"], 0)


def test_writes_reject_both_targets():
    targets, code = resolve_write_edges(_args(edge="b", all=True), ["a", "b"])

    assert targets is None
    assert code == 2


def test_writes_reject_empty_cluster(capsys):
    targets, code = resolve_write_edges(_args(all=True), [])

    assert targets is None
    assert code == 1
    assert "No edges configured" in capsys.readouterr().out
