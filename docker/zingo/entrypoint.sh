#!/bin/bash
set -e

echo "🔧 Initializing Zingo Wallet..."

# Get backend URI from environment variable (set by docker-compose)
BACKEND_URI=${LIGHTWALLETD_URI:-http://lightwalletd:9067}

# Extract hostname from URI for health check
BACKEND_HOST=$(echo $BACKEND_URI | sed 's|http://||' | cut -d: -f1)
BACKEND_PORT=$(echo $BACKEND_URI | sed 's|http://||' | cut -d: -f2)

echo "Configuration:"
echo "  Backend URI:  ${BACKEND_URI}"
echo "  Backend Host: ${BACKEND_HOST}"
echo "  Backend Port: ${BACKEND_PORT}"

# Wait for backend (lightwalletd OR zaino)
echo "⏳ Waiting for backend (${BACKEND_HOST})..."
MAX_ATTEMPTS=60
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if nc -z ${BACKEND_HOST} ${BACKEND_PORT} 2>/dev/null; then
        echo "✅ Backend port is open!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "Attempt $ATTEMPT/$MAX_ATTEMPTS - backend not ready yet..."
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Backend did not become ready in time"
    exit 1
fi

# Give backend time to initialize
echo "⏳ Giving backend 30 seconds to fully initialize..."
sleep 30

# Create wallet if doesn't exist
if [ ! -f "/var/zingo/zingo-wallet.dat" ]; then
    echo "📝 Creating new wallet..."
    
    # Just initialize the wallet
    zingo-cli --data-dir /var/zingo \
              --server ${BACKEND_URI} \
              --nosync << 'EOF'
quit
EOF
    
    echo "✅ Wallet created!"
    
    # Get wallet address
    WALLET_ADDRESS=$(zingo-cli --data-dir /var/zingo \
                               --server ${BACKEND_URI} \
                               --nosync << 'EOF' | grep -oP '"address":\s*"\K[^"]+' | head -1
addresses
quit
EOF
)
    
    echo "📍 Wallet Address: $WALLET_ADDRESS"
    echo "$WALLET_ADDRESS" > /var/zingo/faucet-address.txt
else
    echo "✅ Existing wallet found"
fi

# Sync wallet (ignore errors if no blocks yet)
echo "🔄 Syncing wallet (will complete after blocks are mined)..."
zingo-cli --data-dir /var/zingo \
          --server ${BACKEND_URI} << 'EOF' || true
sync run
quit
EOF

echo "✅ Wallet is ready! (Sync will complete after mining blocks)"
tail -f /dev/null