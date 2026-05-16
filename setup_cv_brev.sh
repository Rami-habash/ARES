#!/bin/bash
# CV-only setup for Brev (GPU instance).
# Run once after cloning the repo on a fresh Brev Ubuntu 22.04+ instance.
# Usage: bash setup_cv_brev.sh
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${GREEN}[setup]${NC} $1"; }
warn() { echo -e "${YELLOW}[warn]${NC}  $1"; }
step() { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CV_DIR="$SCRIPT_DIR/CV"

# ── System dependencies ───────────────────────────────────────────────────────
step "System dependencies"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    libgl1 libglib2.0-0 libgles2 libegl1 \
    libsm6 libxext6 libxrender-dev \
    curl git

# ── CUDA PyTorch ──────────────────────────────────────────────────────────────
step "PyTorch (CUDA)"
if python3 -c "import torch; assert torch.cuda.is_available()" 2>/dev/null; then
    info "PyTorch CUDA already available: $(python3 -c 'import torch; print(torch.__version__)')"
else
    info "Installing PyTorch with CUDA 12.1..."
    pip3 install --quiet torch torchvision \
        --index-url https://download.pytorch.org/whl/cu121
fi

# ── CV Python dependencies ────────────────────────────────────────────────────
step "CV Python dependencies"
pip3 install --quiet -r "$CV_DIR/requirements.txt"

# ── Model files check ─────────────────────────────────────────────────────────
step "Model files"
if [[ -f "$CV_DIR/yolo11l.pt" ]]; then
    info "yolo11l.pt present"
else
    warn "yolo11l.pt not found — ultralytics will auto-download on first run"
fi
if [[ -f "$CV_DIR/pose_landmarker_full.task" ]]; then
    info "pose_landmarker_full.task present"
else
    warn "pose_landmarker_full.task not found — downloading..."
    curl -L -o "$CV_DIR/pose_landmarker_full.task" \
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/latest/pose_landmarker_full.task"
fi

# ── ngrok ─────────────────────────────────────────────────────────────────────
step "ngrok"
if ! command -v ngrok &>/dev/null; then
    info "Installing ngrok..."
    curl -sSL https://ngrok-agent.s3.amazonaws.com/ngrok.asc \
        | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
    echo "deb https://ngrok-agent.s3.amazonaws.com buster main" \
        | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null
    sudo apt-get update -qq && sudo apt-get install -y -qq ngrok
else
    info "ngrok already installed: $(ngrok --version)"
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✓ CV setup complete!${NC}"
echo ""
echo "  Next steps:"
echo "  1. Set your ngrok authtoken:"
echo "       ngrok config add-authtoken <YOUR_TOKEN>"
echo ""
echo "  2. Start the CV server:"
echo "       cd CV && uvicorn api:app --host 0.0.0.0 --port 8001"
echo ""
echo "  3. In another terminal, start ngrok (use your static domain):"
echo "       ngrok http 8001 --domain solstice.ngrok.dev"
echo ""
echo "  4. Update frontend/.env.local on your local machine:"
echo "       NEXT_PUBLIC_CV_BASE=https://solstice.ngrok.dev"
echo ""
echo "  The laptop's detail camera WebRTC will still go to localhost:8001."
echo "  Point NEXT_PUBLIC_CV_LOCAL at the Brev ngrok URL if using Brev for detail too."
echo ""
