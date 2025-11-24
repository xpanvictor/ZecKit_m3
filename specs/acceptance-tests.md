# ZecKit M2 Acceptance Tests

## Overview

This document defines the acceptance criteria for Milestone 2 (CLI Tool + Faucet + Real Transactions).

---

## Test Environment

- **Platform:** Ubuntu 22.04 LTS (WSL2 or native)
- **Docker:** Engine 24.x + Compose v2
- **Rust:** 1.70+
- **Resources:** 2 CPU, 4GB RAM, 5GB disk

---

## M2 Acceptance Criteria

### 1. CLI Tool: `zecdev up`

**Test:** Start devnet with lightwalletd backend

```bash
cd cli
./target/release/zecdev up --backend=lwd
```

**Expected:**
- ✅ Zebra starts in regtest mode
- ✅ Internal miner generates 101+ blocks (coinbase maturity)
- ✅ Lightwalletd connects to Zebra
- ✅ Zingo wallet syncs with lightwalletd
- ✅ Faucet API starts and is accessible
- ✅ All services report healthy
- ✅ Total startup time: < 15 minutes

**Success Criteria:**
```
✓ Mined 101 blocks (coinbase maturity reached)
✓ All services ready!
Zebra RPC: http://127.0.0.1:8232
Faucet API: http://127.0.0.1:8080
```

---

### 2. CLI Tool: `zecdev test`

**Test:** Run comprehensive smoke tests

```bash
./target/release/zecdev test
```

**Expected:**
- ✅ [1/5] Zebra RPC connectivity: PASS
- ✅ [2/5] Faucet health check: PASS
- ✅ [3/5] Faucet stats endpoint: PASS
- ✅ [4/5] Faucet address retrieval: PASS
- ✅ [5/5] Faucet funding request: PASS

**Success Criteria:**
```
✓ Tests passed: 5
✗ Tests failed: 0
```

---

### 3. Real Blockchain Transactions

**Test:** Faucet can send real ZEC on regtest

```bash
# Get faucet address
FAUCET_ADDR=$(curl -s http://127.0.0.1:8080/address | jq -r '.address')

# Get balance
curl http://127.0.0.1:8080/stats | jq '.current_balance'

# Request funds to test address
curl -X POST http://127.0.0.1:8080/request \
  -H "Content-Type: application/json" \
  -d '{"address": "u1test...", "amount": 10.0}'
```

**Expected:**
- ✅ Returns valid TXID (64-char hex)
- ✅ Transaction appears in Zebra mempool
- ✅ Balance updates correctly
- ✅ Transaction history records it

**Success Criteria:**
```json
{
  "txid": "a1b2c3d4...",
  "status": "sent",
  "amount": 10.0
}
```

---

### 4. UA Fixtures Generation

**Test:** Fixtures are created on startup

```bash
cat fixtures/unified-addresses.json
```

**Expected:**
- ✅ File exists at `fixtures/unified-addresses.json`
- ✅ Contains valid unified address
- ✅ Address type is "unified"
- ✅ Receivers include "orchard"

**Success Criteria:**
```json
{
  "faucet_address": "u1...",
  "type": "unified",
  "receivers": ["orchard"]
}
```

---

### 5. Service Health Checks

**Test:** All services report healthy

```bash
# Zebra RPC
curl -X POST http://127.0.0.1:8232 \
  -d '{"jsonrpc":"2.0","method":"getblockcount","params":[],"id":1}'

# Faucet health
curl http://127.0.0.1:8080/health

# Stats endpoint
curl http://127.0.0.1:8080/stats
```

**Expected:**
- ✅ Zebra: Returns block height
- ✅ Faucet: Returns {"status": "healthy"}
- ✅ Stats: Shows balance > 0

---

### 6. Clean Shutdown

**Test:** Services stop cleanly

```bash
./target/release/zecdev down
```

**Expected:**
- ✅ All containers stop
- ✅ No error messages
- ✅ Volumes persist (for restart)

---

### 7. Fresh Start

**Test:** Can restart from clean state

```bash
./target/release/zecdev down --purge
./target/release/zecdev up --backend=lwd
```

**Expected:**
- ✅ All volumes removed
- ✅ Fresh blockchain mined
- ✅ New wallet created
- ✅ All tests pass again

---

## Known Issues (M2)

### ⚠️ Wallet Sync Issue

**Problem:** After deleting volumes and restarting, wallet may have sync errors:
```
Error: wallet height is more than 100 blocks ahead of best chain height
```

**Workaround:**
```bash
./target/release/zecdev down
docker volume rm zeckit_zingo-data zeckit_zebra-data zeckit_lightwalletd-data
./target/release/zecdev up --backend=lwd
```

**Status:** Known issue, will be fixed in M3 with ephemeral wallet volume.

---

## CI/CD Tests

### GitHub Actions Smoke Test

**Test:** CI pipeline runs successfully

```yaml
# .github/workflows/smoke-test.yml
- name: Start ZecKit
  run: ./cli/target/release/zecdev up --backend=lwd
  
- name: Run tests
  run: ./cli/target/release/zecdev test
```

**Expected:**
- ✅ Workflow completes in < 20 minutes
- ✅ All smoke tests pass
- ✅ Logs uploaded as artifacts

---

## Performance Benchmarks

| Metric | Target | Actual |
|--------|--------|--------|
| Startup time | < 15 min | ~10-12 min |
| Block mining | 101 blocks | ✅ |
| Test execution | < 2 min | ~30-60 sec |
| Memory usage | < 4GB | ~2-3GB |
| Disk usage | < 5GB | ~3GB |

---

## M3 Future Tests

Coming in Milestone 3:

- ✅ Shielded transactions (orchard → orchard)
- ✅ Autoshield workflow
- ✅ Memo field support
- ✅ Backend parity (lightwalletd ↔ Zaino)
- ✅ Rescan/sync edge cases
- ✅ GitHub Action integration

---

## Sign-Off

**Milestone 2 is considered complete when:**

1. ✅ All 5 smoke tests pass
2. ✅ Real transactions work on regtest
3. ✅ UA fixtures are generated
4. ✅ CI pipeline passes
5. ✅ Documentation is complete
6. ✅ Known issues are documented

**Status:** ✅ M2 Complete  
**Date:** November 24, 2025  
**Next:** Begin M3 development