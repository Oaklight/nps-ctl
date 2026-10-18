"""Tests for global output flags on the CLI parser."""

from __future__ import annotations

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
