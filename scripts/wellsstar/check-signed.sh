#!/bin/bash
# Fail if any Mach-O file inside the bundle lacks a valid signature. `codesign --verify --deep`
# does not catch loose dylibs such as Xcode's <App>.debug.dylib / __preview.dylib, which dyld
# then refuses at launch ("Library missing ... missing code signature"; 2026-11-20 crash).
#   scripts/wellsstar/check-signed.sh <path/to/App.app>
set -uo pipefail
bad=0
while IFS= read -r -d '' f; do
    file -b "$f" | grep -q 'Mach-O' || continue
    if ! codesign --verify --strict "$f" >/dev/null 2>&1; then echo "UNSIGNED: $f"; bad=1; fi
done < <(find "$1" -type f -print0)
[ $bad = 0 ] && echo "all Mach-O signed: $1"
exit $bad
