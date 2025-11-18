#!/bin/bash
set -euo pipefail

echo "--- Disk and filesystem probe ---"
command -v lsblk >/dev/null || { echo "lsblk not found" >&2; exit 1; }

lsblk -o NAME,MODEL,SIZE,TYPE,FSTYPE,FSAVAIL,FSUSE%,MOUNTPOINT
echo
echo "-- Existing RAID (mdadm) devices --"
cat /proc/mdstat || true
echo
echo "-- Existing LVM --"
vgs || true
pvs || true
lvs || true
echo
echo "-- blkid signatures --"
blkid || true

echo "Tip: Identify target raw devices (e.g., /dev/sdb /dev/sdc). If they contain data, do NOT proceed without backups."


