# VHDX Disk Expansion + Boot Recovery (Hyper-V)

## When to Use

OpenWrt VM root partition is full (~100MB) and you need to expand it, or the VM is stuck in a boot loop after a failed init script modification.

## Environment

- Hyper-V on Windows host
- Gen1 VM, GRUB bootloader
- ext4 root filesystem (not squashfs)
- VHDX differencing disk (snapshots) or plain VHDX

## Step 1: Expand the VHDX

### On the Hyper-V Host (Windows):

```powershell
# If there's a snapshot, merge it first
Get-VM -VMName "vm-name" | Get-VMSnapshot | Remove-VMSnapshot

# Shut down the VM
Stop-VM -VMName "vm-name" -Force

# Resize the VHDX
Resize-VHD -Path "C:\hyper-v-vm\disk.vhdx" -SizeBytes 1GB

# Start the VM
Start-VM -VMName "vm-name"
```

> Note: The VHDX file size on disk stays small (dynamically expanding) — `Resize-VHD` changes the max capacity.

### Inside OpenWrt (if VM is bootable):

```bash
# Install tools
opkg update && opkg install parted resize2fs

# Check current layout
parted /dev/sda unit MiB print free

# Fix GPT (if warning about unused space)
printf "fix\n" | parted /dev/sda unit MiB print free

# Resize partition 2 to fill all free space
printf "1023MiB\n" | parted /dev/sda resizepart 2

# Resize filesystem
resize2fs /dev/sda2

# Verify
df -h /
```

## Step 2: Recover from Boot Loop

### Symptom

VM keeps restarting with <10s uptime (kernel panic or GRUB loop).

### Fix via Local Linux Mount (when VM won't boot)

1. **Copy the VHDX to a Linux machine:**

```bash
# On the Hyper-V host, detach first
Dismount-VHD -Path "C:\hyper-v-vm\disk.vhdx"

# SCP to Linux host
scp user@windows-host:/C:/hyper-v-vm/disk.vhdx /tmp/fix.vhdx
```

2. **Mount via NBD on Linux:**

```bash
sudo modprobe nbd max_part=8
sudo qemu-nbd -c /dev/nbd0 /tmp/fix.vhdx
lsblk /dev/nbd0
```

3. **Mount and fix boot partition (FAT16):**

```bash
sudo mkdir -p /mnt/bootfix
sudo mount /dev/nbd0p1 /mnt/bootfix
# Fix grub.cfg
sudo tee /mnt/bootfix/boot/grub/grub.cfg > /dev/null << 'EOF'
serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1 --rtscts=off
terminal_input console serial; terminal_output console serial
set default="0"
set timeout="5"
search -l kernel -s root
menuentry "OpenWrt" {
	linux /boot/vmlinuz root=PARTUUID=<UUID> rootwait console=tty1 console=ttyS0,115200n8 noinitrd
}
menuentry "OpenWrt (failsafe)" {
	linux /boot/vmlinuz failsafe=true root=PARTUUID=<UUID> rootwait console=tty1 console=ttyS0,115200n8 noinitrd
}
EOF
```

4. **Offline resize root partition (ext4):**

```bash
sudo umount /mnt/bootfix
sudo e2fsck -fy /dev/nbd0p2
sudo resize2fs /dev/nbd0p2
sudo dumpe2fs -h /dev/nbd0p2 | grep -E 'Block count:|Block size:'
```

5. **Copy back and restart:**

```bash
sudo qemu-nbd -d /dev/nbd0
scp /tmp/fix.vhdx user@windows-host:/C:/hyper-v-vm/disk.vhdx
```

On Hyper-V host:
```powershell
Start-VM -VMName "vm-name"
```

## Step 3: GRUB Init Script One-Shot Method (alternative)

If you want to resize without taking the VHDX offline:

1. Create a resize script on the rootfs:

```bash
# On the VM (before reboot)
cat > /sbin/resize-rootfs << 'ENDSCRIPT'
#!/bin/sh
exec 2>/dev/console
echo "Resizing..."
mount /dev/sda1 /boot 2>/dev/null
/sbin/resize2fs -f /dev/sda2
# Restore original GRUB
cat > /boot/grub/grub.cfg << "GRUB"
... (original grub.cfg content) ...
GRUB
rm -f /sbin/resize-rootfs
echo "Done, booting normally"
exec /sbin/init
ENDSCRIPT
chmod +x /sbin/resize-rootfs
```

2. Add a GRUB entry with `init=/sbin/resize-rootfs` and set it as default entry.

3. Reboot. After the script runs, it restores GRUB and boots normally.

> **Caveat:** If `resize2fs` fails or the filesystem has `resize_inode` / `flex_bg` features that the kernel's online resize doesn't support, this method causes a boot loop. Prefer the offline method (Step 2) when possible.
