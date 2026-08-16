#!/usr/bin/env python
"""
Minimal example of pygo_plugin.pyinterp: a host launching a second Python
interpreter as a plugin subprocess and getting back a live, transparent
proxy into it. No custom Plugin/proto implementation required, unlike the
../kv/ example (which needs one per plugin language).

Usage:
    python main.py sqrt 16
    python main.py greet World
"""

from __future__ import absolute_import, print_function

import logging
import os
import sys

import pygo_plugin
from pygo_plugin import pyinterp


def main():
    # Choose which interpreter to launch as the plugin subprocess from an
    # env var. Left unset, pyinterp.connect() defaults to this same
    # interpreter for a zero-setup demo; point it at a venv with a
    # different Python version or dependency graph (e.g.
    # PYINTERP_PYTHON=/path/to/other/venv/bin/python) to see the actual
    # point of pyinterp: talking to a plugin the host process structurally
    # could not import directly. A bare name (e.g. "python3.9") also
    # resolves via PATH, not just an absolute path.
    plugin_python = os.environ.get('PYINTERP_PYTHON')

    try:
        action = sys.argv[1]
    except IndexError:
        print("Usage: <sqrt|greet> <arg>")
        sys.exit(1)

    # We're a host. pyinterp.connect() handles the RpycInterpPlugin setup
    # dance (ClientConfig/Cmd/prepare_cmd/dispense) and, as a context
    # manager, the teardown (conn.close()/client.kill()) too.
    with pyinterp.connect(python=plugin_python) as (client, conn):
        if action == 'sqrt':
            try:
                number = float(sys.argv[2])
            except (IndexError, ValueError):
                print("Usage: sqrt <number>")
                sys.exit(1)
            # math.sqrt runs IN the plugin subprocess, not here. Proves
            # basic remote stdlib module access works.
            result = conn.modules['math'].sqrt(number)
            print("sqrt({}) -> {} (computed in plugin pid {})".format(
                number, result, conn.modules['os'].getpid()))

        elif action == 'greet':
            try:
                name = sys.argv[2]
            except IndexError:
                print("Usage: greet <name>")
                sys.exit(1)
            # remote_greeter.py is never imported by this host process;
            # only the plugin subprocess needs it, so we add this
            # directory to the *remote* sys.path and import it there.
            here = os.path.dirname(os.path.abspath(__file__))
            conn.modules.sys.path.append(here)
            greeting = conn.modules['remote_greeter'].greet(name)
            print(greeting)

        else:
            print("Please provide either 'sqrt' or 'greet' as first arg")
            sys.exit(1)


if __name__ == '__main__':
    logging.basicConfig()
    main()
