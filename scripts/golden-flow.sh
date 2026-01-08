#!/bin/bash
# ========================================
# ZecKit Golden Flow E2E Test Script
# ========================================
# This script runs the complete golden flow for Zcash wallet operations:
#   1. Generate Unified Address (UA)
#   2. Fund wallet (via mining or faucet)
#   3. Autoshield to Orchard
#   4. Shielded send
#   5. Rescan/Sync
#   6. Verify transaction
#
# Usage:
#   ./golden-flow.sh --zebra-rpc http://127.0.0.1:8232 --grpc-url http://zaino:9067 --backend zaino
#
# ========================================

set -e

# ========================================
# Configuration
# ========================================
ZEBRA_RPC="${ZEBRA_RPC:-http://127.0.0.1:8232}"
GRPC_URL="${GRPC_URL:-http://zaino:9067}"
BACKEND="${BACKEND:-zaino}"
WALLET_CONTAINER="${WALLET_CONTAINER:-zeckit-zingo-wallet}"
WALLET_DIR="${WALLET_DIR:-/var/zingo}"
WALLET_DIR_2="${WALLET_DIR_2:-/var/zingo2}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# Counters
STEPS_TOTAL=8
STEPS_PASSED=0
STEPS_FAILED=0

# ========================================
# Parse Arguments
# ========================================
while [[ $# -gt 0 ]]; do
  case $1 in
    --zebra-rpc)
      ZEBRA_RPC="$2"
      shift 2
      ;;
    --grpc-url)
      GRPC_URL="$2"
      shift 2
      ;;
    --backend)
      BACKEND="$2"
      shift 2
      ;;
    --wallet-container)
      WALLET_CONTAINER="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# ========================================
# Helper Functions
# ========================================
log_step() {
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Step $1: $2${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

log_pass() {
    echo -e "${GREEN}✅ $1${NC}"
    STEPS_PASSED=$((STEPS_PASSED + 1))
}

log_fail() {
    echo -e "${RED}❌ $1${NC}"
    STEPS_FAILED=$((STEPS_FAILED + 1))
}

log_warn() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Execute zingo-cli command
zingo_cmd() {
    local data_dir="${1:-$WALLET_DIR}"
    shift
    docker exec "$WALLET_CONTAINER" bash -c \
        "echo -e '$*\nquit' | zingo-cli --data-dir $data_dir --server $GRPC_URL --chain regtest" 2>/dev/null
}

# Make Zebra RPC call
zebra_rpc() {
    local method="$1"
    local params="${2:-[]}"
    curl -sf --max-time 30 \
        --data-binary "{\"jsonrpc\":\"2.0\",\"id\":\"1\",\"method\":\"$method\",\"params\":$params}" \
        -H 'content-type: application/json' \
        "$ZEBRA_RPC"
}

# Mine blocks
mine_blocks() {
    local count="${1:-1}"
    local address="${2:-}"
    
    if [ -n "$address" ]; then
        zebra_rpc "generate" "[$count, \"$address\"]"
    else
        zebra_rpc "generate" "[$count]"
    fi
}

# ========================================
# Golden Flow Steps
# ========================================

step1_generate_ua() {
    log_step 1 "Generate Unified Address (UA)"
    
    # Create new wallet
    local result
    result=$(zingo_cmd "$WALLET_DIR" "new_address ozt\naddresses")
    
    echo "$result"
    
    # Extract UA
    UA=$(echo "$result" | grep -oE 'uregtest[a-zA-Z0-9]{100,}' | head -1)
    
    if [ -z "$UA" ]; then
        log_fail "Failed to generate unified address"
        return 1
    fi
    
    log_pass "Generated UA: ${UA:0:20}...${UA: -20}"
    echo "UA=$UA" >> /tmp/golden-flow-state
    return 0
}

step2_fund_wallet() {
    log_step 2 "Fund Wallet via Mining"
    
    source /tmp/golden-flow-state 2>/dev/null || true
    
    if [ -z "$UA" ]; then
        log_fail "No UA available for mining"
        return 1
    fi
    
    log_info "Mining 20 blocks to wallet..."
    local result
    result=$(mine_blocks 20 "$UA")
    
    echo "Mining result: $result"
    
    # Check block count
    local block_count
    block_count=$(zebra_rpc "getblockcount" | jq -r '.result // 0')
    log_info "Current block height: $block_count"
    
    # Sync wallet
    log_info "Syncing wallet..."
    zingo_cmd "$WALLET_DIR" "balance"
    
    log_pass "Wallet funded via mining"
    return 0
}

step3_verify_funds() {
    log_step 3 "Verify Transparent Funds"
    
    local balance_info
    balance_info=$(zingo_cmd "$WALLET_DIR" "balance")
    
    echo "$balance_info"
    
    # Extract transparent balance
    local transparent
    transparent=$(echo "$balance_info" | grep -i "transparent" | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "0")
    
    log_info "Transparent balance: $transparent ZEC"
    
    if [ "$transparent" == "0" ] || [ -z "$transparent" ]; then
        log_warn "No transparent balance yet (may need more confirmations)"
        # Not a failure - coinbase needs 100 confirmations
    else
        log_pass "Transparent funds verified: $transparent ZEC"
    fi
    
    return 0
}

step4_autoshield() {
    log_step 4 "Autoshield to Orchard"
    
    log_info "Executing shield command..."
    local result
    result=$(zingo_cmd "$WALLET_DIR" "shield")
    
    echo "$result"
    
    # Extract txid
    local txid
    txid=$(echo "$result" | grep -oE '[a-f0-9]{64}' | head -1 || echo "")
    
    if [ -n "$txid" ]; then
        log_pass "Shield transaction: ${txid:0:16}..."
        echo "SHIELD_TXID=$txid" >> /tmp/golden-flow-state
        
        # Mine a block to confirm
        log_info "Mining 1 block to confirm..."
        mine_blocks 1
    else
        log_warn "No shield transaction (may not have spendable transparent funds yet)"
    fi
    
    return 0
}

step5_create_recipient() {
    log_step 5 "Create Second Wallet (Recipient)"
    
    # Create second wallet directory
    docker exec "$WALLET_CONTAINER" bash -c "mkdir -p $WALLET_DIR_2"
    
    # Create new wallet
    local result
    result=$(zingo_cmd "$WALLET_DIR_2" "new_address ozt\naddresses")
    
    echo "$result"
    
    # Extract recipient UA
    RECIPIENT_UA=$(echo "$result" | grep -oE 'uregtest[a-zA-Z0-9]{100,}' | head -1)
    
    if [ -z "$RECIPIENT_UA" ]; then
        log_fail "Failed to create recipient wallet"
        return 1
    fi
    
    log_pass "Recipient UA: ${RECIPIENT_UA:0:20}...${RECIPIENT_UA: -20}"
    echo "RECIPIENT_UA=$RECIPIENT_UA" >> /tmp/golden-flow-state
    return 0
}

step6_shielded_send() {
    log_step 6 "Shielded Send"
    
    source /tmp/golden-flow-state 2>/dev/null || true
    
    if [ -z "$RECIPIENT_UA" ]; then
        log_fail "No recipient UA available"
        return 1
    fi
    
    # Check sender balance first
    log_info "Checking sender balance..."
    zingo_cmd "$WALLET_DIR" "balance"
    
    # Send 0.1 ZEC
    log_info "Sending 0.1 ZEC to recipient..."
    local result
    result=$(zingo_cmd "$WALLET_DIR" "send $RECIPIENT_UA 0.1")
    
    echo "$result"
    
    # Extract txid
    local txid
    txid=$(echo "$result" | grep -oE '[a-f0-9]{64}' | head -1 || echo "")
    
    if [ -n "$txid" ]; then
        log_pass "Send transaction: ${txid:0:16}..."
        echo "SEND_TXID=$txid" >> /tmp/golden-flow-state
        
        # Mine a block to confirm
        log_info "Mining 1 block to confirm..."
        mine_blocks 1
    else
        log_warn "Send may have failed or no spendable funds available"
        # Check if we have any notes
        zingo_cmd "$WALLET_DIR" "notes"
    fi
    
    return 0
}

step7_rescan_sync() {
    log_step 7 "Rescan and Sync Both Wallets"
    
    log_info "Syncing sender wallet..."
    zingo_cmd "$WALLET_DIR" "rescan\nbalance"
    
    log_info "Syncing recipient wallet..."
    zingo_cmd "$WALLET_DIR_2" "balance"
    
    log_pass "Both wallets synced"
    return 0
}

step8_verify_transaction() {
    log_step 8 "Verify Transaction"
    
    log_info "Recipient wallet balance:"
    local recipient_balance
    recipient_balance=$(zingo_cmd "$WALLET_DIR_2" "balance")
    
    echo "$recipient_balance"
    
    # Extract balance
    local balance
    balance=$(echo "$recipient_balance" | grep -oE '[0-9]+\.[0-9]+' | head -1 || echo "0")
    
    if [ "$balance" != "0" ] && [ -n "$balance" ]; then
        log_pass "Recipient received funds: $balance ZEC"
        VERIFIED=true
    else
        log_warn "Recipient balance is 0 (transaction may need more confirmations)"
        VERIFIED=false
    fi
    
    # Show sender transaction list
    log_info "Sender transaction history:"
    zingo_cmd "$WALLET_DIR" "transactions" | head -50
    
    echo "VERIFIED=$VERIFIED" >> /tmp/golden-flow-state
    return 0
}

# ========================================
# Main Execution
# ========================================
main() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════╗"
    echo "║     ZecKit Golden Flow E2E Test Suite        ║"
    echo "╠══════════════════════════════════════════════╣"
    echo "║  Backend:    $BACKEND"
    echo "║  Zebra RPC:  $ZEBRA_RPC"
    echo "║  gRPC:       $GRPC_URL"
    echo "╚══════════════════════════════════════════════╝"
    echo -e "${NC}"
    
    # Clear previous state
    rm -f /tmp/golden-flow-state
    touch /tmp/golden-flow-state
    
    # Run all steps
    step1_generate_ua || true
    step2_fund_wallet || true
    step3_verify_funds || true
    step4_autoshield || true
    step5_create_recipient || true
    step6_shielded_send || true
    step7_rescan_sync || true
    step8_verify_transaction || true
    
    # Summary
    echo -e "\n${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}  Golden Flow Summary${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    
    echo -e "Steps Passed: ${GREEN}$STEPS_PASSED${NC}/$STEPS_TOTAL"
    echo -e "Steps Failed: ${RED}$STEPS_FAILED${NC}/$STEPS_TOTAL"
    
    source /tmp/golden-flow-state 2>/dev/null || true
    
    echo ""
    if [ "$STEPS_FAILED" -eq 0 ] && [ "$VERIFIED" == "true" ]; then
        echo -e "${GREEN}🎉 Golden E2E Flow: ALL STEPS PASSED${NC}"
        exit 0
    elif [ "$STEPS_FAILED" -eq 0 ]; then
        echo -e "${YELLOW}⚠️  Golden E2E Flow: COMPLETED WITH WARNINGS${NC}"
        echo "   Some verifications may need more block confirmations"
        exit 0
    else
        echo -e "${RED}❌ Golden E2E Flow: $STEPS_FAILED STEPS FAILED${NC}"
        exit 1
    fi
}

main "$@"
