#!/usr/bin/env python

from setuptools import Command
from distutils.command.build_py import build_py
from distutils.core import setup
from distutils.errors import DistutilsExecError
from distutils.spawn import find_executable
import glob
import os
import pkg_resources
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))


class GopyGenTool(Command):
    description = "Generate go-plugin python bindings"
    user_options = []

    _CMD = 'gen'

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        gopy = find_executable('gopy')
        if not gopy:
            raise DistutilsExecError("could not find gopy executable in PATH")
        go = find_executable('go')
        if not go:
            raise DistutilsExecError("could not find go executable in PATH")

        self.spawn([
            gopy, self._CMD,
            '-name=goplugin',
            '-no-make=true',
            # '-symbols=false',  # slightly smaller binary if enabled
            '-output', os.path.join(ROOT, 'src/pygo_plugin/_goplugin'),
            '-vm', sys.executable,
            '-rename',
            os.path.join(ROOT, 'go_plugin'),
        ])


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

        proto_include = pkg_resources.resource_filename('grpc_tools', '_proto')

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
        self.run_command('grpc')
        self.run_command('gopy_build')
        super(BuildPyCommand, self).run()


setup(
    cmdclass={
        'build_py': BuildPyCommand,
        'grpc': GrpcGenTool,
        'gopy_gen': GopyGenTool,
        'gopy_build': GopyBuildTool,
    },

    name='pygo-plugin',
    version='0.0.1',
    url='https://github.com/justinfx/pygo-plugin',
    license='Apache License 2.0',
    author='Justin Israel',
    author_email='justinisrael@gmail.com',
    description='Python gRPC Plugin System (port of hashicorp/go-plugin)',

    packages=['pygo_plugin', 'pygo_plugin._goplugin', 'pygo_plugin.proto'],
    package_dir={
        '': 'src',
        'pygo_plugin._goplugin': 'src/pygo_plugin/_goplugin',
        'pygo_plugin.proto': 'src/pygo_plugin/proto',
    },
    package_data={
        'pygo_plugin._goplugin': ['*.so'],
        'pygo_plugin.proto': ['*.py', '*.proto', '*.go-plugin'],
    },
    exclude_package_data={'pygo_plugin._goplugin': ['build.py']},

    classifiers=[
        'Development Status :: 4 - Alpha',
        # 'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software Licensee',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
    ],
    keywords=['python', 'rpc', 'plugin', 'grpc', 'grpcio', 'go-plugin', 'hashicorp'],
    install_requires=[
        'future',
        'futures; python_version == "2.7"',
        'grpcio-tools',
        'grpcio-health-checking',
        'grpcio-reflection',
        'protobuf==3.*',
        'pybindgen',
        'typing; python_version == "2.7"',
    ],
    extras_require={'': ['pytest']},
    zip_safe=False,
)
