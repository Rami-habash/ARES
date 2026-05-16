#!/bin/bash
# ARES VM Setup Script
# Run once on a fresh Ubuntu 22.04+ VM.
# Usage: NVIDIA_API_KEY=nvapi-... bash setup_vm.sh
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}[setup]${NC} $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $1"; }
die()   { echo -e "${RED}[error]${NC} $1"; exit 1; }
step()  { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

SANDBOX_NAME="${SANDBOX_NAME:-nemo-ares}"
MODEL="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Preflight ─────────────────────────────────────────────────────────────────
step "Preflight"
[[ -z "$NVIDIA_API_KEY" ]] && die "NVIDIA_API_KEY not set. Run: export NVIDIA_API_KEY=nvapi-..."
[[ "$EUID" -eq 0 ]]        && die "Do not run as root."
info "API key present. Sandbox name: $SANDBOX_NAME"

# ── System dependencies ───────────────────────────────────────────────────────
step "System dependencies"
sudo apt-get update -qq
sudo apt-get install -y -qq \
    curl git ca-certificates gnupg lsb-release \
    libgl1 libglib2.0-0 libgles2 libegl1 \
    libsm6 libxext6 libxrender-dev

# ── Docker ────────────────────────────────────────────────────────────────────
step "Docker"
if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo bash
    sudo usermod -aG docker "$USER"
    newgrp docker || true
else
    info "Docker already installed: $(docker --version)"
fi

# Fix DNS for filtered networks (eduroam etc.)
DAEMON_JSON="/etc/docker/daemon.json"
if ! sudo grep -q "8.8.8.8" "$DAEMON_JSON" 2>/dev/null; then
    info "Configuring Docker DNS..."
    sudo mkdir -p /etc/docker
    echo '{"dns":["8.8.8.8","1.1.1.1"]}' | sudo tee "$DAEMON_JSON" > /dev/null
    sudo systemctl restart docker
    sleep 3
fi

# ── Node.js 22 ────────────────────────────────────────────────────────────────
step "Node.js"
NODE_VER=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1 || echo 0)
if [[ "$NODE_VER" -lt 22 ]]; then
    info "Installing Node.js 22..."
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
else
    info "Node.js already installed: $(node --version)"
fi

# ── Python dependencies ───────────────────────────────────────────────────────
step "Python dependencies (CV)"
pip3 install --quiet \
    torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip3 install --quiet -r "$SCRIPT_DIR/CV/requirements.txt" 2>/dev/null || \
pip3 install --quiet \
    opencv-python ultralytics mediapipe lap onnxruntime \
    numpy scipy openai fastapi uvicorn aiortc websockets httpx kagglehub

step "Python dependencies (backend)"
pip3 install --quiet -r "$SCRIPT_DIR/backend/requirements.txt" 2>/dev/null || \
pip3 install --quiet fastapi uvicorn sqlalchemy websockets httpx python-jose passlib

# ── Frontend dependencies ─────────────────────────────────────────────────────
step "Frontend dependencies"
cd "$SCRIPT_DIR/frontend" && npm install --silent
cd "$SCRIPT_DIR"

# ── NemoClaw ──────────────────────────────────────────────────────────────────
step "NemoClaw"
if ! command -v nemoclaw &>/dev/null; then
    info "Installing NemoClaw..."
    curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
else
    info "NemoClaw already installed: $(nemoclaw --version 2>/dev/null | head -1)"
fi

# ── Sandbox onboard ───────────────────────────────────────────────────────────
step "NemoClaw sandbox"
if nemoclaw list 2>/dev/null | grep -q "$SANDBOX_NAME"; then
    info "Sandbox '$SANDBOX_NAME' already exists, skipping onboard."
else
    info "Onboarding sandbox '$SANDBOX_NAME'..."
    info "When prompted: select 'nvidia-prod' as provider and pick:"
    info "  $MODEL"
    echo ""
    NVIDIA_API_KEY="$NVIDIA_API_KEY" nemoclaw onboard --name "$SANDBOX_NAME" \
        --yes-i-accept-third-party-software
fi

# ── Workspace files ───────────────────────────────────────────────────────────
step "Pushing workspace files to sandbox"
push_workspace_file() {
    local file="$1" dest="$2"
    if [[ -f "$SCRIPT_DIR/claw/$file" ]]; then
        openshell -g nemoclaw sandbox exec -n "$SANDBOX_NAME" -- \
            sh -c "cat > /sandbox/.openclaw/workspace/$dest" \
            < "$SCRIPT_DIR/claw/$file"
        info "  ✓ $file"
    else
        warn "  $file not found, skipping"
    fi
}

push_workspace_file AGENTS.md AGENTS.md
push_workspace_file SOUL.md   SOUL.md
push_workspace_file TOOLS.md  TOOLS.md

# ── Skills ────────────────────────────────────────────────────────────────────
step "Installing skills"
SKILLS_DIR="$SCRIPT_DIR/claw/skills"
if [[ -d "$SKILLS_DIR" ]]; then
    for skill_dir in "$SKILLS_DIR"/*/; do
        skill_name=$(basename "$skill_dir")
        if [[ -f "$skill_dir/SKILL.md" ]]; then
            nemoclaw "$SANDBOX_NAME" skill install "$skill_dir"
            info "  ✓ $skill_name"
        fi
    done
else
    warn "No skills/ directory found"
fi

# ── Seed patient DB ───────────────────────────────────────────────────────────
step "Seeding patient database"
cd "$SCRIPT_DIR/claw"
python3 -c "from patient_profile.profile import seed_db; seed_db(); print('DB seeded')"
cd "$SCRIPT_DIR"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✓ Setup complete!${NC}"
echo ""
echo "  Sandbox:   $SANDBOX_NAME"
echo "  Model:     $MODEL"
echo ""
echo "  Start services:"
echo "    Terminal 1 — Backend:  cd backend  && uvicorn app.main:app --port 8000"
echo "    Terminal 2 — CV:       cd CV       && uvicorn api:app --host 0.0.0.0 --port 8001"
echo "    Terminal 3 — Frontend: cd frontend && npm run dev"
echo "    Terminal 4 — Daemon:   cd claw     && python3 form_monitor_daemon.py --patient P001 --source 0"
echo ""
echo "  Connect to agent: nemoclaw $SANDBOX_NAME connect && openclaw tui"
echo ""