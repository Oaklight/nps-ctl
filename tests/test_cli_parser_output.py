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


def test_tunnel_status_is_json_capable_and_requires_config():
    args = create_parser().parse_args(["tunnel", "status"])

    assert args.json_capable is True
    assert args.requires_config is True


def test_tunnel_status_accepts_edge_and_all():
    args = create_parser().parse_args(["tunnel", "status", "-e", "edge-a"])
    assert args.edge == "edge-a"

    args = create_parser().parse_args(["tunnel", "status", "-a"])
    assert args.all is True


def test_tunnel_type_filters_accept_mixproxy():
    args = create_parser().parse_args(["tunnel", "list", "-t", "mixProxy"])
    assert args.type == "mixProxy"

    args = create_parser().parse_args(
        ["tunnel", "del", "-p", "1080", "-t", "mixProxy", "-a", "-y"]
    )
    assert args.type == "mixProxy"

    args = create_parser().parse_args(
        [
            "tunnel",
            "edit",
            "-p",
            "1080",
            "-t",
            "mixProxy",
            "-a",
            "--new-target",
            "127.0.0.1:1080",
        ]
    )
    assert args.type == "mixProxy"


def test_edge_status_accepts_edge_and_all():
    args = create_parser().parse_args(["edge", "status", "-e", "edge-a"])
    assert args.edge == "edge-a"

    args = create_parser().parse_args(["edge", "status", "--all"])
    assert args.all is True
