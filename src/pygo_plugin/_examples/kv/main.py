#!/usr/bin/env python

from __future__ import absolute_import, print_function

import logging
import os
import sys

import pygo_plugin
from pygo_plugin._examples.kv.shared import kv_plugin

# generated from our kv.proto, from project root
#   python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. ./pygo_plugin/_examples/kv/shared/kv.proto
from pygo_plugin._examples.kv.shared import kv_pb2, kv_pb2_grpc


def main():
    # Choose which plugin to load from an env var.
    # If not defined, default to the Go plugin implementation.
    kv_plugin_cmd = os.environ.get("KV_PLUGIN")
    if not kv_plugin_cmd:
        root = os.path.dirname(os.path.abspath(__file__))
        kv_plugin_cmd = os.path.join(root, 'kv_plugin_go/kv_plugin_go')

    # Check args to determine which action to perform over plugin RPC
    try:
        action, key = sys.argv[1:3]
    except ValueError:
        print("Usage: <get|put> <key> [value]")
        sys.exit(1)

    if action == 'put':
        try:
            value = sys.argv[3]
        except IndexError:
            print("Usage: put <key> <value>")
            sys.exit(1)

    # We're a host. Create a client config that can launch the plugin process
    cfg = pygo_plugin.ClientConfig()
    cfg.plugins['kv'] = kv_plugin.KVPlugin()
    cfg.set_cmd(kv_plugin_cmd)

    # Used to agree with the plugin on being
    cfg.handshake_config = kv_plugin.handshake_config()

    client = pygo_plugin.Client(cfg)

    # Request the plugin interface
    channel, kv = client.dispense('kv')

    # We should have a KV store now! This feels like a normal local
    # interface but it is in fact an RPC connection
    with channel:
        if action == 'get':
            resp = kv.Get(kv_pb2.GetRequest(key=key))
            print("Get({}) -> {}".format(key, resp.value))

        elif action == 'put':
            kv.Put(kv_pb2.PutRequest(key=key, value=value.encode('utf8')))
            print("Put({}, {})".format(key, value))

        else:
            print("Please provide either 'get' or 'put' as first arg")
            sys.exit(1)


if __name__ == '__main__':
    logging.basicConfig()
    main()
