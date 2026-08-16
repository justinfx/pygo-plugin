# pyinterp Example

This is a minimal example of `pygo_plugin.pyinterp`: a host launching a *second Python interpreter* as a
plugin subprocess and getting back a live, transparent proxy into it.

Unlike the [`../kv/`](../kv/) example, there is no per-language `Plugin`/`.proto` implementation to write here -
any Python interpreter running `python -m pygo_plugin.pyinterp` is already a valid plugin. The interesting part
of pyinterp isn't in this example's code, it's in what interpreter you point it at: a different Python version,
or a venv with a dependency graph the host process can't (or shouldn't) install directly.

## Usage

```
python main.py sqrt 16
python main.py greet World
```

`sqrt` proves basic remote stdlib access - `math.sqrt` actually runs inside the plugin subprocess, not the
host. `greet` proves the actual point of pyinterp: it calls into [`remote_greeter.py`](remote_greeter.py), a
module the host process **never imports directly** - only the plugin subprocess needs it on its own `sys.path`.
That file stands in for a real third-party library the host structurally cannot import itself.

By default the plugin subprocess runs on the same interpreter as the host (`sys.executable`), so the example
works with no extra setup. To see the actual cross-interpreter case, point `PYINTERP_PYTHON` at a different
Python:

```
PYINTERP_PYTHON=/path/to/other/venv/bin/python python main.py greet World
```

The other interpreter only needs `pygo_plugin` (for its pure-Python `server`/`plugin` modules - no compiled
extension required) and `rpyc` importable; it does not need `remote_greeter.py` installed anywhere special,
since `main.py` adds this example's own directory to the *plugin's* `sys.path` at runtime before importing it
there.
