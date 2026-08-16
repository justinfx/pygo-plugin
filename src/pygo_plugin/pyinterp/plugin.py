from __future__ import absolute_import

import contextlib
import os
import shutil
import sys
import tempfile
import threading

import rpyc
from rpyc.utils.factory import unix_connect
from rpyc.utils.server import ThreadedServer

import pygo_plugin
import pygo_plugin.utils


__all__ = ['RpycInterpPlugin', 'handshake_config', 'serve', 'connect', 'PLUGIN_NAME']


# Endpoint hand-off needs no new RPC: the host pre-allocates it and passes
# it to the plugin subprocess via this env var (see prepare_cmd()/
# _endpoint_from_env() below), the same way go-plugin itself passes e.g.
# PLUGIN_MIN_PORT.
_ENV_ENDPOINT = 'PYGO_PLUGIN_RPYC_ENDPOINT'

_MAGIC_COOKIE_KEY = 'PYGO_PLUGIN_PYINTERP'
_MAGIC_COOKIE_VALUE = 'pyinterp'
_PROTOCOL_VERSION = 1

PLUGIN_NAME = 'pyinterp'


class RpycInterpPlugin(pygo_plugin.Plugin):
    """
    A pygo_plugin.Plugin that hands back a live RPyC connection into the
    plugin subprocess's interpreter instead of a grpc stub. go-plugin's own
    grpc channel still handles the control plane (launch, handshake, health,
    shutdown); object-proxy traffic goes over a second RPyC side-channel
    endpoint, agreed up front via an env var rather than negotiated RPC.

    Used on both ends: host side calls ``prepare_cmd(cmd)`` before
    constructing the Client, then ``client()`` connects via RPyC; plugin
    side's ``server_register()`` starts the RPyC ThreadedServer.
    """

    def __init__(self, service=rpyc.ClassicService):
        self._service = service
        self._endpoint = None  # ('unix', path) or ('tcp', host, port)
        self._rpyc_server = None  # set on the plugin subprocess side only

    def client_class(self):
        # Unused: client() below bypasses the default grpc.insecure_channel
        # connection that the base Plugin.client() would otherwise open.
        return None

    def prepare_cmd(self, cmd):
        """
        Host side. Pre-allocate the RPyC side-channel endpoint and stamp it
        into the plugin subprocess's environment. Call this on the Cmd that
        will be passed to ClientConfig.set_cmd(), before constructing the
        Client. The same RpycInterpPlugin instance must then be used as
        the ClientConfig.plugins[...] entry so client() can see the
        endpoint it just chose.

        Args:
            cmd (pygo_plugin.Cmd):

        Returns:
            pygo_plugin.Cmd: the same cmd, for chaining
        """
        if os.name == 'posix':
            fd, sock_path = tempfile.mkstemp(suffix='.sock', prefix='plugin_rpyc_')
            os.close(fd)
            os.unlink(sock_path)
            self._endpoint = ('unix', os.path.abspath(sock_path))
        else:
            port = pygo_plugin.utils.find_free_port()
            self._endpoint = ('tcp', '127.0.0.1', port)
        cmd.env.append(_format_endpoint_env(self._endpoint))
        return cmd

    def client(self, client_conn):
        if self._endpoint is None:
            raise RuntimeError(
                "RpycInterpPlugin.prepare_cmd() must be called on the Cmd "
                "used to launch this plugin before dispense()")
        # Launch the subprocess and wait for the go-plugin handshake, same
        # as the default Plugin.client() would via conn_endpoint(); we
        # just don't need the resulting grpc endpoint ourselves. This
        # guarantees the plugin subprocess's server_register() (and so the
        # RPyC side channel's listen()) has already run before we connect.
        client_conn.start()
        kind = self._endpoint[0]
        if kind == 'unix':
            conn = unix_connect(self._endpoint[1], service=self._service)
        else:
            _, host, port = self._endpoint
            conn = rpyc.connect(host, port, service=self._service)
        return None, conn

    def server_register(self, server):
        # No grpc service of our own to register; the RPyC ThreadedServer
        # is a separate side channel, started here in a background thread
        # rather than served through the grpc.Server passed in.
        endpoint = _endpoint_from_env()
        if endpoint[0] == 'unix':
            self._rpyc_server = ThreadedServer(self._service, socket_path=endpoint[1])
        else:
            self._rpyc_server = ThreadedServer(self._service, hostname=endpoint[1], port=endpoint[2])
        # Bind/listen synchronously so the endpoint is guaranteed connectable
        # as soon as server_register() returns, instead of racing the
        # background thread's own listen() call.
        self._rpyc_server._listen()
        thread = threading.Thread(
            target=self._rpyc_server.start, daemon=True, name='rpyc-side-channel')
        thread.start()


def _format_endpoint_env(endpoint):
    kind = endpoint[0]
    if kind == 'unix':
        value = 'unix:%s' % endpoint[1]
    else:
        value = 'tcp:%s:%s' % (endpoint[1], endpoint[2])
    return '%s=%s' % (_ENV_ENDPOINT, value)


def _endpoint_from_env():
    raw = os.environ.get(_ENV_ENDPOINT)
    if not raw:
        raise RuntimeError(
            "%s not set in plugin subprocess environment; did the host call "
            "RpycInterpPlugin.prepare_cmd(cmd)?" % _ENV_ENDPOINT)
    kind, _, rest = raw.partition(':')
    if kind == 'unix':
        return 'unix', rest
    host, _, port = rest.rpartition(':')
    return 'tcp', host, int(port)


def handshake_config():
    handshake = pygo_plugin.HandshakeConfig()
    handshake.protocol_version = _PROTOCOL_VERSION
    handshake.magic_cookie_key = _MAGIC_COOKIE_KEY
    handshake.magic_cookie_value = _MAGIC_COOKIE_VALUE
    return handshake


def serve():
    """
    Serve a generic pyinterp plugin: exposes this interpreter to a host
    process as a live RPyC connection, with no plugin-specific server code
    required. Run as ``python -m pygo_plugin.pyinterp``.
    """
    cfg = pygo_plugin.ServeConfig()
    cfg.handshake_config = handshake_config()
    cfg.plugins[PLUGIN_NAME] = RpycInterpPlugin()
    pygo_plugin.serve(cfg)


def _resolve_python(python, env):
    # No python and no env: keep the zero-setup default of "this same
    # interpreter" rather than going through PATH resolution at all.
    if python is None and env is None:
        return sys.executable
    cmd = python or 'python'
    # shutil.which() only consults `path` when `cmd` has no directory
    # component, so an already-absolute/relative path passed as `python`
    # is returned as-is regardless of `env`.
    search_path = env.get('PATH') if env is not None else None
    resolved = shutil.which(cmd, path=search_path)
    if resolved is None:
        raise FileNotFoundError(
            "could not resolve a python interpreter (%r) on PATH%s" % (
                cmd, " from the given env" if env is not None else ""))
    return resolved


@contextlib.contextmanager
def connect(python=None, env=None, args=None, dir=None):
    """
    Launch ``python -m pygo_plugin.pyinterp`` as a plugin subprocess and,
    as a context manager, yield ``(client, conn)``, the
    ``pygo_plugin.Client`` and the live RPyC classic ``Connection`` into
    it. Handles the fixed ``RpycInterpPlugin`` setup dance (ClientConfig /
    prepare_cmd / dispense) and teardown (``conn.close()`` /
    ``client.kill()``) so callers don't need to touch ``RpycInterpPlugin``
    directly::

        with pyinterp.connect() as (client, conn):
            conn.modules['math'].sqrt(16)

    Args:
        python (str): interpreter to launch: an absolute/relative path,
            a bare executable name resolved via PATH (``env['PATH']`` if
            `env` is given, else the current process's PATH), or omitted
            to default to ``sys.executable`` (only when `env` is also
            omitted, otherwise defaults to resolving plain ``'python'``
            against `env`).
        env (dict): environment variables for the subprocess (e.g. a
            resolved venv), also used to resolve
            `python` by name when it isn't already a path. go-plugin
            still appends the host's own environment on top of this
            regardless (see ``RpycInterpPlugin.prepare_cmd()``).
        args (list[str]): extra args appended after
            ``-m pygo_plugin.pyinterp``.
        dir (str): working directory for the subprocess.
    """
    interp = _resolve_python(python, env)

    cfg = pygo_plugin.ClientConfig()
    plug = RpycInterpPlugin()
    cfg.plugins[PLUGIN_NAME] = plug
    cfg.handshake_config = handshake_config()

    cmd = pygo_plugin.Cmd([interp, '-m', 'pygo_plugin.pyinterp'] + list(args or []))
    if env is not None:
        for key, value in env.items():
            cmd.env.append('%s=%s' % (key, value))
    if dir is not None:
        cmd.dir = dir
    # prepare_cmd() appends its own endpoint var to cmd.env, so it must
    # run after any env entries above are added, not before.
    plug.prepare_cmd(cmd)
    cfg.set_cmd(cmd)

    client = pygo_plugin.Client(cfg)
    _, conn = client.dispense(PLUGIN_NAME)
    try:
        yield client, conn
    finally:
        conn.close()
        client.kill()
