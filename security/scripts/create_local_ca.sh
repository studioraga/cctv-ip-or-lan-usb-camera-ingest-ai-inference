#!/usr/bin/env bash
set -euo pipefail
mkdir -p security/ca security/certs
openssl genrsa -out security/ca/local_ai_camera_ca.key 4096
openssl req -x509 -new -nodes -key security/ca/local_ai_camera_ca.key -sha256 -days 3650 \
  -subj "/CN=Local AI Camera Lab CA" \
  -out security/ca/local_ai_camera_ca.crt
echo "Created local CA under security/ca/"
