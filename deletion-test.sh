#!/usr/bin/env bash
# The deletion gate, as a script a judge runs.
#
# Sibyl scores an entry by DELETING the memory layer and checking whether the
# product still works. If it does, the memory was decoration and the entry is
# disqualified. This applies that test to ourselves and prints the with/without
# answer so the difference is visible, not asserted. WITH memory = the field's
# warranted belief (the evidenced subset). WITHOUT = the naive vote, which needs
# no store. If they match, the design failed its own gate.
#
#   ./deletion-test.sh [NIGHT]           ingest the frozen field, then compare
#   QUORUM_PY=~/.sibyl-venv/bin/python ./deletion-test.sh   # use the venv client
set -euo pipefail
cd "$(dirname "$0")"
PY="${QUORUM_PY:-python3}"
NIGHT="${1:-2026-08-27}"
STORE="$(mktemp -d)/quorum.db"; export QUORUM_STORE="$STORE"
trap 'rm -rf "$(dirname "$STORE")"' EXIT
echo "▸ ingesting the frozen field into a scratch store ($STORE) …"
"$PY" -m quorum ingest --from tests/fixtures/rows.json >/dev/null
"$PY" -m quorum._gate "$NIGHT"
