#!/usr/bin/env python

from __future__ import absolute_import, print_function

import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

import pygo_plugin
from calc import plugin_pb2, plugin_pb2_grpc


class CalcPlugin(pygo_plugin.Plugin):
    def client_class(self):
        return plugin_pb2_grpc.CalcStub

    def server_register(self, server):
        plugin_pb2_grpc.add_CalcServicer_to_server(CalcServicer(), server)


class CalcServicer(plugin_pb2_grpc.CalcServicer):
    def sum(self, request, context):
        total = request.a + request.b
        return plugin_pb2.SumResponse(result=total)


def handshake_config():
    handshake = pygo_plugin.HandshakeConfig()
    handshake.protocol_version = 1
    handshake.magic_cookie_key = "TEST_CALC_PLUGIN"
    handshake.magic_cookie_value = "magic"
    return handshake


def serve():
    cfg = pygo_plugin.ServeConfig()
    cfg.handshake_config = handshake_config()
    cfg.plugins['calc'] = CalcPlugin()

    try:
        pygo_plugin.serve(cfg)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    serve()
