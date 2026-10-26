"""Health and integrity checks for NPS/NPC deployments.

The package has three layers that share one topology source (``edges.toml``
and ``clients.toml``):

* :mod:`~nps_ctl.check.links` reads each NPC client's bridge sockets and log
  and reports flapping links, without generating any traffic.
* :mod:`~nps_ctl.check.session` pushes self-verifying payloads through the
  real tunnel to an ephemeral echo service and compares what arrived.
* :mod:`~nps_ctl.check.stress` runs named load profiles on top of a session.

:mod:`~nps_ctl.check.echo_server` and :mod:`~nps_ctl.check.loadgen` are
stdlib-only single files, shipped to remote hosts over SSH.
"""
