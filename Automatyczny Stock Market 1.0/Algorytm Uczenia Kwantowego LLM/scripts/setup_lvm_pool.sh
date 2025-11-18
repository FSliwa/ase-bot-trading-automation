#!/bin/bash
set -euo pipefail

# Idempotent LVM setup to pool multiple disks into one logical volume.
# Defaults:
#   DEVICES: space-separated list of block devices (e.g. "/dev/sdb /dev/sdc")
#   VG_NAME: volume group name (default: vgpool)
#   LV_NAME: logical volume name (default: data)
#   MOUNT_POINT: filesystem mount point (default: /srv/data)
#   FS_TYPE: ext4 | xfs | btrfs (default: ext4)
#   STRIPED: set to "1" to stripe across devices (like RAID0). Default: 0 (linear)
#   STRIPE_SIZE_KB: stripe size in KB if STRIPED=1 (default: 64)
#   ALLOW_DESTRUCTIVE: set to "1" to allow creating PVs and filesystems on raw devices (may wipe!)
#
# Usage examples:
#   DEVICES="/dev/sdb /dev/sdc" sudo -E bash setup_lvm_pool.sh
#   DEVICES="/dev/nvme1n1 /dev/nvme2n1" VG_NAME=vgdata LV_NAME=pool STRIPED=1 sudo -E bash setup_lvm_pool.sh

DEVICES=${DEVICES:-}
VG_NAME=${VG_NAME:-vgpool}
LV_NAME=${LV_NAME:-data}
MOUNT_POINT=${MOUNT_POINT:-/srv/data}
FS_TYPE=${FS_TYPE:-ext4}
STRIPED=${STRIPED:-0}
STRIPE_SIZE_KB=${STRIPE_SIZE_KB:-64}
ALLOW_DESTRUCTIVE=${ALLOW_DESTRUCTIVE:-0}

echo "--- LVM pool setup starting ---"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

if [[ -z "$DEVICES" ]]; then
  echo "ERROR: DEVICES environment variable is required (e.g., DEVICES=\"/dev/sdb /dev/sdc\")." >&2
  exit 1
fi

command -v lsblk >/dev/null || { echo "lsblk not found" >&2; exit 1; }
command -v blkid >/dev/null || { echo "blkid not found" >&2; exit 1; }
if ! command -v pvcreate >/dev/null; then
  echo "Installing lvm2..."
  apt-get update -y && apt-get install -y lvm2
fi

echo "Parameters:"
echo "  DEVICES:        $DEVICES"
echo "  VG_NAME:        $VG_NAME"
echo "  LV_NAME:        $LV_NAME"
echo "  MOUNT_POINT:    $MOUNT_POINT"
echo "  FS_TYPE:        $FS_TYPE"
echo "  STRIPED:        $STRIPED"
echo "  STRIPE_SIZE_KB: $STRIPE_SIZE_KB"
echo "  ALLOW_DESTRUCTIVE: $ALLOW_DESTRUCTIVE"

echo "\n-- Disk layout (lsblk) --"
lsblk -o NAME,FSTYPE,SIZE,TYPE,MOUNTPOINT

# Validate devices exist
for dev in $DEVICES; do
  if [[ ! -b "$dev" ]]; then
    echo "ERROR: Device $dev does not exist or is not a block device." >&2
    exit 1
  fi
done

echo "\n-- Ensuring Physical Volumes (PV) exist --"
for dev in $DEVICES; do
  existing_pv=$(pvs --noheadings -o pv_name 2>/dev/null | awk '{$1=$1};1' | grep -Fx "$dev" || true)
  if [[ -z "$existing_pv" ]]; then
    # Not a PV yet
    if [[ "$ALLOW_DESTRUCTIVE" == "1" ]]; then
      # Safety: refuse if mounted or has fs signature and force not requested
      if mount | grep -q "^$dev "; then
        echo "ERROR: $dev is mounted. Unmount before proceeding." >&2
        exit 1
      fi
      sig=$(blkid -o value -s TYPE "$dev" || true)
      if [[ -n "$sig" ]]; then
        echo "WARN: $dev has existing filesystem signature: $sig"
        echo "      Proceeding to pvcreate may make data inaccessible."
      fi
      echo "Creating PV on $dev"
      pvcreate -ff -y "$dev"
    else
      echo "ERROR: $dev is not a PV. Re-run with ALLOW_DESTRUCTIVE=1 to initialize PVs." >&2
      exit 1
    fi
  else
    echo "PV present on $dev"
  fi
done

echo "\n-- Ensuring Volume Group (VG) $VG_NAME exists --"
vg_exists=$(vgs --noheadings -o vg_name 2>/dev/null | awk '{$1=$1};1' | grep -Fx "$VG_NAME" || true)
if [[ -z "$vg_exists" ]]; then
  echo "Creating VG $VG_NAME with devices: $DEVICES"
  vgcreate "$VG_NAME" $DEVICES
else
  echo "VG $VG_NAME exists; ensuring all PVs are added"
  for dev in $DEVICES; do
    in_vg=$(pvs --noheadings -o pv_name,vg_name | awk '{$1=$1};1' | awk '$2=="'"$VG_NAME"'" {print $1}' | grep -Fx "$dev" || true)
    if [[ -z "$in_vg" ]]; then
      # If PV belongs to another VG, refuse
      other_vg=$(pvs --noheadings -o pv_name,vg_name | awk '$1=="'"$dev"'" {print $2}')
      if [[ -n "$other_vg" && "$other_vg" != "$VG_NAME" ]]; then
        echo "ERROR: $dev belongs to VG $other_vg. Please move/remove from that VG first." >&2
        exit 1
      fi
      echo "Adding $dev to VG $VG_NAME"
      vgextend "$VG_NAME" "$dev"
    else
      echo "$dev already in VG $VG_NAME"
    fi
  done
fi

echo "\n-- Ensuring Logical Volume (LV) $LV_NAME exists --"
lv_path="/dev/$VG_NAME/$LV_NAME"
if ! lvdisplay "$lv_path" >/dev/null 2>&1; then
  if [[ "$STRIPED" == "1" ]]; then
    num_devs=$(echo $DEVICES | wc -w | awk '{print $1}')
    echo "Creating striped LV across $num_devs devices: $lv_path"
    lvcreate -i "$num_devs" -I "$STRIPE_SIZE_KB" -l 100%FREE -n "$LV_NAME" "$VG_NAME"
  else
    echo "Creating linear LV: $lv_path"
    lvcreate -l 100%FREE -n "$LV_NAME" "$VG_NAME"
  fi
else
  echo "LV $lv_path already exists"
fi

echo "\n-- Ensuring filesystem on $lv_path --"
fs_type=$(blkid -o value -s TYPE "$lv_path" || true)
if [[ -z "$fs_type" ]]; then
  echo "Creating filesystem $FS_TYPE on $lv_path"
  case "$FS_TYPE" in
    ext4)
      mkfs.ext4 -F -L "$LV_NAME" "$lv_path" ;;
    xfs)
      mkfs.xfs -f -L "$LV_NAME" "$lv_path" ;;
    btrfs)
      mkfs.btrfs -f -L "$LV_NAME" "$lv_path" ;;
    *)
      echo "Unsupported FS_TYPE: $FS_TYPE" >&2; exit 1 ;;
  esac
else
  echo "Filesystem already present on $lv_path: $fs_type"
fi

echo "\n-- Ensuring mount point $MOUNT_POINT and fstab entry --"
mkdir -p "$MOUNT_POINT"
uuid=$(blkid -s UUID -o value "$lv_path")
if [[ -z "$uuid" ]]; then
  echo "ERROR: Could not determine UUID for $lv_path" >&2
  exit 1
fi

fstab_line="UUID=$uuid  $MOUNT_POINT  $FS_TYPE  defaults,nofail  0  2"
if ! grep -q "^UUID=$uuid\s\+$MOUNT_POINT\s" /etc/fstab 2>/dev/null; then
  echo "$fstab_line" >> /etc/fstab
  echo "Added to /etc/fstab: $fstab_line"
else
  echo "fstab entry already present for $lv_path"
fi

echo "\n-- Mounting $MOUNT_POINT --"
mountpoint -q "$MOUNT_POINT" || mount "$MOUNT_POINT"
df -h "$MOUNT_POINT" | tail -n +1

echo "--- LVM pool setup completed successfully ---"


