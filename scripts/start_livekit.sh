#!/bin/bash

# Start LiveKit server
# This script starts a local LiveKit server for development

echo "=========================================="
echo "Starting LiveKit Server"
echo "=========================================="

# Check if LiveKit is installed
if ! command -v livekit-server &> /dev/null; then
    echo "LiveKit server is not installed."
    echo ""
    echo "To install LiveKit server:"
    echo "1. Visit: https://docs.livekit.io/realtime/self-hosting/local/"
    echo "2. Download the latest release for your platform"
    echo "3. Or use Docker:"
    echo "   docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server --dev"
    echo ""
    exit 1
fi

# Start LiveKit in development mode
echo "Starting LiveKit server in development mode..."
echo "URL: ws://localhost:7880"
echo "API Key: devkey"
echo "API Secret: secret"
echo ""

livekit-server --dev --bind 0.0.0.0
