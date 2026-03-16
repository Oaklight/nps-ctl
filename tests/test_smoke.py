"""Smoke tests to verify the package loads correctly."""


def test_import_package():
    """Verify the top-level package is importable."""
    import nps_ctl

    assert hasattr(nps_ctl, "__name__")


def test_import_base():
    """Verify the NPSClient class is importable."""
    from nps_ctl.base import NPSClient

    assert NPSClient is not None


def test_import_cluster():
    """Verify the NPSCluster class is importable."""
    from nps_ctl.cluster import NPSCluster

    assert NPSCluster is not None


def test_import_cli():
    """Verify the CLI module is importable."""
    from nps_ctl.cli import main

    assert callable(main)


def test_import_types():
    """Verify TypedDict types are importable."""
    from nps_ctl.types import ClientInfo, HostInfo, TunnelInfo

    assert ClientInfo is not None
    assert TunnelInfo is not None
    assert HostInfo is not None
