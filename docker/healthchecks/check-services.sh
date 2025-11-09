#!/bin/bash
# Health check script for Zebra node
# Waits for Zebra to be fully operational before proceeding

set -e

# Configuration
MAX_WAIT=${MAX_WAIT:-120}  # Maximum wait time in seconds
INTERVAL=${INTERVAL:-5}    # Check interval in seconds
ZEBRA_RPC_URL=${ZEBRA_RPC_URL:-"http://127.0.0.1:8232"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if Zebra RPC is responding
check_zebra_rpc() {
    local response
    response=$(curl -sf --max-time 5 \
        --data-binary '{"jsonrpc":"2.0","id":"1","method":"getinfo","params":[]}' \
        -H 'content-type: application/json' \
        "$ZEBRA_RPC_URL" 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        # Check if response contains expected fields
        if echo "$response" | grep -q '"result"'; then
            return 0
        fi
    fi
    return 1
}

# Function to check if Zebra is synced (for regtest, should be instant)
check_zebra_sync() {
    local response
    response=$(curl -sf --max-time 5 \
        --data-binary '{"jsonrpc":"2.0","id":"1","method":"getblockchaininfo","params":[]}' \
        -H 'content-type: application/json' \
        "$ZEBRA_RPC_URL" 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        # For regtest, any block count means we're synced
        if echo "$response" | grep -q '"blocks"'; then
            return 0
        fi
    fi
    return 1
}

# Main health check loop
main() {
    log_info "Starting Zebra health check..."
    log_info "RPC URL: $ZEBRA_RPC_URL"
    log_info "Max wait: ${MAX_WAIT}s, Check interval: ${INTERVAL}s"
    
    elapsed=0
    
    # First, wait for RPC to respond
    log_info "Waiting for Zebra RPC to respond..."
    while [ $elapsed -lt $MAX_WAIT ]; do
        if check_zebra_rpc; then
            log_info "✓ Zebra RPC is responding"
            break
        fi
        
        if [ $elapsed -gt 0 ]; then
            log_warn "Zebra RPC not ready yet (${elapsed}s elapsed)..."
        fi
        
        sleep $INTERVAL
        elapsed=$((elapsed + INTERVAL))
    done
    
    if [ $elapsed -ge $MAX_WAIT ]; then
        log_error "✗ Timeout waiting for Zebra RPC to respond"
        log_error "Waited ${MAX_WAIT}s without success"
        exit 1
    fi
    
    # Check if blockchain is initialized
    log_info "Checking blockchain initialization..."
    elapsed=0
    
    while [ $elapsed -lt $MAX_WAIT ]; do
        if check_zebra_sync; then
            log_info "✓ Zebra blockchain is initialized"
            break
        fi
        
        log_warn "Waiting for blockchain initialization (${elapsed}s elapsed)..."
        sleep $INTERVAL
        elapsed=$((elapsed + INTERVAL))
    done
    
    if [ $elapsed -ge $MAX_WAIT ]; then
        log_error "✗ Timeout waiting for blockchain initialization"
        exit 1
    fi
    
    # Get and display info
    log_info "Fetching Zebra info..."
    info=$(curl -sf --max-time 5 \
        --data-binary '{"jsonrpc":"2.0","id":"1","method":"getinfo","params":[]}' \
        -H 'content-type: application/json' \
        "$ZEBRA_RPC_URL" 2>/dev/null | grep -o '"version":[^,]*' || echo "version unknown")
    
    log_info "Zebra version: $info"
    
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log_info "✓ All health checks passed!"
    log_info "✓ Zebra is ready for testing"
    log_info "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    exit 0
}

# Run main function
main "$@"
