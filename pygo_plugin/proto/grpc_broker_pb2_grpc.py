# Generated by the gRPC Python protocol compiler plugin. DO NOT EDIT!
"""Client and server classes corresponding to protobuf-defined services."""
import grpc

from pygo_plugin.proto import grpc_broker_pb2 as pygo__plugin_dot_proto_dot_grpc__broker__pb2


class GRPCBrokerStub(object):
    """Missing associated documentation comment in .proto file."""

    def __init__(self, channel):
        """Constructor.

        Args:
            channel: A grpc.Channel.
        """
        self.StartStream = channel.stream_stream(
                '/plugin.GRPCBroker/StartStream',
                request_serializer=pygo__plugin_dot_proto_dot_grpc__broker__pb2.ConnInfo.SerializeToString,
                response_deserializer=pygo__plugin_dot_proto_dot_grpc__broker__pb2.ConnInfo.FromString,
                )


class GRPCBrokerServicer(object):
    """Missing associated documentation comment in .proto file."""

    def StartStream(self, request_iterator, context):
        """Missing associated documentation comment in .proto file."""
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details('Method not implemented!')
        raise NotImplementedError('Method not implemented!')


def add_GRPCBrokerServicer_to_server(servicer, server):
    rpc_method_handlers = {
            'StartStream': grpc.stream_stream_rpc_method_handler(
                    servicer.StartStream,
                    request_deserializer=pygo__plugin_dot_proto_dot_grpc__broker__pb2.ConnInfo.FromString,
                    response_serializer=pygo__plugin_dot_proto_dot_grpc__broker__pb2.ConnInfo.SerializeToString,
            ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
            'plugin.GRPCBroker', rpc_method_handlers)
    server.add_generic_rpc_handlers((generic_handler,))


 # This class is part of an EXPERIMENTAL API.
class GRPCBroker(object):
    """Missing associated documentation comment in .proto file."""

    @staticmethod
    def StartStream(request_iterator,
            target,
            options=(),
            channel_credentials=None,
            call_credentials=None,
            insecure=False,
            compression=None,
            wait_for_ready=None,
            timeout=None,
            metadata=None):
        return grpc.experimental.stream_stream(request_iterator, target, '/plugin.GRPCBroker/StartStream',
            pygo__plugin_dot_proto_dot_grpc__broker__pb2.ConnInfo.SerializeToString,
            pygo__plugin_dot_proto_dot_grpc__broker__pb2.ConnInfo.FromString,
            options, channel_credentials,
            insecure, call_credentials, compression, wait_for_ready, timeout, metadata)