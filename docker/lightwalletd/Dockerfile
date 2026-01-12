# Multi-stage build for lightwalletd
FROM golang:1.24-bookworm as probe_builder

# Build grpc-health-probe
RUN git clone https://github.com/grpc-ecosystem/grpc-health-probe.git
WORKDIR /grpc-health-probe
RUN go build -o grpc_health_probe

# Runtime stage
FROM electriccoinco/lightwalletd:latest

# Copy grpc_health_probe
COPY --from=probe_builder /grpc-health-probe/grpc_health_probe /usr/local/bin/grpc_health_probe
RUN chmod +x /usr/local/bin/grpc_health_probe

# Copy entrypoint
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create data directory
RUN mkdir -p /var/lightwalletd

WORKDIR /var/lightwalletd

EXPOSE 9067

ENTRYPOINT ["/entrypoint.sh"]