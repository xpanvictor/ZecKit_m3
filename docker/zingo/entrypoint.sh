#!/bin/bash
set -e

echo "🔧 Initializing Zingo Wallet..."

# Wait for lightwalletd
echo "⏳ Waiting for lightwalletd..."
MAX_ATTEMPTS=60
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if nc -z lightwalletd 9067 2>/dev/null; then
        echo "✅ Lightwalletd port is open!"
        break
    fi
    ATTEMPT=$((ATTEMPT + 1))
    echo "Attempt $ATTEMPT/$MAX_ATTEMPTS - lightwalletd not ready yet..."
    sleep 2
done

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    echo "❌ Lightwalletd did not become ready in time"
    exit 1
fi

# Give lightwalletd time to initialize
echo "⏳ Giving lightwalletd 30 seconds to fully initialize..."
sleep 30

# Create wallet if doesn't exist
if [ ! -f "/var/zingo/zingo-wallet.dat" ]; then
    echo "📝 Creating new wallet..."
    
    # Just initialize the wallet
    zingo-cli --data-dir /var/zingo \
              --server http://lightwalletd:9067 \
              --nosync << 'EOF'
quit
EOF
    
    echo "✅ Wallet created!"
    
    # Get wallet address
    WALLET_ADDRESS=$(zingo-cli --data-dir /var/zingo \
                               --server http://lightwalletd:9067 \
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
          --server http://lightwalletd:9067 << 'EOF' || true
sync run
quit
EOF

echo "✅ Wallet is ready! (Sync will complete after mining blocks)"
tail -f /dev/null