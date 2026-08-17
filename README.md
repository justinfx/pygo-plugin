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

* [ ] Tests ([#3](https://github.com/justinfx/pygo-plugin/issues/3))
* [ ] Documentation ([#4](https://github.com/justinfx/pygo-plugin/issues/4))
* [ ] Additional examples ([#5](https://github.com/justinfx/pygo-plugin/issues/5)) 

Feature parity with [hashicorp/go-plugin](https://github.com/hashicorp/go-plugin):

* [X] `Client` and related python API classes wrap `hashicorp/go-plugin` for initial host support
* [X] Initial `Server` and configuration python API
* [X] Vendored go-plugin server proto files
* [X] Server reflection and controller service (graceful shutdown)
* [X] Server min/max TCP port support
* [ ] **Bidirectional communication:** ([#11](https://github.com/justinfx/pygo-plugin/issues/11)) Because the plugin system supports
  complex arguments, the host process can send it interface implementations, and the 
  plugin can call back into the host process.
* [ ] **Stdout/Stderr Syncing**: ([#7](https://github.com/justinfx/pygo-plugin/issues/7)) While plugins are subprocesses, they can continue
  to use stdout/stderr as usual, and the output will get mirrored back to
  the host process. The host process can control what `io.Writer` these
  streams go to prevent this from happening.
* [ ] **Cryptographically Secure Plugins**: ([#9](https://github.com/justinfx/pygo-plugin/issues/9)) Plugins can be verified with an expected
  checksum and RPC communications can be configured to use TLS. The host process
  must be properly secured to protect this configuration.
* [ ] Implement the stdio RPC service for python plugins ([#7](https://github.com/justinfx/pygo-plugin/issues/7))
* [ ] Support TLS connections for host client, and in python plugins ([#9](https://github.com/justinfx/pygo-plugin/issues/9))
* [ ] Support Auto mTLS feature in python plugins ([#8](https://github.com/justinfx/pygo-plugin/issues/8))
* [ ] Support versioned plugins check in python plugins ([#10](https://github.com/justinfx/pygo-plugin/issues/10))

## Architecture

See [hashicorp/go-plugin](https://github.com/hashicorp/go-plugin) for general plugin
system architecture.

The host (client) python implementation uses a binding over `hashicorp/go-plugin` to load and
manage the lifecycle of plugins as subprocesses. The Go side is compiled as a plain OS shared
library (`go build -buildmode=c-shared`) and called from Python via
[`cffi`](https://cffi.readthedocs.io/). It never touches the CPython C API, so the compiled
library works unmodified across Python versions, unlike a typical CPython extension module.

The server (plugin) python implementation is a pure port of the equivalent Go library. This
helps to extend support to Python plugins for more easily serving the plugin, syncing 
stdout/stderr and logging output, graceful shutdowns, protocol and version checking, TLS, and
so on. As per go-plugin documentation, plugins can be written in any language without a specific
server implementation, but do not automatically gain these extended features.

## Requirements

Building the pygo-plugin library requires a recent version of the [Go compiler](https://golang.org) (>= 1.24)
and Python >= 3.9.

A C compiler is required on Linux for `cgo` to build the shared library:

```
sudo apt install build-essential
```

No Python development headers are required: the compiled library is a plain OS shared library, not a CPython
extension.

For a one-shot dev setup (creates a virtualenv, installs pygo-plugin editable, runs the tests), run
`./scripts/bootstrap.sh`. Otherwise, the same steps by hand:

```
# Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# Install pygo-plugin (builds proto codegen + the Go native shared library automatically)
pip install .

# or... to hack on the source, with pytest included
pip install -e ".[test]" --no-build-isolation
# and rebuild the bindings after changing go_plugin/*.go or *.proto files
python setup.py build_py  
# run tests
python -m pytest ./tests
```

## Usage

To use the plugin system, you must take the following steps. These are
high-level steps that must be done. Examples are available in the
[src/pygo_plugin/_examples](src/pygo_plugin/_examples/) directory.

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

## `pyinterp`: a built-in Python-to-Python interpreter plugin

`pygo_plugin.pyinterp` ships as a ready-to-use `Plugin` implementation: no
proto file, no custom gRPC service, no plugin-side code to write. Point it
at any Python interpreter and get back a live, transparent proxy into that
interpreter from your host process.

### What problem it solves

A Python **host** process sometimes cannot simply `import` a library it
needs, because:

- the library only supports a different Python version than the host process is running,
- the library's dependency graph conflicts with the host's own (pinned
  versions, native extensions, etc.), or
- the library only exists inside an isolated/managed environment (e.g. a
  studio package-management system) that the host doesn't have direct
  access to.

`pyinterp` solves this by launching a second interpreter, any interpreter,
any venv, as a `pygo-plugin` plugin subprocess, and handing back a live
object proxy into it, so the host can call into that library as if it were
local, without ever importing it directly.

Running the library in its own subprocess also brings some operational
benefits for free:

- **Crash containment.** A fatal error in the library (a native extension
  segfault, an interpreter-level crash) takes down only the plugin
  subprocess, not the host.
- **Full memory reclamation.** Large in-process caches or native
  allocations that don't always give memory back to the OS, even after
  Python's own garbage collector runs, are cleared for good the moment the
  plugin subprocess is killed, the way unloading an in-process module
  never really can.
- **Live version swaps.** The interpreter/venv is chosen at connect time
  (`pyinterp.connect(python=...)`), so pointing it at an updated venv and
  restarting the plugin subprocess picks up a new version of the library
  on the fly, without restarting the host process itself.

### High-level architecture

- **Control plane**: ordinary `pygo-plugin` machinery, unchanged, process
  launch, handshake, health check, graceful shutdown. `pyinterp` is just
  another `Plugin` implementation.
- **Data plane**: rather than exposing a custom gRPC service, `pyinterp`
  opens a second, [RPyC](https://github.com/tomerfiliba-org/rpyc)-based
  side-channel connection directly between host and plugin subprocess (the
  host chooses the endpoint and hands it to the subprocess via a single
  environment variable). All object-proxy traffic (attribute access,
  method calls, callbacks) goes over this channel, using RPyC's mature
  `ClassicService` implementation rather than reinventing it.
- This sidesteps needing `go-plugin`'s bidirectional `grpc_broker` (still
  unimplemented in this project, see Roadmap) for the Python-to-Python
  case: RPyC already provides bidirectional calls natively.
- Scope: Python **host** talking to a Python **plugin subprocess**. RPyC's
  wire protocol is Python-specific, so this does not extend to non-Python
  plugin languages the way the rest of `pygo-plugin` does.

### Usage

```python
from pygo_plugin import pyinterp

with pyinterp.connect(python="/path/to/other/venv/bin/python") as (client, conn):
    result = conn.modules['numpy'].array([1, 2, 3]).sum()
```

`pyinterp.connect()` handles the whole setup/teardown dance (launching the
subprocess, handshake, RPyC connect, closing the connection and killing the
subprocess on exit) in one call. `python` may be an absolute path, a bare
executable name resolved via `PATH`, or omitted entirely to default to the
current interpreter. See
[src/pygo_plugin/_examples/pyinterp](src/pygo_plugin/_examples/pyinterp)
for a runnable example.

### What you get back: the `conn` object

`conn` is a live [RPyC](https://rpyc.readthedocs.io/) classic `Connection`.
Its full API is available; the parts most relevant to `pyinterp` are:

- **`conn.modules['some.module']`** (or `conn.modules.some_module`)
  imports and returns a proxy to a module inside the plugin subprocess, on
  demand. Nothing on the host needs to import it, and no plugin-side code
  needs to pre-register it, this is a generic remote import, not anything
  specific to `pyinterp`'s own server code.
- **Live proxies ("netrefs"), not copies.** Objects returned from remote
  calls stay in the plugin subprocess. Attribute access and method calls
  on them are dispatched back over the wire automatically, so a mutation
  (e.g. `remote_list.append(4)`) really happens in the plugin subprocess,
  and every subsequent access reflects it.
- **Automatic reference counting.** Dropping the last local reference to a
  proxy tells the plugin subprocess to release the corresponding object.
  No manual handle management.
- **Bidirectional calls, for free.** A host-side callable can be passed
  into a remote call and be invoked *by* the plugin subprocess (e.g. as a
  callback), with no extra setup. This project's own gRPC-based plugins
  don't otherwise support this (see the `grpc_broker` item in the
  Roadmap).
- **`conn.eval("expr")` / `conn.execute("statements")`** run arbitrary
  expressions or statements directly in the plugin subprocess's own
  namespace (`conn.namespace`), for cases a normal proxied call doesn't
  fit well. This is real code execution in the remote process, so treat a
  `pyinterp` plugin as running in the same trust domain as the host (a
  different venv/version, not a sandbox), not as an isolation boundary
  against untrusted code.

RPyC's exception-marshalling caveats, netref lifecycle edge cases, and the
rest of its API are intentionally not duplicated here, see RPyC's own docs
for the full picture.

