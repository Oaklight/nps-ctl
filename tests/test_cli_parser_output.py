"""Tests for global output flags on the CLI parser."""

from __future__ import annotations

import sys

from nps_ctl.cli import main
from nps_ctl.cli.parser import create_parser


def test_json_flag_after_subcommand():
    args = create_parser().parse_args(["edge", "list", "--json"])

    assert args.json is True


def test_json_flag_before_subcommand():
    args = create_parser().parse_args(["--json", "edge", "list"])

    assert args.json is True


def test_json_defaults_to_false():
    args = create_parser().parse_args(["edge", "list"])

    assert args.json is False


def test_no_color_flag_after_subcommand():
    args = create_parser().parse_args(["host", "list", "--no-color"])

    assert args.no_color is True


def test_json_capable_commands_are_marked():
    assert create_parser().parse_args(["edge", "list"]).json_capable is True

    mutation = create_parser().parse_args(["host", "del", "-d", "x", "-a"])
    assert getattr(mutation, "json_capable", False) is False


def test_global_json_rejected_for_non_json_command(monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["nps-ctl", "--json", "host", "del", "-d", "x", "-a", "-y"],
    )

    assert main() == 2
    assert "--json is not supported for this command" in capsys.readouterr().err
