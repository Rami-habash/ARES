#!/bin/bash
set -e

# System libraries required by opencv, mediapipe, and opengl
sudo apt-get update -qq
sudo apt-get install -y -qq libgl1 libglib2.0-0 libgles2 libegl1

# PyTorch CPU build
pip3 install --quiet \
    torch==2.12.0+cpu \
    torchvision==0.27.0+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Everything else
pip3 install --quiet \
    opencv-python==4.13.0.92 \
    ultralytics==8.4.51 \
    mediapipe==0.10.35 \
    lap==0.5.13 \
    insightface==0.7.3 \
    onnxruntime==1.23.2 \
    numpy==2.2.6 \
    scipy==1.15.3 \
    openai==2.37.0 \
    fastapi \
    uvicorn \
    kagglehub==1.0.1

echo ""
echo "Precomputing reference video embeddings..."
cd NemoDemo && python3 precompute_embeddings.py
cd ..

echo "Done."
