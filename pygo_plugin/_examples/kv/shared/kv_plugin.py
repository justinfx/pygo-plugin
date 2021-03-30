from __future__ import absolute_import

import errno
import logging
import os

import pygo_plugin
from pygo_plugin._examples.kv.shared import kv_pb2, kv_pb2_grpc


class KVPlugin(pygo_plugin.Plugin):
    """
    Our plugin implementation for a client and server to
    use the KV service
    """
    def client_class(self):
        """
        Return the grpc stub class for use by the client
        """
        return kv_pb2_grpc.KVStub

    def server_register(self, server):
        """
        Given a server instance, perform the registration of the
        servicer implementation, so that it can be served by the
        plugin
        """
        kv_pb2_grpc.add_KVServicer_to_server(KVServicer(), server)


class KVServicer(kv_pb2_grpc.KVServicer):
    """Server implementation of KVServicer"""

    KV_DIR = os.environ.get('KV_DIR', '')

    def Get(self, request, context):
        filename = self._path("kv_" + request.key)
        result = kv_pb2.GetResponse()
        try:
            with open(filename, 'r+b') as f:
                result.value = f.read()
        except (IOError, OSError) as e:
            if e.errno != errno.ENOENT:
                logging.error("Get: %s", e)
        return result

    def Put(self, request, context):
        filename = self._path("kv_" + request.key)
        value = "{0}\n\nWritten from plugin-python".format(request.value)
        with open(filename, 'w') as f:
            f.write(value)

        return kv_pb2.Empty()

    def _path(self, key):
        return os.path.join(self.KV_DIR, key + '.store')


def handshake_config():
    """
    A shared handshake config for client and server
    """
    handshake = pygo_plugin.HandshakeConfig()
    handshake.protocol_version = 1
    handshake.magic_cookie_key = "BASIC_PLUGIN"
    handshake.magic_cookie_value = "hello"
    return handshake
