#!/bin/bash
# Restore the nemo sandbox to the Solstice workspace snapshot.
set -euo pipefail

SANDBOX="nemo"
SNAPSHOT="with-solstice-workspace-v4"

echo "Restoring $SANDBOX from snapshot '$SNAPSHOT'..."
nemoclaw "$SANDBOX" snapshot restore "$SNAPSHOT"
echo "Done. Agent is ready."
