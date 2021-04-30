from __future__ import absolute_import

import sys

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
