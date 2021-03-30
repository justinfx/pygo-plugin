from __future__ import absolute_import

import contextlib
import inspect
import re
import socket

_MAX_PORT = 65535


def find_free_port(min_port=1024, max_port=_MAX_PORT):
    """
    Find a free port between a given range.
    If min_port=0, return a completely random free port.

    Args:
        min_port (int): first port number to try
        max_port (int): last port number to try

    Returns:
        int: port
    """
    port = min_port
    while port <= max_port:
        try:
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
                s.bind(('127.0.0.1', port))
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                return s.getsockname()[1]
        except OSError:
            port += 1
    raise IOError("no free port in range {}-{}".format(min_port, max_port))


class PEP8NamingMeta(type):
    """
    A metaclass that will convert public attributes to
    snake_case and hide the original attribute.

    Python3 usage::

        class MyClass(object, metaclass=PEP8NamingMeta):
            ...

    Python2/3 usage::

        from future.utils import with_metaclass

        class MyClass(with_metaclass(PEP8NamingMeta, object)):
            ...

    """
    _RX_MATCH_FIRST_CAP = re.compile(r"([A-Z])([A-Z][a-z])")
    _RX_MATCH_ALL_CAP = re.compile(r"([a-z0-9])([A-Z])")

    def __new__(mcls, name, bases, namespace, **kwargs):
        cls = type.__new__(mcls, name, bases, namespace, **kwargs)

        # original attrs that we want to hide
        exclude = set()

        for name in dir(cls):
            # only look at public attributes
            if name.startswith('_'):
                continue

            new_name = mcls._to_snake_case(name)
            if new_name == name:
                # already good
                continue

            attr = getattr(cls, name)

            # handle staticmethods
            if inspect.isfunction(attr):
                if any((name in base.__dict__
                        and isinstance(base.__dict__[name], staticmethod)) for base in bases):
                    attr = staticmethod(attr)

            setattr(cls, new_name, attr)
            exclude.add(name)

        def __getattribute__(self, name):
            if name in exclude:
                raise AttributeError(name)
            return super(cls, self).__getattribute__(name)
        cls.__getattribute__ = __getattribute__

        def __dir__(self):
            return sorted((set(dir(cls)) | set(self.__dict__)) - exclude)
        cls.__dir__ = __dir__

        return cls

    @classmethod
    def _to_snake_case(cls, inp):
        output = cls._RX_MATCH_FIRST_CAP.sub(r"\1_\2", inp)
        output = cls._RX_MATCH_ALL_CAP.sub(r"\1_\2", output)
        output = output.replace('-', '_')
        return output.lower()


