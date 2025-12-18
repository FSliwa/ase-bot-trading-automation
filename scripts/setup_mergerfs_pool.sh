#!/bin/bash
set -euo pipefail

# Idempotent mergerfs pool setup for existing filesystems without formatting.
# Environment variables:
#   BRANCHES     - colon-separated list of source paths (default: /root_storage:/data)
#   MOUNT_POINT  - target mountpoint (default: /mnt/storage)
#   MINFREE      - minfreespace option (default: 10G)
#   OPTIONS_EXTRA- extra options appended to defaults (default: empty)

BRANCHES=${BRANCHES:-/root_storage:/data}
MOUNT_POINT=${MOUNT_POINT:-/mnt/storage}
MINFREE=${MINFREE:-10G}
OPTIONS_EXTRA=${OPTIONS_EXTRA:-}

echo "--- mergerfs pool setup starting ---"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y mergerfs

# Ensure allow_other is permitted by FUSE
if ! grep -q '^user_allow_other' /etc/fuse.conf 2>/dev/null; then
  echo 'user_allow_other' >> /etc/fuse.conf
fi

# Ensure branch directories exist
mkdir -p /root_storage
mkdir -p "$MOUNT_POINT"

# Ensure /root_storage is a bind mount of /
if ! mountpoint -q /root_storage; then
  mount --bind / /root_storage
fi

base_opts="defaults,allow_other,use_ino,category.create=mfs,moveonenospc=true,minfreespace=${MINFREE},fsname=pool"
[[ -n "$OPTIONS_EXTRA" ]] && base_opts="${base_opts},${OPTIONS_EXTRA}"

# Update /etc/fstab entry for mergerfs
tmpfstab=$(mktemp)
awk -v mp="$MOUNT_POINT" -v fstype="fuse.mergerfs" '{ if (!($2==mp && $3==fstype)) print }' /etc/fstab > "$tmpfstab"
echo "${BRANCHES}  ${MOUNT_POINT}  fuse.mergerfs  ${base_opts}  0  0" >> "$tmpfstab"
mv "$tmpfstab" /etc/fstab

# Remount
umount "$MOUNT_POINT" 2>/dev/null || true
mount -a

echo "-- Current mount:"
grep -E "\s${MOUNT_POINT}\s" /proc/mounts || true
df -h "$MOUNT_POINT" || true

echo "--- mergerfs pool setup completed ---"


