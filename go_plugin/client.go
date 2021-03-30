package go_plugin

import (
	"fmt"
	"io"
	"net"
	"os/exec"
	"time"

	plugin "github.com/hashicorp/go-plugin"
)

// generate interfaces into classes in python

type NetAddr net.Addr

// type aliases to expose directly to python

type HandshakeConfig = plugin.HandshakeConfig

type Cmd struct {
	Path string
	Args []string
	Env  []string
	Dir  string
}

func NewCmd() *Cmd {
	return &Cmd{
		Args: []string{},
		Env:  []string{},
	}
}

func (c *Cmd) Valid() bool {
	return c.Path != ""
}

type ReattachConfig struct {
	*plugin.ReattachConfig
}

func (c *ReattachConfig) SetPtr(ptr *plugin.ReattachConfig) {
	c.ReattachConfig = ptr
}

func (c *ReattachConfig) String() string {
	if !c.Valid() {
		return "<ReattachConfig: Valid=False>"
	}
	return fmt.Sprintf("<ReattachConfig: Protocol=%v, Addr=%v, Pid=%v>",
		c.Protocol(), c.Addr(), c.Pid())
}

// gopy:name protocol
func (c *ReattachConfig) Protocol() plugin.Protocol {
	if !c.Valid() {
		return plugin.ProtocolInvalid
	}
	return c.ReattachConfig.Protocol
}

// gopy:name addr
func (c *ReattachConfig) Addr() net.Addr {
	if !c.Valid() {
		return nil
	}
	return c.ReattachConfig.Addr
}

// gopy:name pid
func (c *ReattachConfig) Pid() int {
	if !c.Valid() {
		return -1
	}
	return c.ReattachConfig.Pid
}

// gopy:name test
func (c *ReattachConfig) Test() bool {
	if !c.Valid() {
		return false
	}
	return c.ReattachConfig.Test
}

// gopy:name set_test
func (c *ReattachConfig) SetTest(enabled bool) {
	if !c.Valid() {
		return
	}
	c.ReattachConfig.Test = enabled
}

// gopy:name valid
func (c *ReattachConfig) Valid() bool {
	return c != nil && c.ReattachConfig != nil && c.ReattachConfig.Protocol != plugin.ProtocolInvalid
}

type ClientConfig struct {
	// HandshakeConfig is the configuration that must match servers.
	HandshakeConfig plugin.HandshakeConfig

	//// Plugins are the plugins that can be consumed.
	//// The implied version of this PluginSet is the Handshake.ProtocolVersion.
	//Plugins plugin.PluginSet

	//// VersionedPlugins is a map of PluginSets for specific protocol versions.
	//// These can be used to negotiate a compatible version between client and
	//// server. If this is set, Handshake.ProtocolVersion is not required.
	//VersionedPlugins map[int]plugin.PluginSet

	// One of the following must be set, but not both.
	//
	// Cmd is the unstarted subprocess for starting the plugin. If this is
	// set, then the Client starts the plugin process on its own and connects
	// to it.
	//
	// Reattach is configuration for reattaching to an existing plugin process
	// that is already running. This isn't common.
	cmd      *Cmd
	reattach *plugin.ReattachConfig

	//// SecureConfig is configuration for verifying the integrity of the
	//// executable. It can not be used with Reattach.
	//SecureConfig *plugin.SecureConfig

	//// TLSConfig is used to enable TLS on the RPC client.
	//TLSConfig *tls.Config

	// The minimum port to use for communicating with the subprocess.
	// If not set, this defaults to 10,000.
	MinPort uint

	// The maximum port to use for communicating with the subprocess.
	// If not set, this defaults to 25,000.
	MaxPort uint

	// startTimeout is the timeout to wait for the plugin to say it
	// has started successfully.
	startTimeout time.Duration

	// If non-nil, then the stderr of the client will be written to here
	// (as well as the log). This is the original os.Stderr of the subprocess.
	// This isn't the output of synced stderr.
	Stderr io.Writer

	// SyncStdout, SyncStderr can be set to override the
	// respective os.Std* values in the plugin. Care should be taken to
	// avoid races here. If these are nil, then this will be set to
	// ioutil.Discard.
	SyncStdout io.Writer
	SyncStderr io.Writer

	//// AllowedProtocols is a list of allowed protocols. If this isn't set,
	//// then only netrpc is allowed. This is so that older go-plugin systems
	//// can show friendly errors if they see a plugin with an unknown
	//// protocol.
	////
	//// By setting this, you can cause an error immediately on plugin start
	//// if an unsupported protocol is used with a good error message.
	////
	//// If this isn't set at all (nil value), then only net/rpc is accepted.
	//// This is done for legacy reasons. You must explicitly opt-in to
	//// new protocols.
	//AllowedProtocols []plugin.Protocol

	// AutoMTLS has the client and server automatically negotiate mTLS for
	// transport authentication. This ensures that only the original client will
	// be allowed to connect to the server, and all other connections will be
	// rejected. The client will also refuse to connect to any server that isn't
	// the original instance started by the client.
	//
	// In this mode of operation, the client generates a one-time use tls
	// certificate, sends the public x.509 certificate to the new server, and
	// the server generates a one-time use tls certificate, and sends the public
	// x.509 certificate back to the client. These are used to authenticate all
	// rpc connections between the client and server.
	//
	// Setting AutoMTLS to true implies that the server must support the
	// protocol, and correctly negotiate the tls certificates, or a connection
	// failure will result.
	//
	// The client should not set TLSConfig, nor should the server set a
	// TLSProvider, because AutoMTLS implies that a new certificate and tls
	// configuration will be generated at startup.
	//
	// You cannot Reattach to a server with this option enabled.
	AutoMTLS bool
}

func (c *ClientConfig) toGo() *plugin.ClientConfig {
	cfg := &plugin.ClientConfig{
		HandshakeConfig:  c.HandshakeConfig,
		Plugins:          map[string]plugin.Plugin{},
		MinPort:          c.MinPort,
		MaxPort:          c.MaxPort,
		StartTimeout:     c.startTimeout,
		Stderr:           c.Stderr,
		SyncStdout:       c.SyncStdout,
		SyncStderr:       c.SyncStderr,
		AllowedProtocols: []plugin.Protocol{plugin.ProtocolGRPC},
		//Logger:           nil,
		AutoMTLS: c.AutoMTLS,
	}

	if c.cmd != nil && c.cmd.Valid() {
		cfg.Cmd = &exec.Cmd{
			Path: c.cmd.Path,
			Args: c.cmd.Args,
			Env:  c.cmd.Env,
			Dir:  c.cmd.Dir,
		}
	} else if c.reattach != nil {
		cfg.Reattach = c.reattach
	}
	return cfg
}

// gopy:name cmd
func (c *ClientConfig) Cmd() *Cmd {
	if c.cmd == nil {
		c.cmd = NewCmd()
	}
	return c.cmd
}

// gopy:name set_cmd
func (c *ClientConfig) SetCmd(cmd *Cmd) {
	c.cmd = cmd
}

// gopy:name reattach_config
func (c *ClientConfig) ReattachConfig() *ReattachConfig {
	if c == nil || c.reattach == nil {
		return nil
	}
	return &ReattachConfig{c.reattach}
}

// gopy:name set_reattach_config
func (c *ClientConfig) SetReattachConfig(cfg *ReattachConfig) {
	if cfg == nil {
		c.reattach = nil
	} else {
		c.reattach = cfg.ReattachConfig
	}
}

// gopy:name start_timeout
func (c *ClientConfig) StartTimeout() int64 {
	return c.startTimeout.Milliseconds()
}

// gopy:name set_start_timeout
func (c *ClientConfig) SetStartTimeout(msec int64) {
	c.startTimeout = (time.Millisecond / time.Nanosecond) * time.Duration(msec)
}

type Client = plugin.Client

func NewClient(cfg *ClientConfig) *plugin.Client {
	return plugin.NewClient(cfg.toGo())
}

func ClientPing(client *Client) string {
	proto, err := client.Client()
	if err != nil {
		return err.Error()
	}
	if err = proto.Ping(); err != nil {
		return err.Error()
	}
	return ""
}
