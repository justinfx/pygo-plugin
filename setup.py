#!/usr/bin/env python

import glob
import os
import shutil
import subprocess
import sys
from importlib import resources

from setuptools import Command, setup
from setuptools.command.build_py import build_py
from setuptools.errors import ExecError


ROOT = os.path.dirname(os.path.abspath(__file__))

# Set to skip the Go compile step during build_py, for a plugin-only
# environment (e.g. a pyinterp plugin subprocess venv) that never imports
# pygo_plugin.client and so has no use for the compiled native library,
# but would otherwise need the Go toolchain on PATH just to install the
# package.
SKIP_NATIVE_BUILD_ENV = 'PYGO_PLUGIN_SKIP_NATIVE_BUILD'

_LIB_EXT = {'darwin': 'dylib', 'win32': 'dll'}.get(sys.platform, 'so')
_LIB_NAME = 'libgoplugin.' + _LIB_EXT


class GoBuildTool(Command):
    description = "Build the go_plugin native shared library (cffi-loadable)"
    user_options = []

    build_lib_target = None

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        go = shutil.which('go')
        if not go:
            raise ExecError("could not find go executable in PATH")

        srcdir = os.path.join(ROOT, 'src/pygo_plugin/_goplugin')
        self.mkpath(srcdir)
        output = os.path.join(srcdir, _LIB_NAME)

        cmd = [
            go, 'build', '-buildmode=c-shared',
            '-o', output,
            './go_plugin',
        ]
        self.announce('running: {}'.format(' '.join(cmd)), level=2)
        if not self.dry_run:
            subprocess.run(cmd, cwd=ROOT, check=True)

        if self.build_lib_target is None:
            # Running standalone (not as part of build_py): the library was
            # already built directly into srcdir, nothing to copy.
            return

        for src in glob.glob(os.path.join(srcdir, 'libgoplugin.*')):
            self.copy_file(src, self.build_lib_target)


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
        GoBuildTool.build_lib_target = target_dir

        if not self.dry_run:
            self.mkpath(target_dir)

        self.run_command('grpc')

        if os.environ.get(SKIP_NATIVE_BUILD_ENV):
            print(
                "{} set: skipping go_build (no compiled native library; "
                "this install can only be used for plugin-subprocess-side "
                "code, not pygo_plugin.Client, .ClientConfig, or "
                ".Cmd)".format(SKIP_NATIVE_BUILD_ENV)
            )
        else:
            self.run_command('go_build')

        build_py.run(self)


# All static metadata (name, version, dependencies, classifiers, packages,
# package_data, etc.) lives in pyproject.toml now. setup.py's only reason
# to exist is these custom Commands (the Go build and protoc invoke
# external tools and can't be expressed declaratively), so cmdclass is the
# only thing left here.
setup(
    cmdclass={
        'build_py': BuildPyCommand,
        'grpc': GrpcGenTool,
        'go_build': GoBuildTool,
    },
)
