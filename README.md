# ZecKit

> A Zcash developer toolkit built on Zebra with real blockchain transactions

[![Smoke Test](https://github.com/Supercoolkayy/ZecKit/actions/workflows/smoke-test.yml/badge.svg)](https://github.com/Supercoolkayy/ZecKit/actions/workflows/smoke-test.yml)
[![License: MIT OR Apache-2.0](https://img.shields.io/badge/License-MIT%20OR%20Apache--2.0-blue.svg)](LICENSE-MIT)

---

## 🚀 Project Status: Milestone 2 Complete

**Current Milestone:** M2 - Real Blockchain Transactions  
**Completion:** ✅ 95% Complete (1 known issue)

###

 What Works Now

- ✅ **One-command devnet:** `zecdev up` starts everything
- ✅ **Real blockchain transactions:** Actual ZEC transfers via ZingoLib
- ✅ **Auto-mining:** 101+ blocks mined automatically (coinbase maturity)
- ✅ **Faucet API:** REST API for test funds
- ✅ **UA fixtures:** ZIP-316 unified addresses generated
- ✅ **Smoke tests:** 4/5 tests passing
- ✅ **CI pipeline:** GitHub Actions with self-hosted runner

### Known Issues

- ⚠️ **Wallet sync error** after volume deletion (workaround documented)
- ⚠️ **Test 5/5 fails** - Faucet funding works manually but test needs fixing

---

## Quick Start

### Prerequisites

- **OS:** Linux (Ubuntu 22.04+), WSL2, or macOS/Windows with Docker Desktop 4.34+
- **Docker:** Engine ≥ 24.x + Compose v2
- **Resources:** 2 CPU cores, 4GB RAM, 5GB disk

### Installation

```bash
# Clone repository
git clone https://github.com/Supercoolkayy/ZecKit.git
cd ZecKit

# Build CLI
cd cli
cargo build --release
cd ..

# Start devnet (takes 10-15 minutes for mining)
./cli/target/release/zecdev up --backend=lwd

# Run tests
./cli/target/release/zecdev test
```

### Verify It's Working

```bash
# Check service status
curl http://127.0.0.1:8080/health

# Get faucet stats
curl http://127.0.0.1:8080/stats

# Get UA fixture
cat fixtures/unified-addresses.json

# Request test funds (real transaction!)
curl -X POST http://127.0.0.1:8080/request \
  -H "Content-Type: application/json" \
  -d '{"address": "u1...", "amount": 10.0}'
```

---

## CLI Usage

### Start Devnet

```bash
# Start with lightwalletd
zecdev up --backend=lwd

# Stop services
zecdev down

# Stop and remove volumes (fresh start)
zecdev down --purge
```

### Run Tests

```bash
zecdev test

# Expected: 4/5 tests passing
# [1/5] Zebra RPC connectivity... ✓ PASS
# [2/5] Faucet health check... ✓ PASS
# [3/5] Faucet stats endpoint... ✓ PASS
# [4/5] Faucet address retrieval... ✓ PASS
# [5/5] Faucet funding request... ✗ FAIL (known issue)
```

---

## Faucet API

### Base URL
```
http://127.0.0.1:8080
```

### Endpoints

**Get Statistics**
```bash
curl http://127.0.0.1:8080/stats
```

**Get Address**
```bash
curl http://127.0.0.1:8080/address
```

**Request Funds**
```bash
curl -X POST http://127.0.0.1:8080/request \
  -H "Content-Type: application/json" \
  -d '{"address": "u1abc...", "amount": 10.0}'
```

Response includes real TXID from blockchain:
```json
{
  "txid": "a1b2c3d4e5f6...",
  "status": "sent",
  "amount": 10.0
}
```

---

## Architecture

```
┌─────────────────────────────────────┐
│         Docker Compose              │
│                                     │
│  ┌──────────┐      ┌──────────┐   │
│  │  Zebra   │◄─────┤  Faucet  │   │
│  │ regtest  │      │  Flask   │   │
│  │  :8232   │      │  :8080   │   │
│  └────┬─────┘      └────┬─────┘   │
│       │                 │          │
│       ▼                 ▼          │
│  ┌──────────┐      ┌──────────┐   │
│  │Lightwald │◄─────┤  Zingo   │   │
│  │  :9067   │      │  Wallet  │   │
│  └──────────┘      └──────────┘   │
└─────────────────────────────────────┘
           ▲
           │
      ┌────┴────┐
      │ zecdev  │  (Rust CLI)
      └─────────┘
```

**Components:**
- **Zebra:** Full node with internal miner
- **Lightwalletd:** Light client protocol server
- **Zingo Wallet:** Official Zcash wallet (ZingoLib)
- **Faucet:** Python Flask API for test funds
- **CLI:** Rust tool for orchestration

---

## Troubleshooting

### Wallet Sync Error

**Problem:**
```
Error: wallet height is more than 100 blocks ahead of best chain height
```

**Solution:**
```bash
./target/release/zecdev down
docker volume rm zeckit_zingo-data zeckit_zebra-data zeckit_lightwalletd-data
./target/release/zecdev up --backend=lwd
```

### Test 5/5 Fails

**Problem:** Faucet funding request test fails

**Workaround:** Test manually:
```bash
# Sync wallet first
echo "sync run" | docker exec -i zeckit-zingo-wallet zingo-cli \
  --data-dir /var/zingo --server http://lightwalletd:9067

# Check balance
curl http://127.0.0.1:8080/stats

# Request funds
curl -X POST http://127.0.0.1:8080/request \
  -H "Content-Type: application/json" \
  -d '{"address": "u1...", "amount": 10.0}'
```

### Port Conflicts

```bash
# Check what's using ports
lsof -i :8232
lsof -i :8080
lsof -i :9067

# Or change ports in docker-compose.yml
```

---

## Development

### Repository Structure

```
ZecKit/
├── cli/               # Rust CLI tool
│   ├── src/
│   │   ├── commands/  # up/down/test/status
│   │   └── docker/    # Docker Compose wrapper
│   └── Cargo.toml
├── faucet/            # Python faucet service
│   ├── app/
│   │   ├── routes/    # API endpoints
│   │   └── services/  # Wallet integration
│   └── Dockerfile
├── docker/
│   ├── zebra/         # Custom Zebra build
│   ├── zingo/         # Zingo wallet container
│   └── configs/       # Configuration files
├── fixtures/          # UA test fixtures
├── specs/             # Technical documentation
└── docker-compose.yml
```

### Build from Source

```bash
# Build CLI
cd cli
cargo build --release

# Build Docker images
docker compose --profile lwd build

# Run development faucet
cd faucet
pip install -r requirements.txt
python -m app.main
```

---

## Documentation

- **[Architecture](specs/architecture.md)** - System design
- **[Technical Spec](specs/technical-spec.md)** - Implementation details
- **[Acceptance Tests](specs/acceptance-tests.md)** - Test criteria

---

## Roadmap

### ✅ Milestone 1: Foundation (Complete)
- Docker-based Zebra regtest
- CI/CD pipeline
- Health checks

### ✅ Milestone 2: Real Transactions (95% Complete)
- Rust CLI tool (`zecdev`)
- Real blockchain transactions via ZingoLib
- Faucet API with balance tracking
- UA fixture generation
- Smoke tests (4/5 passing)

### ⏳ Milestone 3: GitHub Action (Next)
- Reusable GitHub Action
- Full E2E golden flows
- Backend parity testing
- Documentation improvements

---

## Known Limitations (M2)

1. ⚠️ **Wallet sync error** after volume deletion
   - Workaround: Delete all volumes before restart
   - Fix planned: Ephemeral wallet volume (M3)

2. ⚠️ **Test 5/5 fails** in automated suite
   - Manual testing works
   - Faucet can send real transactions
   - Fix planned: Improved test reliability (M3)

3. ⚠️ **Long startup time** (10-15 minutes)
   - Due to mining 101 blocks for coinbase maturity
   - Cannot be optimized significantly

4. ⚠️ **Windows/macOS support** is best-effort
   - Primary platform: Linux/WSL2
   - Docker Desktop 4.34+ required

---

## Contributing

Contributions welcome! Please:

1. Fork and create feature branch
2. Test locally: `zecdev up && zecdev test`
3. Follow code style (Rust: `cargo fmt`, Python: `black`)
4. Open PR with clear description

---

## FAQ

**Q: Are these real blockchain transactions?**  
A: Yes! M2 uses real on-chain transactions via ZingoLib and Zingo wallet.

**Q: Can I use this in production?**  
A: No. ZecKit is for development/testing only (regtest mode).

**Q: Why does startup take so long?**  
A: Mining 101 blocks for coinbase maturity takes 10-15 minutes. This is unavoidable.

**Q: Why does test 5/5 fail?**  
A: Known issue with test reliability. Manual transactions work fine.

**Q: How do I reset everything?**  
A: `./target/release/zecdev down --purge` removes all volumes.

---

## Support

- **Issues:** [GitHub Issues](https://github.com/Supercoolkayy/ZecKit/issues)
- **Discussions:** [GitHub Discussions](https://github.com/Supercoolkayy/ZecKit/discussions)
- **Community:** [Zcash Forum](https://forum.zcashcommunity.com/)

---

## License

Dual-licensed under MIT OR Apache-2.0

---

## Acknowledgments

**Built by:** Dapps over Apps team

**Thanks to:**
- Zcash Foundation (Zebra)
- Electric Coin Company (lightwalletd)
- Zingo Labs (ZingoLib)
- Zcash community

---

**Last Updated:** November 24, 2025  
**Next:** M3 - GitHub Action & E2E Flows