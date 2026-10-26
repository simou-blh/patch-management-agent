#!/usr/bin/env bash
# Run in WSL after vagrant up on Windows. Usage: bash scripts/sync_lab_keys.sh /mnt/c/lab
set -euo pipefail
lab_path="${1:-/mnt/c/lab}"
key_dir="$HOME/.ssh/patch-lab"
# Validate all inputs before copying any keys.
for host in vm-01 vm-02 vm-03; do
  test -f "$lab_path/.vagrant/machines/$host/virtualbox/private_key" || {
    echo "Missing $host key. Start the lab with Vagrant first." >&2
    exit 1
  }
done
install -d -m 700 "$key_dir"
for host in vm-01 vm-02 vm-03; do
  install -m 600 "$lab_path/.vagrant/machines/$host/virtualbox/private_key" "$key_dir/$host"
done
echo "Copied three keys into $key_dir. Verify host fingerprints before first SSH use."
