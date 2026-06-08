cd ~/dev/11.node1_cam_reciver

sudo apt update
sudo apt install -y python3-full python3-venv python3-pip \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav

sudo apt install -y \
  python3-opencv \
  python3-numpy \
  gstreamer1.0-tools \
  gstreamer1.0-plugins-base \
  gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad \
  gstreamer1.0-plugins-ugly \
  gstreamer1.0-libav

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install opencv-python numpy
