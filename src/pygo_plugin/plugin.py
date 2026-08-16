from __future__ import absolute_import

import abc

import grpc


__all__ = ['Plugin', 'HandshakeConfig']


class HandshakeConfig(object):
    """
    Plain, dependency-free stand-in for the Go-bound ``plugin.HandshakeConfig``
    struct, so a plugin subprocess can build one without pulling in the
    compiled gopy extension. ``client.ClientConfig.handshake_config``'s
    setter converts it to the real Go-bound type on the host side.
    """
    __slots__ = ('protocol_version', 'magic_cookie_key', 'magic_cookie_value')

    def __init__(self, protocol_version=0, magic_cookie_key='', magic_cookie_value=''):
        self.protocol_version = protocol_version
        self.magic_cookie_key = magic_cookie_key
        self.magic_cookie_value = magic_cookie_value

    def __repr__(self):
        return (
            'HandshakeConfig(protocol_version=%r, magic_cookie_key=%r, '
            'magic_cookie_value=%r)' % (
                self.protocol_version, self.magic_cookie_key, self.magic_cookie_value))


class Plugin(abc.ABC):
    """
    Plugin is an abstract class providing an interface
    for both the client (host) and server (plugin) sides
    of a plugin connection.
    """
    __slots__ = ()

    @abc.abstractmethod
    def client_class(self):
        """
        Implementation should return the grpc stub client class
        type to use when creating a client connection on the host.
        """
        pass

    @abc.abstractmethod
    def server_register(self, server):  # type: (grpc.Server) -> None
        """
        Implementation should register the service implemenation
        of the plugin using the given grpc Server

        Args:
            server (grpc.Server):
        """
        pass

    def client(self, client_conn):
        """
        Creates a client interface to a plugin, given a Client.
        Returns the grpc channel and the rpc interface to talk
        to the plugin. Caller should close the channel when no
        longer needed.

        Args:
            client_conn (pygo_plugin.Client): client connection

        Returns:
              (``grpc.Channel``, object)
        """
        endpoint = client_conn.conn_endpoint()
        stub_klass = self.client_class()
        channel = grpc.insecure_channel(endpoint)
        stub_rpc = stub_klass(channel)
        return channel, stub_rpc
