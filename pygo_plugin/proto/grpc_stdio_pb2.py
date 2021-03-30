# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: pygo_plugin/proto/grpc_stdio.proto
"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf import reflection as _reflection
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from google.protobuf import empty_pb2 as google_dot_protobuf_dot_empty__pb2


DESCRIPTOR = _descriptor.FileDescriptor(
  name='pygo_plugin/proto/grpc_stdio.proto',
  package='plugin',
  syntax='proto3',
  serialized_options=b'Z\006plugin',
  create_key=_descriptor._internal_create_key,
  serialized_pb=b'\n\"pygo_plugin/proto/grpc_stdio.proto\x12\x06plugin\x1a\x1bgoogle/protobuf/empty.proto\"u\n\tStdioData\x12*\n\x07\x63hannel\x18\x01 \x01(\x0e\x32\x19.plugin.StdioData.Channel\x12\x0c\n\x04\x64\x61ta\x18\x02 \x01(\x0c\".\n\x07\x43hannel\x12\x0b\n\x07INVALID\x10\x00\x12\n\n\x06STDOUT\x10\x01\x12\n\n\x06STDERR\x10\x02\x32G\n\tGRPCStdio\x12:\n\x0bStreamStdio\x12\x16.google.protobuf.Empty\x1a\x11.plugin.StdioData0\x01\x42\x08Z\x06pluginb\x06proto3'
  ,
  dependencies=[google_dot_protobuf_dot_empty__pb2.DESCRIPTOR,])



_STDIODATA_CHANNEL = _descriptor.EnumDescriptor(
  name='Channel',
  full_name='plugin.StdioData.Channel',
  filename=None,
  file=DESCRIPTOR,
  create_key=_descriptor._internal_create_key,
  values=[
    _descriptor.EnumValueDescriptor(
      name='INVALID', index=0, number=0,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='STDOUT', index=1, number=1,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
    _descriptor.EnumValueDescriptor(
      name='STDERR', index=2, number=2,
      serialized_options=None,
      type=None,
      create_key=_descriptor._internal_create_key),
  ],
  containing_type=None,
  serialized_options=None,
  serialized_start=146,
  serialized_end=192,
)
_sym_db.RegisterEnumDescriptor(_STDIODATA_CHANNEL)


_STDIODATA = _descriptor.Descriptor(
  name='StdioData',
  full_name='plugin.StdioData',
  filename=None,
  file=DESCRIPTOR,
  containing_type=None,
  create_key=_descriptor._internal_create_key,
  fields=[
    _descriptor.FieldDescriptor(
      name='channel', full_name='plugin.StdioData.channel', index=0,
      number=1, type=14, cpp_type=8, label=1,
      has_default_value=False, default_value=0,
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
    _descriptor.FieldDescriptor(
      name='data', full_name='plugin.StdioData.data', index=1,
      number=2, type=12, cpp_type=9, label=1,
      has_default_value=False, default_value=b"",
      message_type=None, enum_type=None, containing_type=None,
      is_extension=False, extension_scope=None,
      serialized_options=None, file=DESCRIPTOR,  create_key=_descriptor._internal_create_key),
  ],
  extensions=[
  ],
  nested_types=[],
  enum_types=[
    _STDIODATA_CHANNEL,
  ],
  serialized_options=None,
  is_extendable=False,
  syntax='proto3',
  extension_ranges=[],
  oneofs=[
  ],
  serialized_start=75,
  serialized_end=192,
)

_STDIODATA.fields_by_name['channel'].enum_type = _STDIODATA_CHANNEL
_STDIODATA_CHANNEL.containing_type = _STDIODATA
DESCRIPTOR.message_types_by_name['StdioData'] = _STDIODATA
_sym_db.RegisterFileDescriptor(DESCRIPTOR)

StdioData = _reflection.GeneratedProtocolMessageType('StdioData', (_message.Message,), {
  'DESCRIPTOR' : _STDIODATA,
  '__module__' : 'pygo_plugin.proto.grpc_stdio_pb2'
  # @@protoc_insertion_point(class_scope:plugin.StdioData)
  })
_sym_db.RegisterMessage(StdioData)


DESCRIPTOR._options = None

_GRPCSTDIO = _descriptor.ServiceDescriptor(
  name='GRPCStdio',
  full_name='plugin.GRPCStdio',
  file=DESCRIPTOR,
  index=0,
  serialized_options=None,
  create_key=_descriptor._internal_create_key,
  serialized_start=194,
  serialized_end=265,
  methods=[
  _descriptor.MethodDescriptor(
    name='StreamStdio',
    full_name='plugin.GRPCStdio.StreamStdio',
    index=0,
    containing_service=None,
    input_type=google_dot_protobuf_dot_empty__pb2._EMPTY,
    output_type=_STDIODATA,
    serialized_options=None,
    create_key=_descriptor._internal_create_key,
  ),
])
_sym_db.RegisterServiceDescriptor(_GRPCSTDIO)

DESCRIPTOR.services_by_name['GRPCStdio'] = _GRPCSTDIO

# @@protoc_insertion_point(module_scope)