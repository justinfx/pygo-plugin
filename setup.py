#!/usr/bin/env python

import glob
import os
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from importlib import resources

from setuptools import Command, setup
from setuptools.command.build_py import build_py
from setuptools.errors import ExecError


ROOT = os.path.dirname(os.path.abspath(__file__))

# Set to skip the gopy/go compile step during build_py, for a plugin-only
# environment (e.g. a pyinterp plugin subprocess venv) that never imports
# pygo_plugin.client and so has no use for the compiled _goplugin extension,
# but would otherwise need go/gopy on PATH just to install the package.
SKIP_GOPY_BUILD_ENV = 'PYGO_PLUGIN_SKIP_GOPY_BUILD'


class GopyGenTool(Command):
    description = "Generate go-plugin python bindings"
    user_options = []

    _CMD = 'gen'
    build_lib_target = None

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        go = shutil.which('go')
        if not go:
            raise ExecError("could not find go executable in PATH")

        srcdir = 'src/pygo_plugin/_goplugin'
        output = os.path.join(ROOT, srcdir)

        with tempfile.TemporaryDirectory() as toolsdir:
            gopy = self._install_pinned_tool(go, toolsdir, 'github.com/go-python/gopy')
            self._install_pinned_tool(go, toolsdir, 'golang.org/x/tools/cmd/goimports')

            env = dict(os.environ)
            env['PATH'] = os.pathsep.join([toolsdir, env.get('PATH', '')])

            cmd = [
                gopy, self._CMD,
                '-name=goplugin',
                '-no-make=true',
                # '-symbols=false',  # slightly smaller binary if enabled
                '-output', output,
                '-vm', sys.executable,
                '-rename',
                os.path.join(ROOT, 'go_plugin'),
            ]
            self.announce('running: {}'.format(' '.join(cmd)), level=2)
            if not self.dry_run:
                subprocess.run(cmd, cwd=ROOT, env=env, check=True)

        if self.build_lib_target is None:
            # Running standalone (not as part of build_py): gopy already
            # wrote the extension directly into `output`, nothing to copy.
            return

        ext = sysconfig.get_config_var("EXT_SUFFIX")
        if not ext:
            ext = sysconfig.get_config_var("SO")
        if not ext:
            ext = ".so"
        for src in glob.glob(os.path.join(srcdir, '*' + ext)):
            self.copy_file(src, self.build_lib_target)

    def _install_pinned_tool(self, go, gobin, module_path):
        # Deliberately `go install pkg@version`, not `go build`/`go tool`
        # from inside this module: that embeds this module's go1.24
        # GODEBUG defaults (gotypesalias=1) into the gopy binary instead
        # of gopy's own go1.22 defaults, and gopy's type analysis panics
        # on the newer alias representation.
        result = subprocess.run(
            [go, 'list', '-f', '{{.Module.Version}}', module_path],
            cwd=ROOT, capture_output=True, text=True, check=True,
        )
        version = result.stdout.strip()

        cmd = [go, 'install', '{}@{}'.format(module_path, version)]
        self.announce('running: {}'.format(' '.join(cmd)), level=2)
        if not self.dry_run:
            env = dict(os.environ, GOBIN=gobin)
            subprocess.run(cmd, cwd=ROOT, env=env, check=True)

        name = module_path.rsplit('/', 1)[-1]
        if os.name == 'nt':
            name += '.exe'
        return os.path.join(gobin, name)


class GopyBuildTool(GopyGenTool):
    description = "Build go-plugin python bindings"
    _CMD = 'build'


class GrpcGenTool(Command):
    description = "Generate proto/grpc python bindings"
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import grpc_tools.protoc

        proto_include = str(resources.files('grpc_tools') / '_proto')

        for proto in glob.glob(os.path.join(ROOT, 'src/pygo_plugin/proto/*.proto')):
            grpc_tools.protoc.main([
                'grpc_tools.protoc',
                '-I{}'.format(proto_include),
                '-I{}'.format(os.path.join(ROOT, 'src')),
                '--python_out=src',
                '--grpc_python_out=src',
                proto,
            ])


class BuildPyCommand(build_py):
    def run(self):
        target_dir = os.path.join(self.build_lib, 'pygo_plugin/_goplugin')
        GopyGenTool.build_lib_target = target_dir

        if not self.dry_run:
            self.mkpath(target_dir)

        self.run_command('grpc')

        if os.environ.get(SKIP_GOPY_BUILD_ENV):
            print(
                "{} set: skipping gopy_build (no compiled _goplugin "
                "extension; this install can only be used for "
                "plugin-subprocess-side code, not pygo_plugin.Client, "
                ".ClientConfig, or .Cmd)".format(SKIP_GOPY_BUILD_ENV)
            )
        else:
            self.run_command('gopy_build')

        build_py.run(self)


# All static metadata (name, version, dependencies, classifiers, packages,
# package_data, etc.) lives in pyproject.toml now. setup.py's only reason
# to exist is these custom Commands (gopy/protoc invoke external tools and
# can't be expressed declaratively), so cmdclass is the only thing left
# here.
setup(
    cmdclass={
        'build_py': BuildPyCommand,
        'grpc': GrpcGenTool,
        'gopy_gen': GopyGenTool,
        'gopy_build': GopyBuildTool,
    },
)
