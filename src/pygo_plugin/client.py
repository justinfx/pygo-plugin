from __future__ import absolute_import

from . import _native
from . import plugin

__all__ = ['Client', 'ClientConfig', 'Cmd', 'ReattachConfig']


class Cmd(object):

    def __init__(self, args=None):
        """
        Args:
            args (str or list[str]): Command and arguments to run
        """
        self.path = ''
        self.args = []
        self.env = []
        self.dir = ''
        if args:
            # Handle a string
            if not isinstance(args, (list, tuple)):
                args = [args]
            self.path = args[0]
            self.args = list(args)

    @property
    def valid(self):
        return bool(self.path)

    def __repr__(self):
        return 'Cmd(path=%r, args=%r, env=%r, dir=%r)' % (
            self.path, self.args, self.env, self.dir)


class ReattachConfig(object):
    """
    Plain, dependency-free reattach info: either read back from a running
    Client (see Client.reattach_config()) or built directly by a caller
    wanting to attach to an already-running plugin process.
    """

    def __init__(self, protocol='', network='', address='', pid=-1, test=False):
        self.protocol = protocol
        self.network = network
        self.address = address
        self.pid = pid
        self.test = test

    @property
    def valid(self):
        return bool(self.protocol) and bool(self.network) and bool(self.address)

    def __repr__(self):
        if not self.valid:
            return '<ReattachConfig: Valid=False>'
        return '<ReattachConfig: Protocol=%s, Addr=%s:%s, Pid=%s>' % (
            self.protocol, self.network, self.address, self.pid)


class _NetAddr(object):
    """Matches the Go net.Addr shape (.network()/.string()) that
    Client.start()/conn_endpoint() already depend on."""

    def __init__(self, network, address):
        self._network = network
        self._address = address

    def network(self):
        return self._network

    def string(self):
        return self._address


# noinspection PyPep8Naming
class ClientConfig(object):

    def __init__(self):
        super(ClientConfig, self).__init__()
        self._plugin_set = {}  # typing.Dict[str, plugin.Plugin]
        self.handshake_config = plugin.HandshakeConfig()
        self._cmd = None
        self._reattach = None
        self.min_port = 0
        self.max_port = 0
        self.auto_mtls = False
        self._start_timeout_msec = 0

    @property
    def plugins(self):
        # type: () -> typing.Dict[str, plugin.Plugin]
        return self._plugin_set

    def cmd(self):
        if self._cmd is None:
            self._cmd = Cmd()
        return self._cmd

    def set_cmd(self, cmd, *args, **kwargs):
        """
        Set the plugin command.
        Expects either a Cmd instance or a string/list command.

        Args:
            cmd (Cmd or str or list[str]): plugin command
        """
        if not isinstance(cmd, Cmd):
            cmd = Cmd(cmd)
        self._cmd = cmd

    def reattach_config(self):
        return self._reattach

    def set_reattach_config(self, cfg):
        self._reattach = cfg

    def start_timeout(self):
        return self._start_timeout_msec

    def set_start_timeout(self, msec):
        self._start_timeout_msec = msec


# noinspection PyPep8Naming
class Client(object):

    def __init__(self, client_cfg):
        super(Client, self).__init__()
        self._cfg = client_cfg
        cmd = client_cfg._cmd if (client_cfg._cmd and client_cfg._cmd.valid) else None
        reattach = client_cfg._reattach if (client_cfg._reattach and client_cfg._reattach.valid) else None
        self._handle = _native.new_client(
            client_cfg.handshake_config, cmd, reattach,
            client_cfg.min_port, client_cfg.max_port,
            client_cfg._start_timeout_msec, client_cfg.auto_mtls,
        )

    def __del__(self):
        self.kill()
        _native.free_client(self._handle)

    def dispense(self, plugin_name):
        plug = self._cfg.plugins.get(plugin_name)  # type: plugin.Plugin
        if not plug:
            raise ValueError("plugin name '%s' is not registered in the ClientConfig PluginSet"
                             % plugin_name)
        return plug.client(self)

    def exited(self):
        return _native.client_exited(self._handle)

    def kill(self):
        return _native.client_kill(self._handle)

    def reattach_config(self):
        info = _native.client_reattach_config(self._handle)
        if info is None:
            return ReattachConfig()
        return ReattachConfig(
            protocol=info['protocol'], network=info['network'], address=info['address'],
            pid=info['pid'], test=info['test'],
        )

    def ping(self):
        return _native.client_ping(self._handle)

    def start(self):
        network, address = _native.client_start(self._handle)
        return _NetAddr(network, address)

    def conn_endpoint(self):
        addr = self.start()
        endpoint = addr.string()
        if addr.network() == "unix":
            endpoint = "unix:" + endpoint
        return endpoint
