#!/usr/bin/env python

from __future__ import absolute_import, print_function

import sys
import time

import pygo_plugin
from pygo_plugin._examples.kv.shared import kv_plugin


def serve():
    cfg = pygo_plugin.ServeConfig()
    cfg.handshake_config = kv_plugin.handshake_config()
    cfg.plugins['kv'] = kv_plugin.KVPlugin()

    try:
        pygo_plugin.serve(cfg)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == '__main__':
    import logging
    logging.basicConfig(level=logging.INFO)
    serve()
