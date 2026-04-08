#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR"
openssl req -x509 -nodes -days 365 -newkey rsa:2048 -keyout "$SCRIPT_DIR/key.pem" -out "$SCRIPT_DIR/cert.pem" -subj "/CN=paper-trader/O=Local/C=KR"
echo "Self-signed certificate generated in $SCRIPT_DIR"
