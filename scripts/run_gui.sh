#!/usr/bin/env bash
echo "==================================================="
echo " ⚡ PRODUCTIFY NODE DESKTOP CLIENT"
echo "==================================================="
echo "Starting Productify Node..."
if command -v python3 &>/dev/null; then
    python3 main.py "$@"
else
    python main.py "$@"
fi
