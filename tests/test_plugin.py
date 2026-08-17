from __future__ import absolute_import

import sys
import time

import pygo_plugin
from tests.calc import calc_plugin


def test_plugin_impl():
    plug = calc_plugin.CalcPlugin()
    assert plug.client_class() is calc_plugin.plugin_pb2_grpc.CalcStub


def test_plugin_call():
    cfg = pygo_plugin.ClientConfig()
    cfg.plugins['calc'] = calc_plugin.CalcPlugin()
    cfg.set_cmd([sys.executable, calc_plugin.__file__])
    cfg.handshake_config = calc_plugin.handshake_config()

    client = pygo_plugin.Client(cfg)
    assert not client.exited()
    assert client.ping() == ""
    channel, calc = client.dispense('calc')
    a, b = 4, 5
    with channel:
        req = calc_plugin.plugin_pb2.SumRequest(a=a, b=b)
        resp = calc.sum(req)
    expect = a + b
    assert resp.result == expect

    client.kill()
    assert client.exited()


def test_client_reattach():
    cfg = pygo_plugin.ClientConfig()
    cfg.plugins['calc'] = calc_plugin.CalcPlugin()
    cfg.set_cmd([sys.executable, calc_plugin.__file__])
    cfg.handshake_config = calc_plugin.handshake_config()

    client = pygo_plugin.Client(cfg)
    channel, calc = client.dispense('calc')
    with channel:
        req = calc_plugin.plugin_pb2.SumRequest(a=2, b=3)
        resp = calc.sum(req)
    assert resp.result == 5

    reattach = client.reattach_config()
    assert reattach.valid
    assert reattach.protocol == 'grpc'
    assert reattach.network in ('unix', 'tcp')
    assert reattach.address
    assert reattach.pid > 0
    # This project's plugin server doesn't implement go-plugin's Test mode
    # (ServeConfig.Test), so a real reattach always reports test=False here
    # and killing a reattached client really does kill the process, as
    # asserted below.
    assert not reattach.test

    # A second, independent Client, built from the reattach info instead of
    # a Cmd, should connect to the same already-running subprocess rather
    # than launching a new one.
    cfg2 = pygo_plugin.ClientConfig()
    cfg2.plugins['calc'] = calc_plugin.CalcPlugin()
    cfg2.handshake_config = calc_plugin.handshake_config()
    cfg2.set_reattach_config(reattach)

    client2 = pygo_plugin.Client(cfg2)
    assert not client2.exited()

    channel2, calc2 = client2.dispense('calc')
    with channel2:
        req = calc_plugin.plugin_pb2.SumRequest(a=10, b=20)
        resp = calc2.sum(req)
    assert resp.result == 30

    # Killing through the reattached client should bring down the same OS
    # process the original client is watching, proving it's the same
    # subprocess rather than a second one.
    client2.kill()
    deadline = time.time() + 5
    while time.time() < deadline and not client.exited():
        time.sleep(0.05)
    assert client.exited()
    assert client2.exited()
