# OpenWrt Hyper-V VM: Disk Expansion & Boot Recovery

## When to Use

- Root partition is full (OpenWrt default disk images are ~120MB — too small for modern software like mihomo at 46MB)
- VM stuck in boot loop (e.g., after a failed init script or GRUB modification)
- Need to expand the rootfs on an existing VM

## Overview

OpenWrt x86_64 images typically have a ~100MB root partition (ext4 on sda2). After installing packages like OpenClash + mihomo core (46MB), the partition fills up quickly. Expansion requires three steps: Hyper-V disk resize, partition resize, and filesystem resize.

## Step 1: Hyper-V Disk Expansion (on Windows host)

### 1a. Remove snapshots/checkpoints first

If the VM has snapshots, the disk is a differencing AVHDX, not the base VHDX. Remove snapshots before expanding:

```powershell
# On the Hyper-V host
Get-VM -VMName <vm-name> | Get-VMSnapshot | Remove-VMSnapshot
# This merges the snapshot into the base VHDX
```

### 1b. Expand the VHDX

```powershell
# Check current size first
Get-VHD -Path "C:\hyper-v-vm\<vm-name>.vhdx" | Select-Object Path,Size,FileSize

# Shut down VM first
Stop-VM -VMName <vm-name> -Force

# Resize to target (e.g., 1GB = 1073741824 bytes)
Resize-VHD -Path "C:\hyper-v-vm\<vm-name>.vhdx" -SizeBytes 1GB

# Start VM
Start-VM -VMName <vm-name>
```

## Step 2: Expand Partition (on OpenWrt)

The VHDX is larger but the GPT partition table and ext4 filesystem don't know about it yet.

### 2a. Fix GPT header and resize partition

```bash
ssh root@<openwrt-ip>
opkg update && opkg install parted

# Fix the GPT backup header (uses all available space)
printf "fix\n" | parted /dev/sda unit MiB print free 2>&1

# Expand partition 2 (root) to near the end of disk
printf "1023MiB\n" | parted /dev/sda resizepart 2 2>&1
# Or for dynamic disks: calculate the end as <total_size>MiB - 1

# Verify
parted /dev/sda unit MiB print
# Partition 2 should now show ~1007MiB (for a 1024MiB disk)
```

### 2b. Resize filesystem

```bash
# Install resize2fs if not already
opkg install resize2fs

# Online resize (may fail on OpenWrt kernel if flex_bg feature is enabled)
resize2fs /dev/sda2
```

> **Common failure:** OpenWrt's kernel may not support online resize with the `resize_inode` + `flex_bg` ext4 features. The error `resize2fs: Invalid argument While trying to add group #1` means offline resize is needed.

### 2c. Offline Resize (when online fails)

If online resize fails, use `qemu-nbd` from your Linux host:

```bash
# 1. Copy VHDX from Hyper-V host to your Linux machine
scp user@hyperv-host:/C:/hyper-v-vm/<vm-name>.vhdx /tmp/<vm-name>.vhdx

# 2. Mount via NBD
sudo modprobe nbd max_part=8
sudo qemu-nbd -c /dev/nbd0 /tmp/<vm-name>.vhdx

# 3. Verify partitions
lsblk /dev/nbd0

# 4. Check and resize
sudo e2fsck -fy /dev/nbd0p2
sudo resize2fs /dev/nbd0p2

# 5. Verify
sudo dumpe2fs -h /dev/nbd0p2 | grep -E 'Block count:|Block size:'
# Expected: 257728 blocks × 4096 = ~1007MiB (for 1GB disk)

# 6. Disconnect
sudo qemu-nbd -d /dev/nbd0

# 7. Copy back
scp /tmp/<vm-name>.vhdx user@hyperv-host:/C:/hyper-v-vm/<vm-name>.vhdx
```

## Step 3: Boot Recovery (Fixing Boot Loops)

A VM stuck in a boot loop (repeatedly rebooting every few seconds) usually means:
- GRUB points to a bad kernel parameter (e.g., `init=/sbin/resize-rootfs`)
- The init script crashes → kernel panic → reboot

### 3a. Recovery via Offline VHDX Mount

Same NBD approach as step 2c:

```bash
sudo qemu-nbd -c /dev/nbd0 /tmp/<vm-name>.vhdx
sudo mount /dev/nbd0p1 /mnt/bootfix   # Boot partition (FAT16)

# Fix GRUB config
sudo tee /mnt/bootfix/boot/grub/grub.cfg > /dev/null << 'GRUB'
serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1 --rtscts=off
terminal_input console serial; terminal_output console serial

set default="0"
set timeout="5"

search -l kernel -s root

menuentry "OpenWrt" {
	linux /boot/vmlinuz root=PARTUUID=<your-partuuid> rootwait  console=tty1 console=ttyS0,115200n8 noinitrd
}
menuentry "OpenWrt (failsafe)" {
	linux /boot/vmlinuz failsafe=true root=PARTUUID=<your-partuuid> rootwait  console=tty1 console=ttyS0,115200n8 noinitrd
}
GRUB

# Clean up any failed init scripts on the rootfs
sudo mount /dev/nbd0p2 /mnt/rootfix
sudo rm -f /mnt/rootfix/sbin/resize-rootfs  # Remove one-shot fail scripts

sudo umount /mnt/bootfix
sudo umount /mnt/rootfix
sudo qemu-nbd -d /dev/nbd0
```

### 3b. Get the PARTUUID

```bash
sudo blkid /dev/nbd0p2
# Example: /dev/nbd0p2: UUID="..." BLOCK_SIZE="4096" TYPE="ext4" PARTUUID="11458228-0839-40e2-fe5c-7d7fc0445102"
```

## Pitfalls

- **VHDX snapshots (AVHDX):** If the disk shows as `.avhdx`, remove the Hyper-V snapshot first, or the expansion applies to the wrong layer.
- **FAT16 on Windows:** The boot partition (FAT16) on OpenWrt x86_64 is marked as a system partition (type 'Unknown' on Windows). Windows won't assign it a drive letter. Always use `qemu-nbd` on Linux to modify it.
- **Gen1 VM GRUB:** Gen1 VMs use BIOS+GRUB (not UEFI). GRUB config at `/boot/grub/grub.cfg`. Gen2 VMs use UEFI+GRUB with a different path.
- **`noinitrd` in cmdline:** OpenWrt x86_64 boots directly from the ext4 partition, no initramfs. Kernel parameters are in GRUB config, not a bootloader command line.
- **Dynamic VHDX vs fixed:** Hyper-V's default is dynamically expanding VHDX. The `Resize-VHD` changes the maximum size; the file on disk only grows as data is written.
- **SCP from Windows:** Use `scp user@host:/C:/path` or `scp user@host:/cygdrive/c/path` (depending on SSH server — OpenSSH for Windows uses `/C:/path`).
