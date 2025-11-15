#!/bin/bash
# Fund the faucet wallet with test ZEC
# This script mines blocks and sends funds to the faucet

set -e

ZEBRA_RPC_URL=${ZEBRA_RPC_URL:-"http://127.0.0.1:8232"}
FAUCET_API_URL=${FAUCET_API_URL:-"http://127.0.0.1:8080"}
AMOUNT=${1:-1000}  # Default 1000 ZEC

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ZecKit - Fund Faucet Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Function to make RPC calls
rpc_call() {
    local method=$1
    shift
    local params="$@"
    
    if [ -z "$params" ]; then
        params="[]"
    fi
    
    curl -sf --max-time 30 \
        --data-binary "{\"jsonrpc\":\"2.0\",\"id\":\"fund\",\"method\":\"$method\",\"params\":$params}" \
        -H 'content-type: application/json' \
        "$ZEBRA_RPC_URL"
}

# Step 1: Get faucet address
echo -e "${BLUE}[1/4]${NC} Getting faucet address..."
FAUCET_ADDR=$(curl -sf $FAUCET_API_URL/address | jq -r '.address')

if [ -z "$FAUCET_ADDR" ] || [ "$FAUCET_ADDR" = "null" ]; then
    echo -e "${YELLOW}✗ Could not get faucet address${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Faucet address: $FAUCET_ADDR${NC}"
echo ""

# Step 2: Generate miner address and mine blocks
echo -e "${BLUE}[2/4]${NC} Mining blocks to generate funds..."

# Note: Zebra regtest doesn't have a built-in miner address
# We'll need to use the faucet address itself or a temporary address
MINER_ADDR=$FAUCET_ADDR

echo "  Mining 200 blocks (this may take 30-60 seconds)..."

# Try to mine blocks
MINE_RESULT=$(rpc_call "generate" "[200]" 2>&1) || true

if echo "$MINE_RESULT" | grep -q '"result"'; then
    BLOCKS=$(echo "$MINE_RESULT" | jq -r '.result | length')
    echo -e "${GREEN}✓ Mined $BLOCKS blocks${NC}"
else
    echo -e "${YELLOW}⚠ Block generation may not be supported${NC}"
    echo "  Zebra regtest may need manual configuration"
    echo "  Error: $(echo "$MINE_RESULT" | jq -r '.error.message' 2>/dev/null || echo "$MINE_RESULT")"
fi
echo ""

# Step 3: Update faucet balance manually
echo -e "${BLUE}[3/4]${NC} Updating faucet balance..."
echo "  Adding $AMOUNT ZEC to faucet..."

# Use curl to call a manual endpoint (we'll create this)
# For now, we'll document that manual balance update is needed
echo -e "${YELLOW}⚠ Manual balance update required${NC}"
echo ""
echo "Run this command to add funds:"
echo ""
echo "  docker compose exec faucet python -c \\"
echo "    \"from app.main import create_app; \\"
echo "     app = create_app(); \\"
echo "     app.faucet_wallet.add_funds($AMOUNT); \\"
echo "     print(f'Balance: {app.faucet_wallet.get_balance()} ZEC')\""
echo ""

# Step 4: Verify
echo -e "${BLUE}[4/4]${NC} Verification..."
CURRENT_BALANCE=$(curl -sf $FAUCET_API_URL/address | jq -r '.balance')
echo "  Current faucet balance: $CURRENT_BALANCE ZEC"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}✓ Funding script complete${NC}"
echo ""
echo "Next steps:"
echo "  1. Verify faucet balance: curl $FAUCET_API_URL/stats"
echo "  2. Test funding: curl -X POST $FAUCET_API_URL/request \\"
echo "       -H 'Content-Type: application/json' \\"
echo "       -d '{\"address\": \"t1abc...\", \"amount\": 10}'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""