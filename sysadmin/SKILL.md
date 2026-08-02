---
name: sysadmin
description: Linux system administration for Debian 13. Trigger for service management, systemd, SSH, firewall, logs, cron, disk/RAM/CPU monitoring, backups, and any OS-level configuration task.
---

# Sysadmin — Debian 13 Trixie

## System Identity

```
OS:      Debian 13 Trixie
Kernel:  Linux (check: uname -r)
User:    olekamole
Host:    debianminipc
Python:  3.11.x via pyenv (AI/ML), 3.13 system default
```

---

## Service Management (systemd)

```bash
# Status / start / stop / restart
systemctl status <service>
systemctl start <service>
systemctl stop <service>
systemctl restart <service>
systemctl enable <service>   # start on boot
systemctl disable <service>

# View logs for a service
journalctl -u <service> -f          # follow live
journalctl -u <service> --since "1h ago"
journalctl -u <service> -n 100      # last 100 lines

# Create a new service
nano /etc/systemd/system/myapp.service
systemctl daemon-reload
systemctl enable myapp
```

### Service template for Python scripts
```ini
[Unit]
Description=My Python App
After=network.target

[Service]
Type=simple
User=olekamole
WorkingDirectory=/home/olekamole/yolo-vision
ExecStart=/home/olekamole/.pyenv/shims/python person_tracker8.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## Monitoring

```bash
# CPU / RAM
htop
free -h
vmstat 1 5

# Disk
df -h
du -sh /home/olekamole/*
lsblk

# Network
ip a
ss -tulpn          # listening ports
iftop              # live bandwidth (install if missing)
ping 192.168.1.175 # check Frigate NVR

# GPU (Intel Iris Xe) — PMU errors are cosmetic noise, ignore them
intel_gpu_top      # install: apt install intel-gpu-tools
vainfo             # check VAAPI

# Temperature
sensors            # install: apt install lm-sensors && sensors-detect
```

---

## Logs

```bash
# System logs
journalctl -xe                    # recent errors with context
journalctl --since today
journalctl -p err -b              # errors since last boot

# App logs
tail -f /home/olekamole/yolo-vision/face_pipeline.log
grep "ERROR\|WARN" /var/log/syslog

# Docker logs (Frigate, etc.)
docker logs frigate -f --tail=100
```

---

## Networking

```bash
# Check connectivity
ping 192.168.1.175     # Frigate NVR
ping 192.168.1.249     # Hikvision camera

# Open ports
ufw status
ufw allow 8080/tcp
ufw deny 23/tcp

# Firewall (Debian uses ufw or nftables)
ufw enable
ufw status verbose

# Static IP (edit /etc/network/interfaces or netplan)
ip route show
```

---

## Cron Jobs

```bash
crontab -e          # edit current user's cron
crontab -l          # list

# Examples
0 3 * * * /home/olekamole/scripts/backup.sh        # daily 3am backup
*/5 * * * * /home/olekamole/scripts/healthcheck.sh # every 5 min
@reboot python3 /home/olekamole/yolo-vision/person_tracker8.py
```

---

## Backups

```bash
# rsync local backup
rsync -avz --delete /home/olekamole/yolo-vision/ /mnt/backup/yolo-vision/

# Backup model + config only (exclude large video/face crops)
rsync -avz \
  --exclude='known_faces/' \
  --exclude='*.avi' --exclude='*.mp4' \
  /home/olekamole/yolo-vision/ \
  /mnt/backup/yolo-vision/

# Cron-based daily backup
0 2 * * * rsync -az /home/olekamole/projects/ /mnt/backup/projects/
```

---

## SSH Hardening

```bash
# /etc/ssh/sshd_config — key settings
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
AllowUsers olekamole
Port 22   # consider changing to non-standard

systemctl restart sshd

# Add public key
mkdir -p ~/.ssh && chmod 700 ~/.ssh
echo "ssh-rsa AAAA..." >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

---

## Package Management

```bash
apt update && apt upgrade -y
apt install <package>
apt autoremove

# For Python packages (avoid breaking system Python 3.13)
pip install <package> --break-system-packages   # system pip only if needed
# Preferred: use pyenv + venv
source ~/yolo-vision/venv/bin/activate
pip install <package>
```

---

## Known Issues on This Machine

| Issue | Status | Fix |
|-------|--------|-----|
| `Unable to poll intel GPU stats` (PMU error) | Cosmetic noise | Ignore |
| Python 3.13 breaks PyTorch/OpenVINO | Known | Use pyenv 3.11 |
| RTSP stream drops every 1-2h | Fixed | `preset-rtsp-restream` in Frigate config |
