# ZecKit E2E Action

A GitHub Action for running end-to-end tests on Zcash components using ZecKit.

## Usage

```yaml
- name: Run ZecKit E2E Tests
  uses: your-org/zeckit/.github/actions/zeckit-e2e@main
  with:
    backend: 'lwd'  # or 'zaino'
    timeout: '30'   # minutes
    chain-params: 'regtest'
```

## Inputs

- `backend`: Light-client backend to use
  - `lwd` (lightwalletd) - required passing
  - `zaino` - experimental
- `timeout`: Test execution timeout in minutes (default: 30)
- `chain-params`: Chain parameters (default: regtest)
- `zeckit-version`: ZecKit CLI version (default: latest)

## Outputs

- `test-results`: JSON string with test status
- `logs`: Path to test logs

## What it does

1. Builds the ZecKit CLI
2. Starts the ZecKit devnet with the specified backend
3. Waits for services to be healthy
4. Runs the golden E2E test flow:
   - Generate Unified Address
   - Fund the address
   - Autoshield transparent funds
   - Send shielded transaction
   - Rescan/sync wallet
   - Verify balances and transactions
5. Collects logs and artifacts
6. Cleans up resources

## Requirements

- Docker and Docker Compose must be available
- Linux runner (ubuntu-latest recommended)
- Sufficient resources for running Zcash nodes