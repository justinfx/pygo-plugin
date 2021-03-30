#include <iostream>
#include <memory>
#include <string>

#include <grpcpp/grpcpp.h>
#include <grpcpp/health_check_service_interface.h>
#include <grpcpp/ext/proto_server_reflection_plugin.h>

#include "kv.grpc.pb.h"

using grpc::ServerContext;
using grpc::Status;
using proto::GetRequest;
using proto::GetResponse;
using proto::PutRequest;
using proto::Empty;
using proto::KV;


// Implement our plugin service
class KVServiceImpl final : public KV::Service {
    Status Get(ServerContext* context, const GetRequest* request, GetResponse* response) override {
        // TODO: retrieve from storage
        response->set_value("value");
        return Status::OK;
    }
    Status Put(ServerContext* context, const PutRequest* request, Empty* response) override {
        // TODO: do storage
        return Status::OK;
    }
};


void RunServer() {
    // ask for a random local port
    std::string server_address("127.0.0.1:0");
    int port = 0;

    KVServiceImpl service;

    grpc::EnableDefaultHealthCheckService(true);
    grpc::reflection::InitProtoReflectionServerBuilderPlugin();
    grpc::ServerBuilder builder;
    builder.AddListeningPort(server_address, grpc::InsecureServerCredentials(), &port);
    builder.RegisterService(&service);
    std::unique_ptr<grpc::Server> server(builder.BuildAndStart());

    // get the actual port that was selected by grpc
    server_address = "127.0.0.1:" + std::to_string(port);

    const int proto_ver = 1;      // should usually be 1 to match hashicorp/go-plugin
    const int app_proto_ver = 1;  // app-specific plugin version
    const char* network = "tcp";  // tcp or unix
    const char* proto = "grpc";   // only grpc is supported

    // Print the handshake protocol string so that the client can connect to us
    std::printf("%d|%d|%s|%s|%s\n", proto_ver, app_proto_ver, network, server_address.c_str(), proto);
    std::fflush(stdout);

    // Wait for the server to shutdown. Note that some other thread must be
    // responsible for shutting down the server for this call to ever return.
    server->Wait();
}


int main(int argc, char** argv) {
    RunServer();
    return 0;
}
