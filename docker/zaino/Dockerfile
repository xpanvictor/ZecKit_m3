# docker/zaino/Dockerfile
FROM rust:1.85-slim-bookworm

RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    curl \
    netcat-openbsd \
    libclang-dev \
    clang \
    llvm \
    cmake \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# Clone and build Zaino indexer WITH MEMORY LIMITS
WORKDIR /build
RUN git clone https://github.com/zingolabs/zaino.git && \
    cd zaino && \
    CARGO_BUILD_JOBS=1 cargo build --release --bin zainod && \
    mv target/release/zainod /usr/local/bin/ && \
    chmod +x /usr/local/bin/zainod && \
    rm -rf /build  # Clean up immediately

RUN mkdir -p /var/zaino && chmod 777 /var/zaino

WORKDIR /var/zaino

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]