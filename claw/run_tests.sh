#!/bin/bash
#
# Regression tests for exercise_identifier.identify_exercise.
#
# Run from NemoDemo/:
#   bash run_tests.sh
#
# Requires:
#   - install.sh has been run (CV + LLM dependencies installed)
#   - NemoDemo/data/videos/ populated with reference videos
#   - NVIDIA_API_KEY exported for the OOD test
#
set -u

cd "$(dirname "$0")"

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; NC='\033[0m'
pass() { echo -e "${GREEN}PASS${NC}  $1"; }
fail() { echo -e "${RED}FAIL${NC}  $1"; }
info() { echo -e "${YELLOW}TEST${NC}  $1"; }

# ── Test 1: in-domain ─────────────────────────────────────────────────────────
# squat is in P001's prescribed list.  The in-domain pass should match it
# directly without entering the OOD reasoning loop.
info "1/2 — In-domain: P001 (Alice) doing squat → expect 'squat'"
out=$(python3 test_identifier.py \
    --patient P001 \
    --video "data/videos/squat/squat_10.mp4" 2>&1)
echo "$out"
if echo "$out" | grep -q "^Result  : squat$"; then
    pass "in-domain squat match"
else
    fail "expected 'squat' result"
fi
echo

# ── Test 2: out-of-domain ─────────────────────────────────────────────────────
# lat pulldown is NOT in P001's prescription but IS in the reference library
# (prescribed for P002/P004).  The in-domain pass will miss; Nemotron should
# reason its way to suggesting 'lat pulldown' as an OOD candidate.
info "2/2 — OOD: P001 (Alice) doing lat pulldown → expect 'lat pulldown'"
out=$(python3 test_identifier.py \
    --patient P001 \
    --video "data/videos/lat pulldown/lat pulldown_1.mp4" 2>&1)
echo "$out"
if echo "$out" | grep -q "^Result  : lat pulldown$"; then
    pass "OOD lat pulldown match via Nemotron reasoning"
else
    fail "expected 'lat pulldown' result"
fi
