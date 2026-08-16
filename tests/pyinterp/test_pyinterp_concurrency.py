from __future__ import absolute_import

import sys
import threading

import pygo_plugin
from pygo_plugin import pyinterp

from .test_pyinterp import _make_client


# Concurrency was never exercised by the rest of tests/pyinterp/: each
# existing test uses exactly one client/connection from exactly one thread.
# These tests instead ask whether a plugin subprocess (and the connection
# into it) is actually safe under concurrent host-side use, or just happened
# to work by accident because nothing tried harder. They anticipate a
# plausible real usage pattern (a host with multiple worker threads sharing
# one plugin, or spinning up several plugins at once), not a hypothetical one.


def test_pyinterp_concurrent_calls_single_connection():
    # Multiple host threads issuing calls concurrently over ONE RPyC
    # connection into ONE plugin subprocess. RPyC's Connection is not
    # documented as thread-safe by default (no BgServingThread is set up
    # here), so this confirms pygo_plugin's usage of it holds up under
    # concurrent access rather than assuming it does.
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    # A remote counter guarded by its own (remote) lock. If concurrent
    # calls over the connection ever got corrupted or interleaved
    # (responses delivered to the wrong caller, requests dropped), this
    # would show up as lost or duplicate increments.
    conn.execute('\n'.join([
        'import threading',
        'counter = {"n": 0}',
        'lock = threading.Lock()',
        'def bump():',
        '    with lock:',
        '        counter["n"] += 1',
        '        return counter["n"]',
    ]))
    bump = conn.namespace['bump']

    n_threads = 12
    n_per_thread = 15
    seen = []
    seen_lock = threading.Lock()
    errors = []

    def worker(i):
        try:
            for _ in range(n_per_thread):
                v = bump()
                with seen_lock:
                    seen.append(v)
                # interleave a plain call and a remotely-raised exception,
                # so a corrupted response stream would also show up as a
                # call receiving the wrong result/exception.
                assert conn.modules['math'].sqrt((i + 1) ** 2) == i + 1
                try:
                    conn.modules['math'].sqrt(-1)
                except ValueError:
                    pass
                else:
                    errors.append((i, 'sqrt(-1) did not raise'))
        except Exception as e:  # noqa: BLE001 (captured for the assertion below)
            errors.append((i, repr(e)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not [t for t in threads if t.is_alive()], "a worker thread hung"
    assert errors == []
    assert sorted(seen) == list(range(1, n_threads * n_per_thread + 1)), (
        "lost or duplicate increments: concurrent calls corrupted the connection")
    assert conn.eval('counter["n"]') == n_threads * n_per_thread

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_multiple_simultaneous_plugin_subprocesses():
    # Multiple independent Client/RpycInterpPlugin instances, each launching
    # its own plugin subprocess, started concurrently from separate host
    # threads. Confirms no interference between them (e.g. the per-client
    # RPyC endpoint allocation in prepare_cmd()/tempfile.mkstemp racing, or
    # a handshake response getting delivered to the wrong client).
    n = 5
    results = [None] * n
    errors = []

    def worker(i):
        try:
            cfg = pygo_plugin.ClientConfig()
            plug = pyinterp.RpycInterpPlugin()
            cfg.plugins[pyinterp.PLUGIN_NAME] = plug
            cfg.handshake_config = pyinterp.handshake_config()
            cmd = pygo_plugin.Cmd([sys.executable, '-m', 'pygo_plugin.pyinterp'])
            plug.prepare_cmd(cmd)
            cfg.set_cmd(cmd)
            client = pygo_plugin.Client(cfg)
            _, conn = client.dispense(pyinterp.PLUGIN_NAME)

            # each subprocess gets a distinct marker value. If two clients
            # somehow ended up talking to the same subprocess/socket, this
            # would catch it.
            conn.execute('marker = {}'.format(i))
            remote_pid = conn.modules['os'].getpid()
            remote_marker = conn.eval('marker')
            results[i] = (remote_pid, remote_marker)

            conn.close()
            client.kill()
            if not client.exited():
                errors.append((i, 'plugin subprocess did not exit cleanly'))
        except Exception as e:  # noqa: BLE001 (captured for the assertion below)
            errors.append((i, repr(e)))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not [t for t in threads if t.is_alive()], "a worker thread hung"
    assert errors == []
    assert all(results), "a worker never recorded a result"
    assert len({pid for pid, _ in results}) == n, "two workers shared a plugin subprocess"
    assert all(marker == i for i, (_, marker) in enumerate(results)), (
        "cross-talk between concurrently-launched plugin subprocesses")
