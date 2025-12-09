# Multi-stage build for lightwalletd
FROM --platform=$BUILDPLATFORM golang:1.21-bookworm as builder

# Set up cross-compilation
ARG TARGETPLATFORM
ARG BUILDPLATFORM
ARG TARGETOS
ARG TARGETARCH

# Install dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Clone lightwalletd
WORKDIR /build
RUN git clone https://github.com/zcash/lightwalletd.git
WORKDIR /build/lightwalletd

# Build for target architecture
ENV CGO_ENABLED=0
ENV GOOS=${TARGETOS}
ENV GOARCH=${TARGETARCH}

RUN go build -o lightwalletd ./cmd/lightwalletd

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    curl \
    grpc-health-probe \
    && rm -rf /var/lib/apt/lists/*

# Copy binary from builder
COPY --from=builder /build/lightwalletd/lightwalletd /usr/local/bin/lightwalletd
RUN chmod +x /usr/local/bin/lightwalletd

# Create data directory
RUN mkdir -p /var/lib/lightwalletd

WORKDIR /var/lib/lightwalletd

EXPOSE 9067

# Default command - will be overridden by docker-compose
ENTRYPOINT ["/usr/local/bin/lightwalletd"]