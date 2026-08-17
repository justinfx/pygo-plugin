// Command go_plugin builds as a C shared library (-buildmode=c-shared)
// exposing a small C ABI over hashicorp/go-plugin's Client, consumed from
// Python via cffi (see src/pygo_plugin/_native.py). The compiled library
// never touches the CPython C API, so it is not tied to any particular
// Python version or ABI.
//
// Only *plugin.Client needs to survive across separate calls (kill/exited/
// ping/start all operate on the same running client), so it is the only
// value kept alive across the cgo boundary, via runtime/cgo.Handle, the
// standard library's mechanism (Go 1.17+) for passing opaque references to
// Go values through C without violating cgo's pointer-passing rules. Cmd,
// ClientConfig and ReattachConfig never need to persist inside Go between
// calls: Python builds them up entirely on its own side and hands the
// whole thing to NewClient in one call.
package main

// #include <stdlib.h>
// #include <stdint.h>
import "C"

import (
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os/exec"
	"runtime/cgo"
	"time"
	"unsafe"

	plugin "github.com/hashicorp/go-plugin"
)

func main() {}

// simpleAddr is a minimal net.Addr for reconstructing a ReattachConfig's
// Addr from the network/address strings Python provides. go-plugin only
// ever calls Network()/String() on it (to pick unix vs tcp dialing and get
// the address to dial), so a full net.UnixAddr/net.TCPAddr isn't needed,
// which also avoids the syscalls/errors net.Resolve*Addr could introduce.
type simpleAddr struct {
	network string
	address string
}

func (a simpleAddr) Network() string { return a.network }
func (a simpleAddr) String() string  { return a.address }

// string/error marshalling helpers

func goString(s *C.char) string {
	if s == nil {
		return ""
	}
	return C.GoString(s)
}

func setOutError(out **C.char, err error) {
	if out != nil && err != nil {
		*out = C.CString(err.Error())
	}
}

func setOutString(out **C.char, s string) {
	if out != nil {
		*out = C.CString(s)
	}
}

//export FreeString
func FreeString(s *C.char) {
	C.free(unsafe.Pointer(s))
}

// Client handle lookup

// clientFromHandle safely resolves a Client handle, recovering from the
// panic cgo.Handle.Value() raises for an invalid/deleted handle. A panic
// escaping an //export'ed function is fatal to the whole process rather
// than a catchable Python exception, so every handle lookup below goes
// through this instead of calling cgo.Handle.Value() directly.
func clientFromHandle(h C.uintptr_t) (c *plugin.Client, ok bool) {
	defer func() {
		if recover() != nil {
			c, ok = nil, false
		}
	}()
	v := cgo.Handle(h).Value()
	c, ok = v.(*plugin.Client)
	return
}

const invalidHandleErr = "invalid or already-freed Client handle"

// NewClient / FreeClient

// handshakeParams, cmdParams and reattachParams mirror plugin.HandshakeConfig,
// exec.Cmd and plugin.ReattachConfig closely enough to decode directly off
// the wire; newClientRequest is the single JSON document NewClient accepts.
// Using one JSON blob instead of ~20 flat positional C parameters removes
// an entire class of bug (a same-typed parameter landing in the wrong
// position silently corrupts the wrong field) in exchange for a decode
// step that only ever runs once per Client, not per call.
type handshakeParams struct {
	ProtocolVersion  uint   `json:"protocol_version"`
	MagicCookieKey   string `json:"magic_cookie_key"`
	MagicCookieValue string `json:"magic_cookie_value"`
}

type cmdParams struct {
	Path string   `json:"path"`
	Args []string `json:"args"`
	Env  []string `json:"env"`
	Dir  string   `json:"dir"`
}

type reattachParams struct {
	Protocol string `json:"protocol"`
	Network  string `json:"network"`
	Address  string `json:"address"`
	Pid      int    `json:"pid"`
	Test     bool   `json:"test"`
}

type newClientRequest struct {
	Handshake        handshakeParams `json:"handshake"`
	Cmd              *cmdParams      `json:"cmd"`
	Reattach         *reattachParams `json:"reattach"`
	MinPort          uint            `json:"min_port"`
	MaxPort          uint            `json:"max_port"`
	StartTimeoutMsec int64           `json:"start_timeout_msec"`
	AutoMTLS         bool            `json:"auto_mtls"`
}

// NewClient returns 0 (an invalid cgo.Handle, per its own documented
// invariant) with outError set if configJSON fails to parse; Python checks
// for a 0 return the same way it checks any other outError-reporting call.
//
//export NewClient
func NewClient(configJSON *C.char, outError **C.char) C.uintptr_t {
	var req newClientRequest
	if err := json.Unmarshal([]byte(goString(configJSON)), &req); err != nil {
		setOutError(outError, fmt.Errorf("invalid NewClient config: %w", err))
		return 0
	}

	cfg := &plugin.ClientConfig{
		HandshakeConfig: plugin.HandshakeConfig{
			ProtocolVersion:  req.Handshake.ProtocolVersion,
			MagicCookieKey:   req.Handshake.MagicCookieKey,
			MagicCookieValue: req.Handshake.MagicCookieValue,
		},
		Plugins:          map[string]plugin.Plugin{},
		MinPort:          req.MinPort,
		MaxPort:          req.MaxPort,
		StartTimeout:     time.Duration(req.StartTimeoutMsec) * time.Millisecond,
		AllowedProtocols: []plugin.Protocol{plugin.ProtocolGRPC},
		AutoMTLS:         req.AutoMTLS,
	}

	if req.Cmd != nil && req.Cmd.Path != "" {
		cfg.Cmd = &exec.Cmd{
			Path: req.Cmd.Path,
			Args: req.Cmd.Args,
			Env:  req.Cmd.Env,
			Dir:  req.Cmd.Dir,
		}
	} else if req.Reattach != nil {
		protocol := req.Reattach.Protocol
		if protocol == "" {
			protocol = string(plugin.ProtocolGRPC)
		}
		cfg.Reattach = &plugin.ReattachConfig{
			Protocol: plugin.Protocol(protocol),
			Addr: simpleAddr{
				network: req.Reattach.Network,
				address: req.Reattach.Address,
			},
			Pid:  req.Reattach.Pid,
			Test: req.Reattach.Test,
		}
	}

	client := plugin.NewClient(cfg)
	return C.uintptr_t(cgo.NewHandle(client))
}

//export FreeClient
func FreeClient(handle C.uintptr_t) {
	// Deleting an already-deleted (or never-valid) Handle panics; recover
	// so a double-free from Python (e.g. a defensive __del__) is a no-op,
	// not a process crash.
	defer func() { recover() }()
	cgo.Handle(handle).Delete()
}

// Client methods

//export ClientExited
func ClientExited(handle C.uintptr_t) C.int {
	c, ok := clientFromHandle(handle)
	if !ok {
		return 1
	}
	if c.Exited() {
		return 1
	}
	return 0
}

//export ClientKill
func ClientKill(handle C.uintptr_t) {
	c, ok := clientFromHandle(handle)
	if !ok {
		return
	}
	c.Kill()
}

// ClientPing returns an owned, empty string on success, or the error
// message on failure. This is a plain string return, not an out_error
// failure, matching the Python-level `client.ping() == ""` convention
// tests assert.
//
//export ClientPing
func ClientPing(handle C.uintptr_t) *C.char {
	c, ok := clientFromHandle(handle)
	if !ok {
		return C.CString(invalidHandleErr)
	}
	proto, err := c.Client()
	if err != nil {
		return C.CString(err.Error())
	}
	if err = proto.Ping(); err != nil {
		return C.CString(err.Error())
	}
	return C.CString("")
}

//export ClientStart
func ClientStart(handle C.uintptr_t, outNetwork **C.char, outAddress **C.char, outError **C.char) C.int {
	c, ok := clientFromHandle(handle)
	if !ok {
		setOutError(outError, errors.New(invalidHandleErr))
		return 1
	}
	addr, err := c.Start()
	if err != nil {
		setOutError(outError, err)
		return 1
	}
	setOutString(outNetwork, addr.Network())
	setOutString(outAddress, addr.String())
	return 0
}

// ClientReattachConfig returns: 1 with all out params written if the
// client has reattach info available, 0 (out params untouched) if not
// (matches the underlying go-plugin contract: nil before the process has
// been started), -1 with outError set for an invalid handle.
//
//export ClientReattachConfig
func ClientReattachConfig(
	handle C.uintptr_t,
	outProtocol **C.char, outNetwork **C.char, outAddress **C.char,
	outPid *C.int, outTest *C.int,
	outError **C.char,
) C.int {
	c, ok := clientFromHandle(handle)
	if !ok {
		setOutError(outError, errors.New(invalidHandleErr))
		return -1
	}
	reattach := c.ReattachConfig()
	if reattach == nil {
		return 0
	}
	setOutString(outProtocol, string(reattach.Protocol))
	if reattach.Addr != nil {
		setOutString(outNetwork, reattach.Addr.Network())
		setOutString(outAddress, reattach.Addr.String())
	}
	if outPid != nil {
		*outPid = C.int(reattach.Pid)
	}
	if outTest != nil {
		if reattach.Test {
			*outTest = 1
		} else {
			*outTest = 0
		}
	}
	return 1
}

var _ net.Addr = simpleAddr{} // compile-time assertion: simpleAddr implements net.Addr
