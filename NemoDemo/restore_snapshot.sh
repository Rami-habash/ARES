#!/bin/bash
# Restore the nemo-ares sandbox to the Solstice workspace snapshot.
set -euo pipefail

SANDBOX="nemo-ares"
SNAPSHOT="with-solstice-workspace"

echo "Restoring $SANDBOX from snapshot '$SNAPSHOT'..."
nemoclaw "$SANDBOX" snapshot restore "$SNAPSHOT"
echo "Done. Agent is ready."
