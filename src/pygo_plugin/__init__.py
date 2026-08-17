from __future__ import absolute_import

from .plugin import *
from .server import *

# .client imports the compiled native library, which a plugin subprocess
# (only .plugin/.server) shouldn't need just for `import pygo_plugin` to
# work.
_CLIENT_ATTRS = ('Client', 'ClientConfig', 'Cmd', 'ReattachConfig')

__all__ = list(plugin.__all__) + list(server.__all__) + list(_CLIENT_ATTRS)


# Import .client lazily on first access to Client/ClientConfig/Cmd, instead
# of eagerly at the top of this file, so plain `import pygo_plugin` doesn't
# require the compiled native library.
def __getattr__(name):
    if name in _CLIENT_ATTRS:
        from . import client
        value = getattr(client, name)
        globals()[name] = value
        return value
    raise AttributeError("module %r has no attribute %r" % (__name__, name))
