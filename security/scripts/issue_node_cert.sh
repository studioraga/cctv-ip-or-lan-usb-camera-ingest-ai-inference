#!/usr/bin/env bash
set -euo pipefail
NODE_NAME="${1:?usage: $0 <node-name> <ip>}"
NODE_IP="${2:?usage: $0 <node-name> <ip>}"
mkdir -p security/certs
openssl genrsa -out "security/certs/${NODE_NAME}.key" 2048
cat > "security/certs/${NODE_NAME}.cnf" <<EOF
[req]
distinguished_name=req
[san]
subjectAltName=DNS:${NODE_NAME},IP:${NODE_IP}
EOF
openssl req -new -key "security/certs/${NODE_NAME}.key" -subj "/CN=${NODE_NAME}" -out "security/certs/${NODE_NAME}.csr"
openssl x509 -req -in "security/certs/${NODE_NAME}.csr" \
  -CA security/ca/local_ai_camera_ca.crt -CAkey security/ca/local_ai_camera_ca.key -CAcreateserial \
  -out "security/certs/${NODE_NAME}.crt" -days 825 -sha256 \
  -extfile "security/certs/${NODE_NAME}.cnf" -extensions san
echo "Issued cert for ${NODE_NAME} ${NODE_IP}"
EOF
