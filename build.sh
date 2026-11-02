#!/bin/sh
# Native Linux entry point; quote every argument so ISO paths may contain spaces.
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 -I -u "$root/tools/pipeline/linux.py" "$@"
