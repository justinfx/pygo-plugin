from __future__ import absolute_import

import typing

from ._goplugin import go_plugin as _wrapper
from ._goplugin.go_plugin import HandshakeConfig
from . import plugin

__all__ = ['Client', 'ClientConfig', 'Cmd', 'HandshakeConfig']


# noinspection PyPep8Naming
class Client(object):

    def __init__(self, client_cfg):
        super(Client, self).__init__()
        self._cfg = client_cfg
        self._client = _wrapper.Client(_wrapper.new_client(client_cfg))

    def __del__(self):
        self.kill()

    def dispense(self, plugin_name):
        plug = self._cfg.plugins.get(plugin_name)  # type: plugin.Plugin
        if not plug:
            raise ValueError("plugin name '%s' is not registered in the ClientConfig PluginSet"
                             % plugin_name)
        return plug.client(self)

    def exited(self):
        return self._client.exited()

    def kill(self):
        return self._client.kill()

    def reattach_config(self):
        cfg = _wrapper.ReattachConfig()
        cfg.set_ptr(self._client.reattach_config())
        return cfg

    def ping(self):
        return _wrapper.client_ping(self._client)

    def start(self):
        return _wrapper.NetAddr(self._client.start())

    def conn_endpoint(self):
        addr = self.start()
        endpoint = addr.string()
        if addr.network() == "unix":
            endpoint = "unix:" + endpoint
        return endpoint


# noinspection PyPep8Naming
class ClientConfig(_wrapper.ClientConfig):

    def __init__(self, *args, **kwargs):
        super(ClientConfig, self).__init__(*args, **kwargs)
        self._plugin_set = {}  # typing.Dict[str, plugin.Plugin]

    @property
    def plugins(self):
        # type: () -> typing.Dict[str, plugin.Plugin]
        return self._plugin_set

    def set_cmd(self, cmd, *args, **kwargs):
        """
        Set the plugin command.
        Expects either a Cmd instance or a string/list command.

        Args:
            cmd (Cmd or str or list[str]): plugin command
        """
        if not isinstance(cmd, Cmd):
            cmd = Cmd(cmd)
        super(ClientConfig, self).set_cmd(cmd)


class Cmd(_wrapper.Cmd):

    def __init__(self, args):
        """

        Args:
            args (str or list[str]): Command and arguments to run
        """
        super(Cmd, self).__init__(_wrapper.new_cmd())
        if args:
            # Handle a string
            if not isinstance(args, (list, tuple)):
                args = [args]
            self.path = args[0]
            self.args += args
