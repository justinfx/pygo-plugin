from __future__ import absolute_import, print_function

import threading
from concurrent import futures
import logging
import multiprocessing
import os
import sys
import tempfile
import typing

import grpc
from grpc_health.v1.health import HealthServicer
from grpc_health.v1 import health_pb2, health_pb2_grpc
from grpc_reflection.v1alpha import reflection

import pygo_plugin
import pygo_plugin.proto.grpc_controller_pb2 as _controller_pb2
import pygo_plugin.proto.grpc_controller_pb2_grpc as _controller_pb2_grpc
import pygo_plugin.utils


__all__ = ['serve', 'Server', 'ServeConfig']


_GO_PLUGIN_PROTOCOL_VER = 1


def serve(cfg):
    """
    Serve the plugin service and block until the
    server chooses to stop.
    If the server fails, then exit the process with
    a non-zero status.

    For more control over the Server, create a Server
    instance and manage it directly.

    Args:
        cfg (ServeConfig):
    """
    server = pygo_plugin.Server(cfg)
    if not server.serve(wait=True):
        if server.error_msg:
            logging.error(server.error_msg)
        else:
            logging.error("plugin server exited with unknown error")
        sys.exit(1)


class ServeConfig(object):
    """
    ServeConfig defines the configuration options for
    staring a plugin server.
    """
    def __init__(self):
        self._handshake = None
        self._plugins = {}  # typing.Dict[str, plugin.Plugin]

    @property
    def handshake_config(self):
        """
        handshake_config is the configuration that must match clients.

        Returns:
            pygo_plugin.HandshakeConfig
        """
        if self._handshake is None:
            self._handshake = pygo_plugin.HandshakeConfig()
        return self._handshake

    @handshake_config.setter
    def handshake_config(self, cfg):
        if cfg is not None and not isinstance(cfg, pygo_plugin.HandshakeConfig):
            raise TypeError("type %r is not a HandshakeConfig" % type(cfg))
        self._handshake = cfg

    @property
    def plugins(self):
        """
        The plugins that are served.
        The implied version of this PluginSet is the Handshake.ProtocolVersion.

        Returns:
            typing.Dict[str, plugin.Plugin]:
        """
        if self._plugins is None:
            self._plugins = {}
        return self._plugins

    @plugins.setter
    def plugins(self, plugins):
        self._plugins = plugins


class Server(object):
    """
    Server provides the implementation of one or more plugins,
    and serves it via grpc.
    """
    GRPC_SERVICE_NAME = 'plugin'

    def __init__(self, cfg):
        """
        Args:
            cfg (ServeConfig):
        """
        self._cfg = cfg
        self._server = None
        self._error = ''

    @property
    def error_msg(self):
        """
        Return the last error message generated by the server

        Returns:
            str
        """
        return self._error

    def server(self, **opts):
        """
        Create an instance of a grpc server, passing extra
        grpc options to the server constructor.
        Implementation calls ``self.default_grpc_server()``

        Args:
            **opts: extra grpc.Server options

        Returns:
            ``grpc.Server``
        """
        return self.default_grpc_server(**opts)

    def serve(self, wait=False):
        """
        Start serving the plugin grpc services, and return control
        to the called. If ``wait=True``, block until the server is stopped.

        If ``False`` is returned, caller can check `.error_msg` to read the
        last error message.

        Args:
            wait (bool): Block until server stops

        Returns:
            bool: Return True on successful start
        """
        self.stop()
        self._error = ''

        if not self.check_magic_key():
            return False

        self._server = server = self.server()

        # We need to build a health service to work with go-plugin
        health = HealthServicer()
        health.set(self.GRPC_SERVICE_NAME, health_pb2.HealthCheckResponse.ServingStatus.Value('SERVING'))
        health_pb2_grpc.add_HealthServicer_to_server(health, server)

        # enable controller
        _controller_pb2_grpc.add_GRPCControllerServicer_to_server(ServerController(server), server)

        # instrument the server to capture the registration of the plugin
        # services, so that we can automatically add them for reflection
        _add_generic_rpc_handlers = server.add_generic_rpc_handlers
        plugin_service_names = set()

        def add_generic_rpc_handlers(self, handlers):
            plugin_service_names.update({h.service_name() for h in handlers})
            return _add_generic_rpc_handlers(handlers)

        server.add_generic_rpc_handlers = add_generic_rpc_handlers.__get__(server, server.__class__)

        # Register all plugins
        plugins = self._cfg.plugins
        for name in plugins:
            plugin = plugins[name]
            plugin.server_register(server)

        # reset the handler and set up reflection
        server.add_generic_rpc_handlers = _add_generic_rpc_handlers
        if plugin_service_names:
            names = list(plugin_service_names)
            logging.info("plugin server installing grpc reflection for plugins: %s", names)
            names.append(reflection.SERVICE_NAME)
            reflection.enable_server_reflection(names, server)

        # configure server endpoint
        if os.name == 'posix':
            fd, sock_path = tempfile.mkstemp(suffix=".sock", prefix="plugin_")
            os.close(fd)
            os.unlink(sock_path)
            endpoint = os.path.abspath(sock_path)
            server.add_insecure_port("unix:" + endpoint)
            network = 'unix'
        else:
            port = 0
            port_opts = {}
            try:
                port_opts['min_port'] = int(os.environ.get('PLUGIN_MIN_PORT', ''))
            except ValueError:
                pass
            try:
                port_opts['max_port'] = int(os.environ.get('PLUGIN_MAX_PORT', ''))
            except ValueError:
                pass
            if port_opts:
                port = pygo_plugin.utils.find_free_port(**port_opts)
            port = server.add_insecure_port('127.0.0.1:{}'.format(port))
            network = 'tcp'
            endpoint = '127.0.0.1:%d' % port

        server.start()

        # Output information
        handshake = "{proto_ver}|{app_proto_ver}|{network}|{endpoint}|{protocol}".format(
            proto_ver=_GO_PLUGIN_PROTOCOL_VER,
            app_proto_ver=self._cfg.handshake_config.protocol_version,
            network=network,
            endpoint=endpoint,
            protocol='grpc',
        )
        # logging.info(handshake)
        print(handshake)
        sys.stdout.flush()

        if wait:
            server.wait_for_termination()

        return True

    def stop(self, grace=None):  # type: (float) -> threading.Event
        """
        Stop a running server.
        A grace period in seconds can be given to wait for the
        server to actually stop gracefully. Otherwise it will
        be stopped immediately without waiting for in-flight
        requests to complete.

        Returns a ``threading.Event`` that will be set when this
        Server has completely stopped, i.e. when running RPCs
        either complete or are aborted and all handlers have
        terminated.

        Args:
            grace (float): shutdown grace period in seconds

        Returns:
            threading.Event
        """
        if self._server is None:
            evt = threading.Event()
            evt.set()
            return evt
        return self._server.stop(grace)

    def check_magic_key(self):
        """
        Checks if the handshake configuration was set in the current
        environment, and if it matches the current server configuration.
        If the check fails, ``.error_msg`` will be set and ``False`` will
        be returned.

        Returns:
            bool: success
        """
        # Check magic key/value
        if self._cfg.handshake_config.magic_cookie_key:
            env_key = self._cfg.handshake_config.magic_cookie_key
            env_val = self._cfg.handshake_config.magic_cookie_value
            if os.environ.get(env_key) != env_val:
                self._error = (
                    "Misconfigured ServeConfig handshake given to serve this plugin:\n"
                    "  no magic cookie key, or value was set incorrectly.\n"
                    "Please notify the plugin author and report this as a bug.\n")
                return False
        return True

    @classmethod
    def default_grpc_server(cls, **opts):
        """
        Create a default grpc Server instance using a
        concurrent.futures thread pool. The thread pool
        will be set to a default worker count based on
        the host cpu count.

        Args:
            **opts: ``grpc.server`` constructor options

        Returns:
            ``grpc.Server``
        """
        if 'thread_pool' not in opts:
            # python 3.8+ concurrent.futures default
            workers = min(32, multiprocessing.cpu_count() + 4)
            opts['thread_pool'] = futures.ThreadPoolExecutor(max_workers=workers)
        return grpc.server(**opts)


class ServerController(_controller_pb2_grpc.GRPCControllerServicer):
    """
    ServerController implements controller requests in the server,
    sent by the client.
    """
    def __init__(self, server, grace=2):
        """
        Args:
            server (Server): Server instance
            grace (float): Graceful shutdown time in seconds
        """
        self._server = server  # type: Server
        self._grace = float(grace)
    
    def Shutdown(self, request, context):
        """
        Shut down the server using the configured grace period
        """
        event = self._server.stop(self._grace)  # type: threading.Event
        if not event.wait():
            self._server.stop(0)
        return _controller_pb2.Empty()
