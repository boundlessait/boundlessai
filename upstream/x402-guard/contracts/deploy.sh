#!/bin/bash
# Deploy GuardLog to X Layer testnet
# X Layer testnet RPC: https://testrpc.xlayer.tech
# Or mainnet: https://rpc.xlayer.tech
# Chain ID testnet: 195, mainnet: 196

set -e

# Check if cast/forge is available
if ! command -v cast &> /dev/null; then
  echo "Installing Foundry..."
  curl -L https://foundry.paradigm.xyz | bash
  # shellcheck source=/dev/null
  source "$HOME/.bashrc" 2>/dev/null || source "$HOME/.profile" 2>/dev/null || true
  foundryup
fi

if [ -z "$DEPLOYER_PRIVATE_KEY" ]; then
  echo "ERROR: DEPLOYER_PRIVATE_KEY env var is not set"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

RPC_URL="${XLAYER_RPC_URL:-https://testrpc.xlayer.tech}"
CHAIN_ID="${XLAYER_CHAIN_ID:-195}"

echo "Deploying GuardLog.sol to X Layer testnet..."
echo "  RPC  : $RPC_URL"
echo "  Chain: $CHAIN_ID"

# Deploy using forge create (run from project root so the path resolves)
cd "$PROJECT_ROOT"
OUTPUT=$(forge create contracts/GuardLog.sol:GuardLog \
  --rpc-url "$RPC_URL" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  --broadcast 2>&1)

echo "$OUTPUT"

# Extract the deployed address from forge output
DEPLOYED_ADDR=$(echo "$OUTPUT" | grep -oP 'Deployed to: \K0x[0-9a-fA-F]+' || true)

if [ -n "$DEPLOYED_ADDR" ]; then
  echo ""
  echo "Contract deployed at: $DEPLOYED_ADDR"
  echo "Explorer: https://www.oklink.com/xlayer-test/address/$DEPLOYED_ADDR"

  # Save to deployed.json
  cat > "$SCRIPT_DIR/deployed.json" <<EOF
{
  "contract": "GuardLog",
  "address": "$DEPLOYED_ADDR",
  "network": "xlayer-testnet",
  "chainId": $CHAIN_ID,
  "rpcUrl": "$RPC_URL",
  "explorerUrl": "https://www.oklink.com/xlayer-test/address/$DEPLOYED_ADDR",
  "deployedAt": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF
  echo "Saved to contracts/deployed.json"
else
  echo "Warning: could not extract deployed address from output"
fi
