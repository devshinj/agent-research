#!/bin/bash
mkdir -p "$(dirname "$0")"
openssl req -x509 -nodes -days 365 \
    -newkey rsa:2048 \
    -keyout "$(dirname "$0")/key.pem" \
    -out "$(dirname "$0")/cert.pem" \
    -subj "/CN=paper-trader/O=Local/C=KR"
echo "Self-signed certificate generated."
