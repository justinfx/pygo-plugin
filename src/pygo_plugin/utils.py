from __future__ import absolute_import

import contextlib
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
