#!/usr/bin/env python

import glob
import os
import shutil
import sys
import sysconfig
from importlib import resources

from setuptools import Command, setup
from setuptools.command.build_py import build_py
from setuptools.errors import ExecError


ROOT = os.path.dirname(os.path.abspath(__file__))


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
        gopy = shutil.which('gopy')
        if not gopy:
            raise ExecError("could not find gopy executable in PATH")
        go = shutil.which('go')
        if not go:
            raise ExecError("could not find go executable in PATH")

        srcdir = 'src/pygo_plugin/_goplugin'
        output = os.path.join(ROOT, srcdir)

        self.spawn([
            gopy, self._CMD,
            '-name=goplugin',
            '-no-make=true',
            # '-symbols=false',  # slightly smaller binary if enabled
            '-output', output,
            '-vm', sys.executable,
            '-rename',
            os.path.join(ROOT, 'go_plugin'),
        ])

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
