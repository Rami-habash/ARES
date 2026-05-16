#!/bin/bash
set -e

# System libraries required by opencv, mediapipe, opengl, and audio
sudo apt-get update -qq
sudo apt-get install -y -qq \
    libgl1 libglib2.0-0 libgles2 libegl1 \
    libsrtp2-dev libopus-dev libvpx-dev

# Node.js (frontend)
if ! command -v node &>/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
fi

# PyTorch CPU build
pip3 install --quiet \
    torch==2.12.0+cpu \
    torchvision==0.27.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# CV + backend Python deps
pip3 install --quiet \
    opencv-contrib-python==4.13.0.92 \
    ultralytics==8.4.51 \
    mediapipe==0.10.35 \
    lap==0.5.13 \
    insightface==0.7.3 \
    onnxruntime==1.23.2 \
    numpy==2.2.6 \
    scipy==1.15.3 \
    openai==2.37.0 \
    fastapi \
    uvicorn[standard] \
    aiortc==1.14.0 \
    httpx==0.28.1 \
    websockets==15.0.1 \
    python-jose[cryptography]==3.5.0 \
    python-dotenv==1.2.2 \
    bcrypt==5.0.0 \
    python-multipart==0.0.28 \
    kagglehub==1.0.1

# Frontend deps
cd frontend && npm install --silent
cd ..

echo ""
echo "Precomputing reference video embeddings..."
cd claw && python3 -c "
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('..') / 'CV'))
from exercise_identifier import _s3d, _sample_reference_videos, _embed, VIDEO_ROOT
import os
for ex_dir in sorted(VIDEO_ROOT.iterdir()):
    if not ex_dir.is_dir(): continue
    vids = _sample_reference_videos(ex_dir.name)
    for v in vids:
        _embed(v)
        print(f'  cached {v.name}')
print('Embeddings ready.')
"
cd claw && python3 precompute_embeddings.py
cd ..

echo "Done."
