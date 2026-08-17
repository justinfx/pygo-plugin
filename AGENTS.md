# AGENTS.md

This file provides guidance to agents (clade code, etc) when working with code in this repository.

## What this is

`pygo-plugin` is a Python port/binding of [hashicorp/go-plugin](https://github.com/hashicorp/go-plugin), the
plugin-over-RPC system used by Terraform, Vault, Nomad, Packer, etc. It lets a Python host process launch
plugin subprocesses (written in Go, Python, C++, or anything) and talk to them over gRPC as if they were local
objects. The project is alpha-quality (see Roadmap in README.md) and largely a solo/experimental effort.

## Architecture

The repo has two halves:

1. **Go host bindings (`go_plugin/client.go`)**: a small `package main` Go file, built with
   `go build -buildmode=c-shared` into a plain OS shared library (`src/pygo_plugin/_goplugin/libgoplugin.*`;
   this directory is git-ignored except for `__init__.py`/`README.txt`; the compiled library is a build artifact,
   not checked in). It exports a C ABI (`NewClient`, `FreeClient`, `ClientExited`, `ClientKill`, `ClientPing`,
   `ClientStart`, `ClientReattachConfig`, `FreeString`) over `hashicorp/go-plugin`'s `Client`/`ClientConfig`. The
   only Go value that needs to survive across separate calls is the running `*plugin.Client` itself (kill/exited/
   ping/start all operate on the same one), so it's the only thing kept alive across the cgo boundary, as a
   `runtime/cgo.Handle` (Go 1.17+, the standard library's mechanism for passing opaque references to Go values
   through C without violating cgo's pointer-passing rules). `Cmd`/`ClientConfig`/`ReattachConfig` never persist
   inside Go between calls: Python builds them up entirely on its own side and hands the whole thing to
   `NewClient` in one call, as a single JSON-encoded config string (`NewClient(configJSON *C.char, outError
   **C.char)`), decoded into `newClientRequest` on the Go side. This replaced an earlier ~20-parameter flat
   positional C signature: with that many same-typed scalar parameters (e.g. two adjacent `C.int`s for a
   reattach pid and a reattach test flag), a parameter landing in the wrong position on either side would
   silently corrupt the wrong field instead of failing loudly. One JSON blob turns that into a normal,
   catchable decode error, at the cost of a decode step that only ever runs once per `Client`, not per call.
   Every exported function that looks up a handle recovers from the panic `cgo.Handle.Value()` raises on an
   invalid/deleted handle (an unrecovered panic crossing an `//export`ed function is fatal to the whole process,
   not a catchable Python exception), and fallible calls report failure via a `char** outError` out-parameter
   rather than a shared/global error, since multiple `Client`s are launched concurrently from separate Python
   threads in practice (see `tests/pyinterp/test_pyinterp_concurrency.py`).
   Because this is a plain shared library that never touches the CPython C API, one compiled artifact works
   unmodified across Python versions; there's no per-Python-minor-version build matrix to maintain for it.
   - `pygo_plugin/_native.py` loads the compiled library via `cffi` (`ffi.dlopen(...)`, no compile step on the
     Python side) and exposes thin wrapper functions doing the string/array marshalling and error-to-exception
     conversion.
   - `pygo_plugin/client.py` builds the public API on top of `_native`: `Client`, `ClientConfig`, `Cmd`,
     `ReattachConfig` are all plain Python classes now (no Go-bound base class). `Client.dispense(name)` starts
     the plugin subprocess (via `_native.new_client`), performs the handshake, and returns a gRPC channel + stub
     for the requested plugin.
   - **`glibc` vs `musl`, dlopen, and static TLS: verified, not just assumed.** Any `-buildmode=c-shared` Go
     binary defines exactly one small TLS variable of its own (`runtime·tls_g`, used by `runtime.save_g`/
     `load_g` to preserve the goroutine pointer across cgo transitions; confirmed by inspecting the Go 1.24
     runtime source: linux/amd64 sets its `g`/`m` state via a raw `arch_prctl(ARCH_SET_FS)` syscall, not a
     compiler-managed TLS variable, so `tls_g` really is the only one). By default Go's linker/assembler emit
     this as an *initial-exec* model TLS access for `c-shared`/`c-archive` builds, a model that's only
     technically valid for libraries present at process start, not ones `dlopen`'d later (the Go team's own
     design doc for fixing this, `golang.org/design/71953-go-dynamic-tls.md`, states plainly: "the absence of a
     dynamic TLS model is generally benign with GlibC ... this shortcoming becomes problematic with the Musl C
     library"; see `golang.org/issue/54805`). Confirmed empirically against this project's actual compiled
     `go_plugin` (Debian bookworm/glibc vs. Alpine/musl containers, both linux/arm64, Go 1.24): on **glibc**,
     `cffi.dlopen()` succeeds and a full `NewClient` call (which creates a goroutine, exercising the exact
     `tls_g` code path) completes normally, and this project's CI (`ubuntu-latest`) and any mainstream glibc
     distro are unaffected. On **musl** (e.g. Alpine), `cffi.dlopen()` fails immediately and reproducibly with
     `OSError: ... initial-exec TLS resolves to dynamic definition in libgoplugin.so`, a real, documented
     limitation for anyone deploying into an Alpine-based Python image, not a bug in this project's own binding
     code, and not fixable here (fix is tracked upstream, arm64-first as of this writing per the design doc).
     **Not a new, migration-introduced risk**: `gopy` (this project's previous backend, `bind/gen.go` in its
     source) compiled the Go side with the exact same `go build -buildmode=c-shared`, then linked the result
     into the final `_goplugin.cpython-*.so` CPython extension via a plain `gcc --shared -fPIC`, same Go
     toolchain, same `tls_g` variable, same initial-exec model, just with an extra pybindgen glue layer.
     CPython's own import machinery loads extension modules via `dlopen()` internally
     (`Python/dynload_shlib.c`), the same OS mechanism `cffi`/`ctypes` call; confirmed by reproducing the exact
     same musl failure with plain `ctypes.CDLL(...)` in the same container, no `cffi` involved. This was always
     a latent risk for a musl deployment; the cffi/c-shared migration didn't create it, it was just never
     exercised (no evidence this project has ever been deployed on musl). If musl support is ever needed,
     revisit `golang.org/issue/54805` for whether the general-dynamic TLS model has landed by then.
   - **Unrelated portability fix found while verifying the above:** the cgo preamble originally only
     `#include <stdlib.h>`. `uintptr_t` (used in every exported function's C signature) happened to be visible
     anyway on macOS, because Darwin's `<stdlib.h>` transitively pulls in `<stdint.h>`, but this is not
     guaranteed by the C standard and does not hold on glibc, where the same build fails outright
     (`could not determine what C.uintptr_t refers to`). Fixed by adding an explicit
     `#include <stdint.h>`. This was caught by actually building for Linux in a container while investigating
     the TLS question above, not by any glibc-targeted CI run; worth remembering if `client.go`'s cgo preamble
     is ever touched again: macOS building successfully does not prove a change is Linux-portable.

2. **Python plugin server (`pygo_plugin/server.py`)**: a *pure Python* reimplementation of go-plugin's server
   side (not generated/bound from Go). `ServeConfig`/`Server`/`serve()` start a `grpc.server`, register a health
   service, a `GRPCControllerServicer` (graceful shutdown, invoked by the Go client), optionally gRPC reflection,
   bind to a Unix domain socket (POSIX) or a TCP port in `$PLUGIN_MIN_PORT`-`$PLUGIN_MAX_PORT` (other platforms),
   and print the go-plugin handshake line (`proto_ver|app_proto_ver|network|endpoint|grpc`) to stdout; this is
   the line the Go/Python client parses to connect. This lets Python processes act as plugins servable to any
   go-plugin-compatible host, not just this library's client.

Shared abstraction: `pygo_plugin/plugin.py` defines the `Plugin` ABC (`client_class()`, `server_register()`)
that both a plugin author (server side) and plugin consumer (host side) implement/use. A single `Plugin`
subclass is meant to be usable from both ends; see `tests/calc/calc_plugin.py` for the canonical minimal
example, and `src/pygo_plugin/_examples/kv/` for a fuller cross-language example (Go/Python/C++ plugin
implementations of the same key/value gRPC service, driven by a Python host in `_examples/kv/main.py`).

`pygo_plugin/proto/` contains the vendored go-plugin gRPC service protos (`grpc_broker`, `grpc_controller`,
`grpc_stdio`) plus their generated `_pb2`/`_pb2_grpc` Python modules. `grpc_broker` and `grpc_stdio` are vendored
for protocol compatibility but are not yet wired up (bidirectional communication / stdio syncing are open
roadmap items, see README "Roadmap").

`pygo_plugin/utils.py` has one helper, `find_free_port()`, used by the server for TCP port allocation.

`pygo_plugin/__init__.py` re-exports the public API from `plugin` and `server` eagerly (`import *`), and
`Client`/`ClientConfig`/`Cmd` lazily via a module-level `__getattr__`; see "Lazy `.client` import" below.

### Build pipeline (`pyproject.toml` + `setup.py`)

All static packaging metadata (name, version, dependencies, classifiers, `packages`/`package_data`, etc.) lives
in `pyproject.toml`. `setup.py` only exists for the custom setuptools `Command`s that shell out to external
tools (nothing declarative can express "compile this with Go"), wired in via `cmdclass` on an otherwise
metadata-free `setup()` call. `build_py` is overridden to run two of them automatically before every
build/install:
- `grpc` (`GrpcGenTool`): runs `grpc_tools.protoc` over `src/pygo_plugin/proto/*.proto` to (re)generate the
  `_pb2`/`_pb2_grpc` files in place.
- `go_build` (`GoBuildTool`): runs `go build -buildmode=c-shared -o .../libgoplugin.<so|dylib|dll> ./go_plugin`,
  then (when run as part of `build_py`) copies the result into the build dir. Requires only `go` on `PATH`, no
  pinned-tool bootstrap step, since there's no `gopy`/`goimports` involved anymore.
  Set `PYGO_PLUGIN_SKIP_NATIVE_BUILD=1` to skip this step for a plugin-only environment (e.g. a `pyinterp`
  plugin subprocess venv) that never imports `pygo_plugin.client` and has no use for the compiled library.
  `grpc` still runs in that case.

`grpcio-tools` (imported/used only by `GrpcGenTool` above, never at runtime) is declared in
`[build-system] requires`, not `[project.dependencies]`; this means a plain, isolated `pip install .` correctly
provisions pip's own build venv with everything the custom commands need and just works. For local iteration,
`pip install -e . --no-build-isolation` is still faster (skips recreating pip's build venv on every reinstall),
but is no longer required the way it once was before `[build-system] requires` existed. `cffi` (how
`pygo_plugin._native` loads the compiled library) is a genuine runtime dependency, declared in
`[project.dependencies]` instead.

`setup.py` was ported off `distutils` to plain `setuptools` (Sept 2026 modernization) so it runs fine on
Python 3.12+; `pkg_resources` (also gone from modern setuptools) was replaced with `importlib.resources` for
locating the vendored grpc proto includes.

### Lazy `.client` import (`pygo_plugin/__init__.py`)

`Client`/`ClientConfig`/`Cmd`/`ReattachConfig` live in `pygo_plugin.client`, which loads the compiled native
library (`src/pygo_plugin/_goplugin/libgoplugin.*`) via `pygo_plugin._native`. Only the host side ever needs
those names; a plugin subprocess (e.g. `pygo_plugin.pyinterp`'s `__main__` entry point, or
`tests/calc/calc_plugin.py` run standalone) only needs `pygo_plugin.plugin`/`.server`, and must not be forced to
have the compiled library present just because it did `import pygo_plugin`. A module-level `__getattr__`
(PEP 562) in `__init__.py` defers importing `.client` until `Client`/`ClientConfig`/`Cmd`/`ReattachConfig` is
actually accessed, caching the result on first access. This originally worked around "the compiled extension is
built for one specific CPython ABI"; the later cffi/c-shared migration eliminated that constraint at the root
instead of just working around it: a plugin-only environment still doesn't need the native library at all, but
now *any* Python version's host can use the one compiled library, not just the one it was built against.
`pygo_plugin.HandshakeConfig` (defined in `plugin.py`) is no longer a "related but separate fix" needing its own
conversion path; with no Go-bound Python type left at all, it's simply the one and only representation, used
as-is on both the host and plugin side.

## Bootstrapping an environment

Requires Go >= 1.24 and Python >= 3.9 (tested against 3.12). Confirmed working on macOS arm64 with the Homebrew
Python 3.12 framework build.

`./scripts/bootstrap.sh` runs the steps below in one shot for a first-time setup; they're spelled out here too
since they're short and rarely need changing:

```bash
# 1. Create and activate a virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 2. Build + install (a C compiler is needed on Linux for cgo, e.g.
#    `sudo apt install build-essential`; go on PATH is the only other
#    external requirement, unlike the old gopy-based pipeline, since no
#    Python development headers are needed: the compiled library
#    is a plain OS shared library, not a CPython extension).
#    Runs proto codegen + the Go c-shared library build automatically:
#    the build-time-only tool (grpcio-tools) is provisioned into pip's
#    own isolated build venv via pyproject.toml's [build-system]
#    requires, so this needs no other setup:
pip install .
# or, editable install for hacking on the source: faster to reinstall
# since it skips recreating pip's isolated build venv each time:
pip install -e . --no-build-isolation
# with the test extra, if you also want pytest:
pip install -e ".[test]" --no-build-isolation

# Rebuild just the generated bindings after changing go_plugin/*.go or *.proto files
python setup.py build_py

# 3. Run tests
python -m pytest ./tests
```

`protobuf`/`grpcio*` are no longer version-pinned (previously pinned to `protobuf==3.*`, which predates the
current protobuf runtime); regenerating `*_pb2*.py` files with the installed `grpcio-tools` keeps them in sync.
If you regenerate a `.proto` by hand instead of via `python setup.py grpc`, pass `-I` so the generated import
matches the existing style in that file (e.g. `tests/calc/plugin_pb2_grpc.py` imports as `from calc import
plugin_pb2`, which requires `protoc -Itests`, not `-I.` from repo root: the include root determines the
generated import path).

## Common commands

```bash
# One-shot first-time setup: creates .venv, installs pygo-plugin editable, runs tests
./scripts/bootstrap.sh

# Regenerate just the vendored proto -> Python bindings
python setup.py grpc

# Compile go_plugin/ into the native shared library
python setup.py go_build

# Run the full test suite
python -m pytest ./tests

# Run a single test
python -m pytest ./tests/test_plugin.py::test_plugin_call

# Run the KV example (from src/pygo_plugin/_examples/kv/)
export KV_PLUGIN='./kv_plugin_go/kv_plugin_go'   # or kv_plugin_py/kv_plugin.py, or the C++ binary
python ./main.py get foo
python ./main.py put foo value
```

## Notes when modifying code

- Changes to `go_plugin/client.go` require recompiling the native library (`python setup.py build_py` or
  `go_build`) before Python code will see the change; there is no auto-reload, and
  `src/pygo_plugin/_goplugin/` contents besides `__init__.py`/`README.txt` are build output, not source to edit
  directly. Any new `//export`ed function also needs a matching entry added to `_CDEF` in
  `src/pygo_plugin/_native.py`: cffi's `cdef` is hand-written, not generated from the Go source.
- Changes to any `*.proto` file under `src/pygo_plugin/proto/` require regenerating with `python setup.py grpc`
  (or the direct `grpc_tools.protoc` invocation shown in comments in `_examples/kv/main.py`); the `_pb2*.py`
  files are checked in but generated, not hand-written.
- A `Plugin` subclass (`pygo_plugin.Plugin`) is the integration point for a new plugin type: implement
  `client_class()` (returns the gRPC stub class for the host side) and `server_register(server)` (registers the
  servicer implementation for the plugin side). `tests/calc/calc_plugin.py` is the smallest complete example of
  both halves plus the required `handshake_config()`.
- The codebase is Python 3-only now (the `future`/Python 2 compat shim in `plugin.py` was removed in favor of
  plain `abc.ABC`); the various `from __future__ import ...` lines elsewhere are inert leftovers, not load-bearing.
