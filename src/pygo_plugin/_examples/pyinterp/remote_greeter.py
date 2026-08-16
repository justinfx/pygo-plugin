"""
Only needs to exist in the plugin subprocess's interpreter. main.py (the
host) never imports it directly, only reaches it via conn.modules(...).
Stands in for a real third-party library the host can't import itself.
"""
from __future__ import absolute_import

import platform


def greet(name):
    return "Hello, {}! This greeting was generated on Python {} in the plugin subprocess.".format(
        name, platform.python_version())
