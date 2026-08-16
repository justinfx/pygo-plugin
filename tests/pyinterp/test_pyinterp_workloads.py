from __future__ import absolute_import

import time

from .test_pyinterp import _make_client
from pygo_plugin import pyinterp


# Perf/ergonomics work (batched eval, message-size tuning) is explicitly
# deferred until a real workload demonstrates the need. As a library, we
# don't get to know what that workload will actually be, so instead of
# guessing at an optimization (batching APIs, tuned limits) with no real
# case driving the design, these tests anticipate a couple of plausible
# usage patterns (a large payload crossing the boundary, and a chatty
# sequence of small calls) and confirm current behavior at a reasonable
# scale, rather than assuming it either does or doesn't need work. If a
# real caller later hits an actual wall, these are the tests that should
# grow into a regression check for whatever fix follows.


def test_pyinterp_large_payload_roundtrip():
    # Unlike a hypothetical grpc-based service (which would inherit grpc's
    # ~4MB default message size limit), RpycInterpPlugin's RPyC side
    # channel is a raw socket, not grpc, so nothing in this path should
    # impose that kind of ceiling. Confirms a size an anticipated real
    # caller (e.g. handing back a large buffer/array from a wrapped
    # library) might plausibly hit.
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    size = 20 * 1024 * 1024  # 20MB
    start = time.time()
    conn.execute('data = bytes(bytearray(range(256)) * ({size} // 256 + 1))[:{size}]'.format(size=size))
    remote_len = conn.eval('len(data)')
    fetched = conn.modules.builtins.bytes(conn.namespace['data'])
    elapsed = time.time() - start

    assert remote_len == size
    assert len(fetched) == size
    assert fetched[:512] == bytes(bytearray(range(256))) * 2
    # Generous sanity bound, not a performance assertion. This is here to
    # catch a genuine hang/pathological blowup, not to enforce a target
    # (20MB completed in ~0.1-0.3s in local testing; 30s leaves wide margin
    # for slower/loaded CI runners).
    assert elapsed < 30, "20MB round trip took {:.1f}s, investigate before raising this bound".format(elapsed)

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_many_sequential_calls():
    # A chatty caller doing many small round trips in a loop: the scenario
    # a batched-eval API would exist to help with, if it ever turns out to
    # matter. Confirms today's per-call overhead is low enough that a few
    # hundred sequential calls is a non-issue, without asserting a specific
    # latency number (would be flaky across machines/CI).
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    n = 300
    start = time.time()
    for i in range(n):
        assert conn.modules['os'].getpid() == conn.modules['os'].getpid()
    elapsed = time.time() - start

    # Generous sanity bound (same reasoning as above): local testing saw
    # roughly 0.1ms/call (300 calls in well under 1s); 20s leaves wide
    # margin. If this ever needs to be raised, that's itself a signal that
    # a batched-eval API has finally found its motivating workload.
    assert elapsed < 20, (
        "{} sequential round trips took {:.1f}s ({:.2f}ms/call); if this "
        "regressed, or if a real caller needs more throughput than this, "
        "that's the motivating case a batched-eval API has been waiting "
        "for".format(n, elapsed, elapsed / n * 1000))

    conn.close()
    client.kill()
    assert client.exited()
