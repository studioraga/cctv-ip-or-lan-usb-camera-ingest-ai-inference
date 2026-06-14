#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"
fail=0
scan() {
  local pattern="$1"; shift
  if grep -RInE "$pattern" "$@" --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.pytest_cache --exclude-dir=runtime --exclude='*.db*' --exclude='validate_portability.sh'; then
    fail=1
  fi
}
echo '[CHECK] user-specific absolute home paths'
scan '/home/(rmk|srrmk)/|ai-camera-node1-node2-agent-framework' systemd scripts services configs policies docker docs README.md
echo '[CHECK] premises-specific private LAN addresses in executable/config files'
scan '192\.168\.29\.' systemd scripts services configs policies docker
if (( fail )); then echo '[FAIL] portability scan found hardcoded deployment values' >&2; exit 1; fi
echo '[OK] portability scan passed'
