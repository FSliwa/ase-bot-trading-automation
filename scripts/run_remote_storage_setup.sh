#!/bin/bash
set -euo pipefail

# Wrapper to copy probe/setup scripts to a remote host and execute them.
# Supports password auth via SSHPASS env var (uses sshpass if provided), or key-based auth if not.
# Required env vars:
#   REMOTE_USER (e.g., admin or root)
#   REMOTE_HOST (e.g., 185.70.196.214)
# Optional for LVM:
#   DEVICES     (e.g., "/dev/sdb /dev/sdc")
#   VG_NAME, LV_NAME, MOUNT_POINT, FS_TYPE, STRIPED, STRIPE_SIZE_KB, ALLOW_DESTRUCTIVE
# Optional for mergerfs:
#   BRANCHES, MOUNT_POINT, MINFREE, OPTIONS_EXTRA

REMOTE_USER=${REMOTE_USER:-}
REMOTE_HOST=${REMOTE_HOST:-}
DEVICES=${DEVICES:-}
SUDO_PASSWORD=${SUDO_PASSWORD:-${SSHPASS:-}}

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "ERROR: REMOTE_USER and REMOTE_HOST are required." >&2
  exit 1
fi

# Note: DEVICES is only required if running LVM setup. For mergerfs-only flows it's optional.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SCP="scp"
SSH="ssh"
if [[ -n "${SSHPASS:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "Installing sshpass locally (requires sudo)..."
    sudo apt-get update -y && sudo apt-get install -y sshpass || true
  fi
  if command -v sshpass >/dev/null 2>&1; then
    SCP="sshpass -p \"$SSHPASS\" scp -o StrictHostKeyChecking=no"
    SSH="sshpass -p \"$SSHPASS\" ssh -o StrictHostKeyChecking=no"
  else
    echo "WARNING: sshpass not available; falling back to interactive ssh/scp."
  fi
fi

echo "--- Copying scripts to $REMOTE_USER@$REMOTE_HOST:/tmp ---"
$SCP "$SCRIPT_DIR/probe_disks.sh" "$SCRIPT_DIR/setup_lvm_pool.sh" "$SCRIPT_DIR/setup_mergerfs_pool.sh" "$REMOTE_USER@$REMOTE_HOST:/tmp/"

echo "--- Running probe on remote host ---"
if [[ -n "$SUDO_PASSWORD" ]]; then
  $SSH -t "$REMOTE_USER@$REMOTE_HOST" "echo '$SUDO_PASSWORD' | sudo -S bash /tmp/probe_disks.sh | sed -e 's/^/[remote] '/" || true
else
  $SSH -t "$REMOTE_USER@$REMOTE_HOST" "sudo bash /tmp/probe_disks.sh | sed -e 's/^/[remote] '/" || true
fi

echo "--- Executing LVM setup on remote host ---"
if [[ -n "${DEVICES:-}" ]]; then
  echo "--- Executing LVM setup on remote host ---"
  remote_cmd="DEVICES='$DEVICES' VG_NAME='${VG_NAME:-vgpool}' LV_NAME='${LV_NAME:-data}' MOUNT_POINT='${MOUNT_POINT:-/srv/data}' FS_TYPE='${FS_TYPE:-ext4}' STRIPED='${STRIPED:-0}' STRIPE_SIZE_KB='${STRIPE_SIZE_KB:-64}' ALLOW_DESTRUCTIVE='${ALLOW_DESTRUCTIVE:-0}' bash /tmp/setup_lvm_pool.sh"
  if [[ -n "$SUDO_PASSWORD" ]]; then
    $SSH -t "$REMOTE_USER@$REMOTE_HOST" "echo '$SUDO_PASSWORD' | sudo -S bash -lc \"$remote_cmd\""
  else
    $SSH -t "$REMOTE_USER@$REMOTE_HOST" "sudo bash -lc \"$remote_cmd\""
  fi
fi

if [[ -n "${BRANCHES:-}" || -n "${MERGERFS:=1}" ]]; then
  echo "--- Executing mergerfs setup on remote host ---"
  remote_cmd_mfs="BRANCHES='${BRANCHES:-/root_storage:/data}' MOUNT_POINT='${MOUNT_POINT:-/mnt/storage}' MINFREE='${MINFREE:-10G}' OPTIONS_EXTRA='${OPTIONS_EXTRA:-}' bash /tmp/setup_mergerfs_pool.sh"
  if [[ -n "$SUDO_PASSWORD" ]]; then
    $SSH -t "$REMOTE_USER@$REMOTE_HOST" "echo '$SUDO_PASSWORD' | sudo -S bash -lc \"$remote_cmd_mfs\""
  else
    $SSH -t "$REMOTE_USER@$REMOTE_HOST" "sudo bash -lc \"$remote_cmd_mfs\""
  fi
fi

echo "--- Done. Verify with: ssh $REMOTE_USER@$REMOTE_HOST 'df -h ${MOUNT_POINT:-/mnt/storage}' ---"


