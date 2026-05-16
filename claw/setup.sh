#!/bin/bash
set -e

# NemoDemo VM Setup Script
# Run this once on a fresh Ubuntu 22.04+ VM as a non-root user with sudo access.
# Usage: NVIDIA_API_KEY=nvapi-... bash setup.sh

# ── Config ────────────────────────────────────────────────────────────────────
SANDBOX_NAME="nemo-demo"
MODEL="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
PROVIDER="nvidia"
# ─────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${GREEN}[setup]${NC} $1"; }
warn()    { echo -e "${YELLOW}[warn]${NC}  $1"; }
die()     { echo -e "${RED}[error]${NC} $1"; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────
[[ -z "$NVIDIA_API_KEY" ]] && die "NVIDIA_API_KEY is not set. Run: export NVIDIA_API_KEY=nvapi-..."
[[ "$EUID" -eq 0 ]]       && die "Do not run as root. Run as a normal user with sudo access."

info "Starting NemoDemo setup on $(hostname)"

# ── 1. System dependencies ────────────────────────────────────────────────────
info "Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq curl git ca-certificates gnupg lsb-release

# ── 2. Docker ─────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  info "Installing Docker..."
  curl -fsSL https://get.docker.com | sudo bash
  sudo usermod -aG docker "$USER"
  warn "Docker installed. You may need to log out and back in for group changes to take effect."
  warn "If docker commands fail, run: newgrp docker"
  newgrp docker || true
else
  info "Docker already installed: $(docker --version)"
fi

# ── 3. Node.js 22 ─────────────────────────────────────────────────────────────
NODE_VERSION=$(node --version 2>/dev/null | sed 's/v//' | cut -d. -f1)
if [[ -z "$NODE_VERSION" ]] || [[ "$NODE_VERSION" -lt 22 ]]; then
  info "Installing Node.js 22..."
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt-get install -y -qq nodejs
else
  info "Node.js already installed: $(node --version)"
fi

# ── 4. NemoClaw ───────────────────────────────────────────────────────────────
if ! command -v nemoclaw &>/dev/null; then
  info "Installing NemoClaw..."
  curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
  export PATH="$HOME/.local/bin:$PATH"
else
  info "NemoClaw already installed: $(nemoclaw --version 2>/dev/null | head -1)"
fi

# ── 5. Docker DNS (fix for eduroam/filtered networks) ────────────────────────
DAEMON_JSON="/etc/docker/daemon.json"
if ! sudo grep -q "8.8.8.8" "$DAEMON_JSON" 2>/dev/null; then
  info "Configuring Docker DNS..."
  sudo mkdir -p /etc/docker
  echo '{"dns":["8.8.8.8","1.1.1.1"]}' | sudo tee "$DAEMON_JSON" > /dev/null
  sudo systemctl restart docker
  sleep 3
fi

# ── 6. Onboard NemoClaw sandbox ───────────────────────────────────────────────
if nemoclaw list 2>/dev/null | grep -q "$SANDBOX_NAME"; then
  info "Sandbox '$SANDBOX_NAME' already exists, skipping onboard."
else
  info "Onboarding NemoClaw sandbox '$SANDBOX_NAME' (this takes 5-15 min)..."
  NEMOCLAW_NON_INTERACTIVE=1 \
  NEMOCLAW_YES=1 \
  NEMOCLAW_PROVIDER=nvidia-prod \
  nemoclaw onboard --name "$SANDBOX_NAME"
fi

# ── 7. Install skills ─────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR/skills"

if [[ -d "$SKILLS_DIR" ]]; then
  info "Installing skills from $SKILLS_DIR..."
  for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    if [[ -f "$skill_dir/SKILL.md" ]]; then
      nemoclaw "$SANDBOX_NAME" skill install "$skill_dir"
      info "  ✓ installed skill: $skill_name"
    fi
  done
else
  warn "No skills/ directory found, skipping skill install."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}✓ Setup complete!${NC}"
echo ""
echo "  Sandbox:   $SANDBOX_NAME"
echo "  Model:     $MODEL"
echo ""
echo "  Connect:   nemoclaw $SANDBOX_NAME connect"
echo "  Status:    nemoclaw $SANDBOX_NAME status"
echo "  Chat UI:   openclaw tui  (run inside the sandbox)"
echo ""
echo "  Dashboard: http://localhost:18789"
echo "  Token:     nemoclaw $SANDBOX_NAME gateway-token --quiet"
echo ""
