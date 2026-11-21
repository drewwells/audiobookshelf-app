#!/bin/sh
# One-time (re-runnable) signing setup through the App Store Connect API: register the fork's
# bundle ids and make IOS_APP_STORE profiles for them with the Apple Distribution certificate
# 6PABTH8924 (identity in deej-signing.keychain-db). Profiles go to ~/.config/abs-signing/.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
set -a; . "$HOME/.config/dance-practice/deploy.env"; set +a
out="$HOME/.config/abs-signing"
mkdir -p "$out"; chmod 700 "$out"
cert=6PABTH8924
"$here/asc.py" bundle-id dev.wellsstar.abs "ABS Fork"
"$here/asc.py" bundle-id dev.wellsstar.abs.watchkitapp "ABS Fork Watch"
"$here/asc.py" profile "abs App Store" IOS_APP_STORE dev.wellsstar.abs $cert "$out/abs-appstore.mobileprovision"
"$here/asc.py" profile "abs watch App Store" IOS_APP_STORE dev.wellsstar.abs.watchkitapp $cert \
    "$out/abs-watch-appstore.mobileprovision"
