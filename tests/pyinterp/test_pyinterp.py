from __future__ import absolute_import

import gc
import os
import sys
import time

import pytest
import rpyc
from rpyc.utils.factory import unix_connect

import pygo_plugin
from pygo_plugin import pyinterp


_COUNTED_CLASS_SRC = '\n'.join([
    'class _Counted(object):',
    '    count = 0',
    '    def __init__(self):',
    '        type(self).count += 1',
    '    def __del__(self):',
    '        type(self).count -= 1',
])


def _make_client():
    cfg = pygo_plugin.ClientConfig()
    plug = pyinterp.RpycInterpPlugin()
    cfg.plugins[pyinterp.PLUGIN_NAME] = plug
    cfg.handshake_config = pyinterp.handshake_config()

    cmd = pygo_plugin.Cmd([sys.executable, '-m', 'pygo_plugin.pyinterp'])
    plug.prepare_cmd(cmd)
    cfg.set_cmd(cmd)

    return pygo_plugin.Client(cfg)


def test_pyinterp_stdlib_roundtrip():
    client = _make_client()
    assert not client.exited()
    assert client.ping() == ""

    channel, conn = client.dispense(pyinterp.PLUGIN_NAME)
    assert channel is None  # no grpc channel; RPyC owns the object-proxy traffic

    remote_os = conn.modules['os']
    assert remote_os.getpid() != os.getpid()

    remote_math = conn.modules['math']
    assert remote_math.sqrt(16) == 4.0

    # construct a remote object (a proper netref proxy, not a copy) and
    # mutate it via a method call
    remote_list = conn.modules.builtins.list([1, 2, 3])
    remote_list.append(4)
    assert list(remote_list) == [1, 2, 3, 4]

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_callback():
    # This is the capability grpc_broker was meant to provide. Confirms
    # RPyC gives it for free: pass a host-side callable into a remote call
    # and have the remote interpreter invoke it.
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    seen = []

    def host_cb(x):
        seen.append(x)
        return x * 2

    result = conn.modules.builtins.list(conn.modules.builtins.map(host_cb, [1, 2, 3]))
    assert list(result) == [2, 4, 6]
    assert seen == [1, 2, 3]

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_connect():
    # connect() replaces the ClientConfig/Cmd/prepare_cmd/dispense dance in
    # _make_client() with one call, and handles conn.close()/client.kill()
    # on exit.
    with pyinterp.connect(python=sys.executable) as (client, conn):
        assert not client.exited()
        assert conn.modules['math'].sqrt(16) == 4.0
    assert client.exited()


def test_pyinterp_connect_default_python():
    # python=None with no env defaults to sys.executable (this same
    # interpreter) rather than resolving a bare "python" off PATH.
    with pyinterp.connect() as (client, conn):
        assert conn.modules['sys'].executable == sys.executable


def test_pyinterp_resolve_python_by_name():
    # A bare executable name (no directory component) resolves via PATH,
    # same as the current env by default.
    name = os.path.basename(sys.executable)
    resolved = pyinterp.plugin._resolve_python(name, None)
    assert os.path.samefile(resolved, sys.executable)


def test_pyinterp_resolve_python_from_env():
    # A bare name resolves against env['PATH'] when an env dict is given,
    # not the current process's PATH; this is the Oz-style use case.
    name = os.path.basename(sys.executable)
    fake_env = {'PATH': os.path.dirname(sys.executable)}
    resolved = pyinterp.plugin._resolve_python(name, fake_env)
    assert os.path.samefile(resolved, sys.executable)


def test_pyinterp_resolve_python_absolute():
    # An already-absolute path is returned as-is, regardless of env.
    resolved = pyinterp.plugin._resolve_python(sys.executable, {'PATH': '/does/not/exist'})
    assert resolved == sys.executable


def test_pyinterp_resolve_python_missing():
    with pytest.raises(FileNotFoundError):
        pyinterp.plugin._resolve_python('no-such-interpreter-xyz', {'PATH': '/does/not/exist'})


def test_pyinterp_netref_refcounting():
    # Dropping the host-side netref proxy must release the corresponding
    # object in the plugin subprocess: no leaked objects in the child
    # interpreter after the host stops referencing them.
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    conn.execute(_COUNTED_CLASS_SRC)
    remote_cls = conn.namespace['_Counted']

    def remote_count():
        return conn.eval('_Counted.count')

    assert remote_count() == 0

    proxy = remote_cls()
    assert remote_count() == 1

    # BaseNetref.__del__ sends an async decref request. The remote server
    # thread processes it slightly after the host-side gc pass, so poll
    # briefly instead of asserting immediately.
    del proxy
    gc.collect()
    deadline = time.time() + 5
    count = remote_count()
    while count != 0 and time.time() < deadline:
        time.sleep(0.05)
        count = remote_count()
    assert count == 0

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_close_with_live_netref():
    # Closing the connection / killing the plugin while a netref proxy is
    # still live on the host must not hang or raise on either side. Unlike
    # the other tests here, this one deliberately never drops `proxy`
    # before tearing down.
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    conn.execute(_COUNTED_CLASS_SRC)
    proxy = conn.namespace['_Counted']()  # noqa: F841 (intentionally kept live)

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_exception_duck_typing():
    # Codifies a real finding: exceptions raised in the plugin subprocess
    # do not round-trip as a real isinstance()-able type when the host
    # cannot import the exception's defining module (here, a class defined
    # ad hoc via conn.execute(), so it is never importable on the host by
    # construction). The supported contract is broad `except Exception:`
    # plus duck-typing on type(e).__name__ / __module__ / the message text.
    client = _make_client()
    _, conn = client.dispense(pyinterp.PLUGIN_NAME)

    conn.execute('\n'.join([
        'class MyRemoteError(Exception):',
        '    pass',
        'def raise_it():',
        '    raise MyRemoteError("boom")',
    ]))
    raise_it = conn.namespace['raise_it']

    with pytest.raises(Exception) as excinfo:
        raise_it()
    e = excinfo.value
    assert 'MyRemoteError' in type(e).__name__
    assert 'boom' in str(e)

    # isinstance()/except against the remote class itself is NOT part of the
    # supported contract: it either returns False or raises, never True.
    remote_cls = conn.namespace['MyRemoteError']
    assert isinstance(e, remote_cls) is False
    with pytest.raises(TypeError):
        try:
            raise_it()
        except remote_cls:
            pass

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_exception_instantiate_custom_exceptions():
    # Optional/exploratory follow-up: confirm whether opting in to
    # instantiate_custom_exceptions changes anything observable for an
    # exception type that IS importable host-side (a builtin). This
    # already works under the default config (asserted below via the
    # plugin's normal client()); the point of this test is only to confirm
    # the opt-in doesn't change that case. No constructor parameter has
    # been added to RpycInterpPlugin since nothing here demonstrates a
    # need for one yet.
    cfg = pygo_plugin.ClientConfig()
    plug = pyinterp.RpycInterpPlugin()
    cfg.plugins[pyinterp.PLUGIN_NAME] = plug
    cfg.handshake_config = pyinterp.handshake_config()
    cmd = pygo_plugin.Cmd([sys.executable, '-m', 'pygo_plugin.pyinterp'])
    plug.prepare_cmd(cmd)
    cfg.set_cmd(cmd)
    client = pygo_plugin.Client(cfg)

    _, conn_default = client.dispense(pyinterp.PLUGIN_NAME)
    with pytest.raises(ValueError) as excinfo:
        conn_default.eval('int("not a number")')
    assert 'not a number' in str(excinfo.value)
    conn_default.close()

    # RpycInterpPlugin.client() doesn't expose a way to pass a custom
    # protocol_config through to rpyc.connect()/unix_connect(). There's no
    # need for it yet, so exercise the flag with a second, manual
    # connection to the same already-running plugin subprocess instead of
    # adding speculative constructor surface for a single test.
    endpoint = plug._endpoint
    protocol_config = {'instantiate_custom_exceptions': True}
    if endpoint[0] == 'unix':
        conn = unix_connect(endpoint[1], service=rpyc.ClassicService, config=protocol_config)
    else:
        conn = rpyc.connect(endpoint[1], endpoint[2], service=rpyc.ClassicService, config=protocol_config)

    with pytest.raises(ValueError) as excinfo:
        conn.eval('int("not a number")')
    assert 'not a number' in str(excinfo.value)

    conn.close()
    client.kill()
    assert client.exited()


def test_pyinterp_import_excludes_goplugin():
    # A plugin subprocess only ever needs pygo_plugin.plugin/.server (and,
    # for this plugin type, .pyinterp). It must never transitively import
    # pygo_plugin.client, which loads the compiled go_plugin native shared
    # library via pygo_plugin._native. Verified in a fresh subprocess (not
    # this test process, which may have already imported pygo_plugin.client
    # via other tests/fixtures).
    script = (
        "import sys\n"
        "import pygo_plugin.pyinterp.plugin\n"
        "assert 'pygo_plugin.client' not in sys.modules, sorted(sys.modules)\n"
        "assert 'pygo_plugin._native' not in sys.modules, sorted(sys.modules)\n"
        "print('OK')\n"
    )
    import subprocess
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'OK'


def test_pyinterp_subprocess_without_goplugin_so():
    # Stronger version of the test above: physically hide the compiled
    # go_plugin native shared library so a fresh interpreter genuinely
    # CANNOT load it, then confirm the plugin subprocess (a real, separate
    # process) still starts and completes a normal round trip. The host
    # process here is allowed to already have the library loaded in memory
    # (from module import time / other tests); only the host actually
    # needs it, to launch and dispense the plugin subprocess in the first
    # place.
    # Force the host side's own (in-memory, already-loaded-from-disk) copy
    # of the library to be resolved *before* hiding it on disk below,
    # otherwise this process, not just the plugin subprocess, would fail to
    # load it fresh, which is not what this test is checking.
    import pygo_plugin._goplugin as _goplugin_pkg
    import pygo_plugin.client  # noqa: F401

    ext_dir = os.path.dirname(_goplugin_pkg.__file__)
    ext_names = [
        name for name in os.listdir(ext_dir)
        if name.startswith('libgoplugin.') and name.endswith(('.so', '.dylib', '.dll'))
    ]
    assert ext_names, "expected to find the compiled native library under %s" % ext_dir

    moved = []
    try:
        for name in ext_names:
            src = os.path.join(ext_dir, name)
            dst = src + '.hidden-for-test'
            os.rename(src, dst)
            moved.append((src, dst))

        client = _make_client()
        _, conn = client.dispense(pyinterp.PLUGIN_NAME)
        assert conn.modules['os'].getpid() != os.getpid()
        conn.close()
        client.kill()
        assert client.exited()
    finally:
        for src, dst in moved:
            os.rename(dst, src)
