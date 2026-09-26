#!/usr/bin/env bash
# One-time preparation of a fresh Ubuntu VM (1 GB micro instance). Run it ON the
# server:  ssh ubuntu@<ip> 'bash -s' < deploy/server-setup.sh
# Then log out and back in once so the docker group applies.
set -euo pipefail

# 1 GB of RAM holds the stack (~410 MB measured) but not image loads and
# Postgres start-up on top of the OS. Swap is the cushion.
if ! swapon --show | grep -q /swapfile; then
	sudo fallocate -l 4G /swapfile
	sudo chmod 600 /swapfile
	sudo mkswap /swapfile
	sudo swapon /swapfile
	echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

if ! command -v docker >/dev/null; then
	curl -fsSL https://get.docker.com | sudo sh
fi
sudo usermod -aG docker "$USER"

# Oracle's Ubuntu images ship iptables rules that REJECT everything except SSH,
# so opening 80/443 in the VCN security list alone is not enough.
if sudo iptables -L INPUT -n | grep -q "REJECT"; then
	sudo iptables -I INPUT -p tcp -m state --state NEW -m multiport --dports 80,443 -j ACCEPT
	sudo iptables -I INPUT -p udp --dport 443 -j ACCEPT
	if command -v netfilter-persistent >/dev/null; then
		sudo netfilter-persistent save
	fi
fi

mkdir -p ~/dhruva
echo "ready: $(nproc) cpu, $(free -h | awk '/Mem/{print $2}') ram, $(df -h ~ | awk 'NR==2{print $4}') disk free"
