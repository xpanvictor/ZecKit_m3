# ZecKit E2E Action

A GitHub Action for running end-to-end tests on Zcash components using ZecKit.

> **Note:** This action is designed to be published to the GitHub Marketplace for easy consumption across repositories.

## Usage

```yaml
- name: Run ZecKit E2E Tests
  uses: your-org/zeckit/.github/actions/zeckit-e2e@main
  with:
    backend: 'lwd'  # or 'zaino'
    timeout: '30'   # minutes
    chain-params: 'regtest'
```

Or when published to marketplace:

```yaml
- name: Run ZecKit E2E Tests
  uses: your-org/zeckit-e2e-action@v1
  with:
    backend: 'lwd'
    timeout: '30'
    chain-params: 'regtest'
```

## Inputs

### Required Inputs

- `backend`: Light-client backend to use
  - `lwd` (lightwalletd) - production-ready, required passing
  - `zaino` - experimental indexer, may have issues

### Optional Inputs

- `timeout`: Test execution timeout in minutes (default: `30`)
- `chain-params`: Chain parameters (default: `regtest`)
  - `regtest`: Local testing network
  - `testnet`: Zcash test network
  - `mainnet`: Zcash main network (not recommended for CI)
- `zeckit-version`: ZecKit CLI version/tag to use (default: `latest`)

## Outputs

- `test-results`: JSON string with test status
  - `{"status":"passed"}` or `{"status":"failed"}`
- `logs`: Path to collected log files (relative to workspace)

## Artifacts

The action automatically collects and makes available the following log files:

- `status.log`: ZecKit CLI status output
- `zebra.log`: Zebra node logs
- `backend.log`: Backend service logs (lightwalletd or zaino)
- `zingo.log`: Zingo wallet logs

**Finding Artifacts:**
1. Go to the Actions tab in your repository
2. Click on the completed workflow run
3. Scroll down to "Artifacts" section
4. Download the `e2e-logs-{backend}` artifact

## Local Development

While the action is designed for CI environments, you can test locally:

### Prerequisites
- Docker and Docker Compose
- Rust toolchain (for building CLI)
- Linux/macOS environment

### Local Testing Steps

1. **Clone and build ZecKit:**
   ```bash
   git clone https://github.com/your-org/zeckit
   cd zeckit/cli
   cargo build --release
   cd ..
   ```

2. **Run tests manually:**
   ```bash
   # Start devnet
   ./cli/target/release/zeckit up --backend lwd --fresh

   # Run golden E2E tests
   ./cli/target/release/zeckit test --golden

   # Check status
   ./cli/target/release/zeckit status

   # Cleanup
   ./cli/target/release/zeckit down --purge
   ```

3. **Check logs:**
   ```bash
   docker logs zeckit-zebra
   docker logs zeckit-lightwalletd
   docker logs zeckit-zingo-wallet
   ```

## Troubleshooting

### Common Failure Modes

#### 1. Service Startup Timeout
**Symptoms:** Action fails with "Services did not become ready"
**Causes:**
- Insufficient resources (CPU/RAM)
- Slow network connectivity
- Docker daemon issues

**Solutions:**
- Increase timeout: `timeout: '45'`
- Use larger runner: `runs-on: ubuntu-latest-8-cores`
- Check Docker status: `docker system info`

#### 2. Backend Connection Issues
**Symptoms:** "Backend detection failed" or "No backend detected"
**Causes:**
- Backend service crashed during startup
- Network issues between containers
- Incorrect backend configuration

**Solutions:**
- Check backend logs in artifacts
- Verify backend parameter: `backend: 'lwd'` or `backend: 'zaino'`
- Ensure Docker networking is working

#### 3. Wallet Operation Failures
**Symptoms:** Golden E2E steps fail (funding, shielding, sending)
**Causes:**
- Insufficient block generation
- Faucet service issues
- Zingo wallet connectivity problems

**Solutions:**
- Check zingo.log for wallet errors
- Verify zebra is mining blocks
- Check faucet service logs

#### 4. Resource Exhaustion
**Symptoms:** Container crashes or OOM errors
**Causes:**
- Insufficient RAM/CPU allocation
- Large blockchain state
- Concurrent jobs on same runner

**Solutions:**
- Increase runner resources
- Add `docker system prune -a` before tests
- Run tests sequentially, not in parallel

### Debug Mode

For additional debugging, you can:

1. **Enable verbose logging:**
   ```yaml
   - name: Run ZecKit E2E Tests
     uses: ./.github/actions/zeckit-e2e
     with:
       backend: 'lwd'
       timeout: '60'  # Give more time
   ```

2. **Check container status:**
   ```bash
   docker ps -a
   docker logs <container_id>
   ```

3. **Manual intervention:**
   ```bash
   # Connect to running containers
   docker exec -it zeckit-zebra bash
   docker exec -it zeckit-lightwalletd bash
   ```

## Requirements

- **Runner OS:** Linux (ubuntu-latest recommended)
- **Docker:** Engine ≥ 24.x + Compose v2
- **Resources:** 2 CPU cores, 4GB RAM minimum (8GB recommended)
- **Network:** Outbound internet access for container pulls

## Support

For issues or questions:
- Check the troubleshooting section above
- Review the artifacts from failed runs
- Open an issue in the ZecKit repository