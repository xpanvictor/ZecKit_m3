# ZecKit Architecture

## System Overview

ZecKit is a containerized development toolkit for building on Zcash's Zebra node. It provides a one-command devnet with pre-funded wallets, UA fixtures, and automated testing.

---

## High-Level Architecture (M2)

```
┌─────────────────────────────────────────────────────────────┐
│                    Docker Compose Network                    │
│                      (zeckit-network)                        │
│                                                              │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │    Zebra     │◄────────┤   Faucet     │                 │
│  │  (Rust)      │  RPC    │  (Python)    │                 │
│  │  regtest     │  8232   │  Flask       │                 │
│  │              │         │  :8080       │                 │
│  └──────┬───────┘         └──────┬───────┘                 │
│         │                        │                          │
│         │                        │                          │
│         │                        ▼                          │
│         │              ┌─────────────────┐                 │
│         │              │  Docker Socket  │                 │
│         │              │  (for exec)     │                 │
│         │              └─────────────────┘                 │
│         │                        │                          │
│         ▼                        ▼                          │
│  ┌──────────────┐      ┌──────────────┐                   │
│  │ Lightwalletd │◄─────┤ Zingo Wallet │                   │
│  │  (Go)        │      │  (Rust)      │                   │
│  │  gRPC :9067  │      │  CLI         │                   │
│  └──────────────┘      └──────────────┘                   │
│                                                              │
│  Volumes:                                                   │
│  • zebra-data       - Blockchain state                     │
│  • zingo-data       - Wallet database                      │
│  • lightwalletd-data - LWD cache                           │
└─────────────────────────────────────────────────────────────┘
                            ▲
                            │
                       ┌────┴────┐
                       │ zecdev  │  (Rust CLI)
                       │ up/down │
                       │  test   │
                       └─────────┘
```

---

## Component Details

### 1. Zebra Node

**Purpose:** Core Zcash full node in regtest mode

**Technology:** Rust

**Responsibilities:**
- Validate blocks and transactions
- Provide RPC interface (port 8232)
- Run internal miner for block generation
- Maintain blockchain state

**Configuration:**
- Network: Regtest
- RPC: Enabled (no auth for dev)
- Internal Miner: Enabled
- Checkpoint sync: Disabled

**Docker Image:** Custom build from `ZcashFoundation/zebra`

**Key Files:**
- `/etc/zebrad/zebrad.toml` - Configuration
- `/var/zebra/` - Blockchain data

---

### 2. Lightwalletd

**Purpose:** Light client protocol server (gRPC)

**Technology:** Go

**Responsibilities:**
- Bridge between light clients and Zebra
- Serve compact blocks via gRPC
- Provide transaction broadcast API
- Cache blockchain data

**Configuration:**
- RPC Host: zebra:8232
- gRPC Port: 9067
- TLS: Disabled (dev only)

**Docker Image:** `electriccoinco/lightwalletd:latest`

---

### 3. Zingo Wallet

**Purpose:** Official Zcash wallet with CLI

**Technology:** Rust (ZingoLib)

**Responsibilities:**
- Generate unified addresses
- Sign and broadcast transactions
- Sync with lightwalletd
- Manage wallet state

**Configuration:**
- Data dir: `/var/zingo`
- Server: http://lightwalletd:9067
- Network: Regtest

**Docker Image:** Custom build from `zingolabs/zingolib`

**Key Files:**
- `/var/zingo/zingo-wallet.dat` - Wallet database
- `/var/zingo/wallets/` - Wallet subdirectory

---

### 4. Faucet Service

**Purpose:** REST API for test funds and fixtures

**Technology:** Python 3.11 + Flask + Gunicorn

**Responsibilities:**
- Serve test ZEC via REST API
- Generate UA fixtures
- Track balance and history
- Provide health checks

**Configuration:**
- Port: 8080
- Workers: 4 (Gunicorn)
- Wallet backend: Zingo CLI (via docker exec)

**Docker Image:** Custom Python 3.11-slim + Docker CLI

**Key Files:**
- `/app/app/` - Flask application
- `/var/zingo/` - Shared wallet data (read-only)

---

### 5. CLI Tool (`zecdev`)

**Purpose:** Developer command-line interface

**Technology:** Rust

**Responsibilities:**
- Orchestrate Docker Compose
- Run health checks
- Execute smoke tests
- Manage service lifecycle

**Commands:**
- `up` - Start services
- `down` - Stop services  
- `test` - Run smoke tests
- `status` - Check service health

**Key Files:**
- `cli/src/commands/` - Command implementations
- `cli/src/docker/` - Docker Compose wrapper

---

## Data Flow

### Startup Sequence

```
1. User runs: zecdev up --backend=lwd
   │
   ├─► CLI starts Docker Compose with lwd profile
   │
   ├─► Zebra starts, mines 101+ blocks
   │   └─► Internal miner: 5-60 sec per block
   │
   ├─► Lightwalletd connects to Zebra RPC
   │   └─► Waits for Zebra sync
   │
   ├─► Zingo Wallet starts
   │   ├─► Generates new wallet (if none exists)
   │   └─► Syncs with lightwalletd
   │
   ├─► Faucet starts
   │   ├─► Connects to Zingo via docker exec
   │   ├─► Gets wallet address
   │   └─► Waits for wallet sync
   │
   └─► CLI verifies all services healthy
       └─► Displays status dashboard
```

### Transaction Flow

```
1. User requests funds via API
   │
   ├─► POST /request {"address": "u1...", "amount": 10}
   │
   ├─► Faucet validates request
   │   ├─► Check balance > amount
   │   ├─► Validate address format
   │   └─► Apply rate limits
   │
   ├─► Faucet calls Zingo CLI
   │   └─► docker exec zeckit-zingo-wallet zingo-cli send ...
   │
   ├─► Zingo Wallet creates transaction
   │   ├─► Selects notes
   │   ├─► Creates proof
   │   └─► Signs transaction
   │
   ├─► Lightwalletd broadcasts to Zebra
   │   └─► Zebra adds to mempool
   │
   ├─► Internal miner includes in block
   │   └─► Block mined (5-60 seconds)
   │
   └─► Faucet returns TXID to user
```

---

## Network Configuration

### Ports (Host → Container)

| Service | Host Port | Container Port | Protocol |
|---------|-----------|----------------|----------|
| Zebra RPC | 127.0.0.1:8232 | 8232 | HTTP |
| Faucet API | 0.0.0.0:8080 | 8080 | HTTP |
| Lightwalletd | 127.0.0.1:9067 | 9067 | gRPC |

### Internal Network

- **Name:** `zeckit-network`
- **Driver:** bridge
- **Subnet:** Auto-assigned by Docker

**Container Hostnames:**
- `zebra` → Zebra node
- `lightwalletd` → Lightwalletd
- `zingo-wallet` → Zingo wallet
- `faucet` → Faucet API

---

## Storage Architecture

### Docker Volumes

```
zebra-data/
└── state/              # Blockchain database
    ├── rocksdb/
    └── finalized-state.rocksdb/

zingo-data/
└── wallets/            # Wallet database
    └── zingo-wallet.dat

lightwalletd-data/
└── db/                 # Compact block cache
```

### Volume Lifecycle

**Persistent (default):**
- Volumes persist between `up`/`down`
- Allows fast restarts

**Ephemeral (--purge):**
- `zecdev down --purge` removes all volumes
- Forces fresh blockchain mining
- Required after breaking changes

---

## Security Model

### Development Only

**⚠️ ZecKit is NOT production-ready:**

- No authentication on RPC/API
- No TLS/HTTPS
- No secret management
- Docker socket exposed
- Regtest mode only

### Isolation

- Services run in isolated Docker network
- Zebra RPC bound to localhost (127.0.0.1)
- Faucet API exposed (0.0.0.0) for LAN testing

### Secrets

**Current (M2):**
- No secrets required
- RPC has no authentication

**Future (M3+):**
- API keys for faucet rate limiting
- Optional RPC authentication

---

## Performance Characteristics

### Resource Usage

| Component | CPU | Memory | Disk |
|-----------|-----|--------|------|
| Zebra | 1 core | 500MB | 2GB |
| Lightwalletd | 0.2 core | 200MB | 500MB |
| Zingo Wallet | 0.1 core | 100MB | 50MB |
| Faucet | 0.1 core | 100MB | 10MB |
| **Total** | **1.4 cores** | **900MB** | **2.6GB** |

### Timing

- **Cold start:** 10-15 minutes (101 blocks)
- **Warm start:** 30 seconds (volumes persist)
- **Block time:** 5-60 seconds (variable)
- **Transaction confirmation:** 1 block (~30 sec avg)

---

## Design Decisions

### Why Docker Compose?

**Pros:**
- Simple single-file orchestration
- Native on Linux/WSL
- Profile-based backend switching
- Volume management built-in

**Cons:**
- Windows/macOS require Docker Desktop
- No built-in service mesh

**Alternative considered:** Kubernetes → Rejected (overkill for dev)

### Why Zingo CLI?

**Pros:**
- Official Zcash wallet
- Supports unified addresses
- Active development

**Cons:**
- Requires lightwalletd (no direct Zebra)
- Slower than native RPC

**Alternative considered:** Direct Zebra RPC → Rejected (no UA support)

### Why Python Faucet?

**Pros:**
- Fast development
- Rich HTTP ecosystem (Flask)
- Easy to extend

**Cons:**
- Slower than Rust
- Extra Docker socket dependency

**Alternative considered:** Rust faucet → Deferred to M3

---

## Future Architecture (M3+)

### Planned Changes

1. **Ephemeral Wallet:**
   ```yaml
   zingo-wallet:
     tmpfs:
       - /var/zingo  # Don't persist between runs
   ```

2. **Direct Wallet Integration:**
   - Move from docker exec to gRPC API
   - Remove Docker socket dependency

3. **Rate Limiting:**
   - Redis for distributed rate limits
   - API keys for authenticated requests

4. **Monitoring:**
   - Prometheus metrics
   - Grafana dashboards

---

## Troubleshooting Architecture

### Common Issues

**Wallet sync error:**
- **Cause:** Wallet state ahead of blockchain
- **Fix:** Delete zingo-data volume

**Port conflicts:**
- **Cause:** Another service using 8232/8080/9067
- **Fix:** Change ports in docker-compose.yml

**Out of memory:**
- **Cause:** Too many services
- **Fix:** Increase Docker memory limit

---

## References

- [Zebra Architecture](https://zebra.zfnd.org/dev.html)
- [Lightwalletd Protocol](https://github.com/zcash/lightwalletd)
- [Zingo Wallet](https://github.com/zingolabs/zingolib)
- [Docker Compose Spec](https://docs.docker.com/compose/compose-file/)

---

**Last Updated:** November 24, 2025  
**Version:** M2 (Real Transactions)