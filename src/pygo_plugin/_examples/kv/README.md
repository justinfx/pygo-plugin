# KV Plugin Example

This is an example of a host application accessing a simple key/value store, implemented as a plugin
in various languages.

Based on: https://github.com/hashicorp/go-plugin/tree/master/examples/grpc

## Build

### Go

Requires an installed Go compiler.

```
cd kv_plugin_go
go build
```

### C++

Requires cmake, libgrpc, and protobuf compiler.

```
cd kv_plugin_cpp
cmake .
make
```

## Usage

The client looks for the environment variable `KV_PLUGIN` to choose which plugin executable to load.

Python plugin

```
export KV_PLUGIN='./kv_plugin_py/kv_plugin.py'
python ./main.py get foo
python ./main.py put foo value
```

Go plugin

```
export KV_PLUGIN='./kv_plugin_go/kv_plugin_go'
#...
```

C++ plugin

```
export KV_PLUGIN='./kv_plugin_cpp/kv_plugin_cpp'
#...
```