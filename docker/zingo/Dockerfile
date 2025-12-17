# docker/zingo/Dockerfile
FROM rust:1.85-slim-bookworm

RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    protobuf-compiler \
    libssl-dev \
    curl \
    git \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN git clone https://github.com/zingolabs/zingolib.git && \
    cd zingolib && \
    git checkout dev && \
    cargo build --release --package zingo-cli --jobs 1 && \
    mv target/release/zingo-cli /usr/local/bin/ && \
    chmod +x /usr/local/bin/zingo-cli && \
    rm -rf /build  # Clean up to save space

RUN mkdir -p /var/zingo && chmod 777 /var/zingo

WORKDIR /var/zingo

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]