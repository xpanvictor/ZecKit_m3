# ========================================
# ZecKit Zaino - Using Pre-built Image
# ========================================
# Uses the official zingodevops/zaino image with no-TLS support
# This avoids the 20+ minute build time
#
FROM zingodevops/zaino:v0.1.2-rc3-no-tls

USER root

RUN apt-get update && apt-get install -y \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create zaino user if not exists
RUN id -u zaino 2>/dev/null || useradd -m -u 2002 -s /bin/bash zaino

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

RUN mkdir -p /var/zaino && chown -R zaino:zaino /var/zaino

WORKDIR /var/zaino

USER zaino

ENTRYPOINT ["/entrypoint.sh"]