from __future__ import absolute_import

import abc

import future.utils as futils
import grpc


__all__ = ['Plugin']


class Plugin(futils.with_metaclass(abc.ABCMeta, object)):
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
