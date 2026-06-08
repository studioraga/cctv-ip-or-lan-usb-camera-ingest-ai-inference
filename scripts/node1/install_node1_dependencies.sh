#!/usr/bin/env bash
set -euo pipefail
sudo apt update
sudo apt install -y \
  python3-full python3-venv python3-pip python3-opencv python3-numpy \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-libav \
  build-essential cmake pkg-config libopencv-dev \
  ufw iproute2 net-tools htop
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-node1.txt
