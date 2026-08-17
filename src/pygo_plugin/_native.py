"""
cffi binding over the compiled ``go_plugin`` shared library (see
``go_plugin/client.go``). This is the sole place that talks to the native
library directly; ``pygo_plugin.client`` builds its public ``Client``/
``ClientConfig``/``Cmd`` classes on top of the thin functions below.

The shared library is a plain OS shared library (``-buildmode=c-shared``),
not a CPython extension: it links no CPython symbols, so one compiled
artifact works unmodified across Python versions. There is accordingly no
per-Python-version filename tag on the library file.
"""

from __future__ import absolute_import

import json
import os
import sys

import cffi

_CDEF = """
uintptr_t NewClient(char* configJSON, char** outError);
void FreeClient(uintptr_t handle);
int  ClientExited(uintptr_t handle);
void ClientKill(uintptr_t handle);
char* ClientPing(uintptr_t handle);
int  ClientStart(uintptr_t handle, char** outNetwork, char** outAddress, char** outError);
int  ClientReattachConfig(
    uintptr_t handle,
    char** outProtocol, char** outNetwork, char** outAddress,
    int* outPid, int* outTest,
    char** outError
);
void FreeString(char* s);
"""


def _library_path():
    if sys.platform == 'darwin':
        ext = 'dylib'
    elif sys.platform == 'win32':
        ext = 'dll'
    else:
        ext = 'so'
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '_goplugin', 'libgoplugin.' + ext)


def _load():
    path = _library_path()
    if not os.path.exists(path):
        raise ImportError(
            "compiled pygo_plugin native library not found at '{}'. "
            "Run 'python setup.py build_py' (or reinstall the package) to build it, "
            "or set PYGO_PLUGIN_SKIP_NATIVE_BUILD=1 if this environment is only "
            "meant to be used plugin-subprocess-side (no pygo_plugin.Client/"
            ".ClientConfig/.Cmd access)".format(path)
        )
    ffi = cffi.FFI()
    ffi.cdef(_CDEF)
    return ffi, ffi.dlopen(path)


_ffi, _lib = _load()


def _take_owned_str(char_p):
    if char_p == _ffi.NULL:
        return ''
    try:
        return _ffi.string(char_p).decode('utf-8')
    finally:
        _lib.FreeString(char_p)


def _take_error(out_error):
    msg = _take_owned_str(out_error[0])
    return msg or 'unknown native error'


def new_client(handshake, cmd, reattach,
               min_port, max_port, start_timeout_msec, auto_mtls):
    """
    Args:
        handshake: object with .protocol_version/.magic_cookie_key/.magic_cookie_value
        cmd: Cmd instance, or None if reattach is set instead
        reattach: ReattachConfig instance, or None if cmd is set instead
        min_port (int):
        max_port (int):
        start_timeout_msec (int):
        auto_mtls (bool):

    Returns:
        int: opaque Client handle

    Raises:
        RuntimeError: if the native NewClient call fails (e.g. malformed config).
    """
    config = {
        'handshake': {
            'protocol_version': int(handshake.protocol_version),
            'magic_cookie_key': handshake.magic_cookie_key,
            'magic_cookie_value': handshake.magic_cookie_value,
        },
        'min_port': int(min_port),
        'max_port': int(max_port),
        'start_timeout_msec': int(start_timeout_msec),
        'auto_mtls': bool(auto_mtls),
    }
    if cmd and cmd.valid:
        config['cmd'] = {
            'path': cmd.path,
            'args': list(cmd.args),
            'env': list(cmd.env),
            'dir': cmd.dir,
        }
    elif reattach and reattach.valid:
        config['reattach'] = {
            'protocol': reattach.protocol,
            'network': reattach.network,
            'address': reattach.address,
            'pid': int(reattach.pid),
            'test': bool(reattach.test),
        }

    out_error = _ffi.new('char**')
    handle = _lib.NewClient(json.dumps(config).encode('utf-8'), out_error)
    if handle == 0:
        raise RuntimeError(_take_error(out_error))
    return int(handle)


def free_client(handle):
    _lib.FreeClient(handle)


def client_exited(handle):
    return bool(_lib.ClientExited(handle))


def client_kill(handle):
    _lib.ClientKill(handle)


def client_ping(handle):
    return _take_owned_str(_lib.ClientPing(handle))


def client_start(handle):
    """Returns (network, address)."""
    out_network = _ffi.new('char**')
    out_address = _ffi.new('char**')
    out_error = _ffi.new('char**')
    status = _lib.ClientStart(handle, out_network, out_address, out_error)
    if status != 0:
        raise RuntimeError(_take_error(out_error))
    return _take_owned_str(out_network[0]), _take_owned_str(out_address[0])


def client_reattach_config(handle):
    """Returns a dict (protocol, network, address, pid, test) or None."""
    out_protocol = _ffi.new('char**')
    out_network = _ffi.new('char**')
    out_address = _ffi.new('char**')
    out_pid = _ffi.new('int*')
    out_test = _ffi.new('int*')
    out_error = _ffi.new('char**')
    status = _lib.ClientReattachConfig(
        handle, out_protocol, out_network, out_address, out_pid, out_test, out_error)
    if status < 0:
        raise RuntimeError(_take_error(out_error))
    if status == 0:
        return None
    return {
        'protocol': _take_owned_str(out_protocol[0]),
        'network': _take_owned_str(out_network[0]),
        'address': _take_owned_str(out_address[0]),
        'pid': int(out_pid[0]),
        'test': bool(out_test[0]),
    }
