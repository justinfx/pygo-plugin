from __future__ import absolute_import

import contextlib
import socket

import pytest

from pygo_plugin import utils


def test_find_free_port():
    port = utils.find_free_port()
    assert port > 0

    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(('127.0.0.1', port))
        next_port = utils.find_free_port(min_port=port)
        assert next_port > port

    next_port = utils.find_free_port(min_port=port)
    assert next_port >= port

    with pytest.raises(IOError):
        utils.find_free_port(min_port=10, max_port=10)
