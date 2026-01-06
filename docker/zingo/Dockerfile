# docker/zingo/Dockerfile
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Download latest zingo-cli release binary
WORKDIR /tmp
RUN curl -sSL -o zingo-cli.tar.gz "https://github.com/zingolabs/zingolib/releases/latest/download/zingo-cli-x86_64-unknown-linux-gnu.tar.gz" \
    && tar -xzf zingo-cli.tar.gz \
    && mv zingo-cli /usr/local/bin/zingo-cli \
    && chmod +x /usr/local/bin/zingo-cli \
    && rm zingo-cli.tar.gz

RUN mkdir -p /var/zingo && chmod 777 /var/zingo

WORKDIR /var/zingo

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]