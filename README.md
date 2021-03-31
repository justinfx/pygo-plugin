# Python Plugin System over gRPC 

This project is a port/wrapper over [github.com/hashicorp/go-plugin](https://github.com/hashicorp/go-plugin), 
that implements the client (host) in Python, as opposed to Go.

## The `hashicorp/go-plugin` project

`go-plugin` is a Go (golang) plugin system over RPC. It is the plugin system
that has been in use by HashiCorp tooling for over 4 years. While initially
created for [Packer](https://www.packer.io), it is additionally in use by
[Terraform](https://www.terraform.io), [Nomad](https://www.nomadproject.io), and
[Vault](https://www.vaultproject.io).

While the plugin system is over RPC, it is currently only designed to work
over a local [reliable] network. Plugins over a real network are not supported
and will lead to unexpected behavior.

This plugin system has been used on millions of machines across many different
projects and has proven to be battle hardened and ready for production use.

## `pygo-plugin` Features

Like [hashicorp/go-plugin](https://github.com/hashicorp/go-plugin), this system supports a 
number of features:

**Plugins are gRPC interface implementations.**  
For a plugin author: you just implement an interface as if it were going to run in  
the same process.  
For a plugin user: you just use and call functions on an interface as if it 
were in the same process.  
This plugin system handles the communication in between.

**Cross-language support.** Plugins can be written (and consumed) by
almost every major language. This library supports serving plugins via
[gRPC](http://www.grpc.io). gRPC-based plugins enable plugins to be written
in any language.

**Built-in Logging.** Any plugins that use the `log` standard library
will have log data automatically sent to the host process. The host
process will mirror this output prefixed with the path to the plugin
binary. This makes debugging with plugins simple.

**Protocol Versioning.** A very basic "protocol version" is supported that
can be incremented to invalidate any previous plugins. This is useful when
interface signatures are changing, protocol level changes are necessary,
etc. When a protocol version is incompatible, a human friendly error
message is shown to the end user.

**TTY Preservation.** Plugin subprocesses are connected to the identical
stdin file descriptor as the host process, allowing software that requires
a TTY to work. For example, a plugin can execute `ssh` and even though there
are multiple subprocesses and RPC happening, it will look and act perfectly
to the end user.

**Host upgrade while a plugin is running.** Plugins can be "reattached"
so that the host process can be upgraded while the plugin is still running.
This requires the host/plugin to know this is possible and daemonize
properly. `Client` takes a `ReattachConfig` to determine if and how to
reattach.


## Roadmap

This project is in early stages as is currently considered "alpha". 

* [ ] Tests
* [ ] Documentation 
* [ ] Additional examples 

Feature parity with [hashicorp/go-plugin](https://github.com/hashicorp/go-plugin):

* [X] `Client` and related python API classes wrap `hashicorp/go-plugin` for initial host support
* [X] Initial `Server` and configuration python API
* [X] Vendored go-plugin server proto files
* [X] Server reflection and controller service (graceful shutdown)
* [X] Server min/max TCP port support
* [ ] **Bidirectional communication:** Because the plugin system supports
  complex arguments, the host process can send it interface implementations, and the 
  plugin can call back into the host process.
* [ ] **Stdout/Stderr Syncing**: While plugins are subprocesses, they can continue
  to use stdout/stderr as usual, and the output will get mirrored back to
  the host process. The host process can control what `io.Writer` these
  streams go to prevent this from happening.
* [ ] **Cryptographically Secure Plugins**: Plugins can be verified with an expected
  checksum and RPC communications can be configured to use TLS. The host process
  must be properly secured to protect this configuration.
* [ ] Implement the stdio RPC service for python plugins
* [ ] Support TLS connections for host client, and in python plugins
* [ ] Support Auto mTLS feature in python plugins
* [ ] Support versioned plugins check in python plugins

## Architecture

See [hashicorp/go-plugin](https://github.com/hashicorp/go-plugin) for general plugin
system architecture.

The host (client) python implementation uses a binding over `hashicorp/go-plugin` to load and
manage the lifecycle of plugins as subprocesses. Bindings are generated using 
[go-python/gopy](https://github.com/go-python/gopy).

The server (plugin) python implementation is a pure port of the equivalent Go library. This
helps to extend support to Python plugins for more easily serving the plugin, syncing 
stdout/stderr and logging output, graceful shutdowns, protocol and version checking, TLS, and
so on. As per go-plugin documentation, plugins can be written in any language without a specific
server implementation, but do not automatically gain these extended features.

## Requirements

Building the pygo-plugin library requires a recent version of the [Go compiler](https://golang.org) (>= 1.15).

The python development headers are required to compile the python extension module. On linux:

```
sudo apt install libpython3-dev build-essential 
```

The `gopy` and `goimports` tools must also be installed, to support generating the bindings from Go to Python:

```
go get golang.org/x/tools/cmd/goimports
go get github.com/go-python/gopy@master
```

After these tools are available, the build script will be able to generate bindings, and run the protobuf code
generation.

```
# Install python dependencies.
pip install -r requirements.txt

# Install pygo
python setup.py install

# or... to hack on the source
python setup.py develop  
```

## Usage

To use the plugin system, you must take the following steps. These are
high-level steps that must be done. Examples are available in the
[pygo_plugin/_examples](pygo_plugin/_examples/) directory.

  1. Write the gRPC Protocol Buffers interface that you want to expose for plugins.

  2. For each interface, implement an implementation of that gRPC proto
     that communicates over a [gRPC](http://www.grpc.io) connection. You'll have to implement
     both a client and server implementation.

  3. Create a `Plugin` class implementation that knows how to create the RPC
     client/server for a given plugin type.

  4. Plugin authors call `pygo_plugin.serve` to serve a plugin from the
     `main` function.

  5. Plugin users use `pygo_plugin.Client` to launch a subprocess and request
     an interface implementation over RPC.


