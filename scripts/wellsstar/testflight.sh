#!/bin/sh
# Archive the fork (and its embedded watch app, when there is one), sign it by hand from the
# deej-signing keychain (headless on beast: no Xcode account, the login keychain is locked), upload
# it and give it to the TestFlight internal group "abs internal". Recipe from drewwells' deej
# (ios/app/scripts/testflight.sh). See WELLSSTAR.md.
#   testflight.sh              web bundle + archive + sign + upload + wait + group
#   testflight.sh --no-web     skip nuxt generate / cap copy (ios/App/App/public already current)
#   testflight.sh --no-upload  stop after the .ipa
# Build number: the git commit count, bumped past any build already on App Store Connect.
set -eu
here=$(cd "$(dirname "$0")/../.." && pwd)
ios=$here/ios/App
out=$ios/build/tf
kc="$HOME/Library/Keychains/deej-signing.keychain-db"
cfg="$HOME/.config/abs-signing"
prof="$cfg/abs-appstore.mobileprovision"
watch_prof="$cfg/abs-watch-appstore.mobileprovision"
identity=623D59B50C6E5690C07BD89F88B3D092DBBC9002  # Apple Distribution 6PABTH8924 (deej-signing keychain)
team=8943DPB6NM
bundle=dev.wellsstar.abs
web=1 upload=1
while [ $# -gt 0 ]; do
    case $1 in
        --no-web) web=0 ;;
        --no-upload) upload=0 ;;
        *) echo "unknown option $1" >&2; exit 2 ;;
    esac
    shift
done
set -a; . "$HOME/.config/dance-practice/deploy.env"; set +a
asc="$here/scripts/wellsstar/asc.py"
build=$(git -C "$here" rev-list --count HEAD)
[ $upload = 0 ] || build=$("$asc" next-build $bundle "$build")
if [ $web = 1 ]; then
    (cd "$here" && npm run generate && npx cap copy ios)
fi
mkdir -p "$out"
[ ! -e "$out/App.xcarchive" ] || mv "$out/App.xcarchive" "$out/App.xcarchive.old.$$"
[ ! -e "$out/ipa" ] || mv "$out/ipa" "$out/ipa.old.$$"
# Xcode 27 builds iOS 15 at the least; the pods ask for 14.
xcodebuild -workspace "$ios/App.xcworkspace" -scheme App -configuration Release \
    -destination generic/platform=iOS -derivedDataPath "$out/dd" -archivePath "$out/App.xcarchive" \
    CODE_SIGNING_ALLOWED=NO IPHONEOS_DEPLOYMENT_TARGET=15.0 CURRENT_PROJECT_VERSION="$build" archive -quiet
mkdir -p "$out/ipa/Payload"
cp -R "$out/App.xcarchive/Products/Applications/Audiobookshelf.app" "$out/ipa/Payload/"
app=$out/ipa/Payload/Audiobookshelf.app
watch=$app/Watch/ABSWatch.app
cp "$prof" "$app/embedded.mobileprovision"
ent() {  # profile entitlements -> plist, keychain group narrowed to the app's own id
    security cms -D -i "$1" | plutil -extract Entitlements xml1 -o "$2" -
    plutil -replace keychain-access-groups -json "[\"$team.$3\"]" "$2"
}
ent "$prof" "$out/ent-app.plist" $bundle
# Never `set -x` here: the next line expands the keychain password.
security unlock-keychain -p "$(cat "$HOME/.config/deej-signing/keychain.pass")" "$kc"
# Inside out: frameworks, the watch app, then the phone app.
for f in "$app"/Frameworks/*; do
    [ -e "$f" ] && codesign --force --sign "$identity" --keychain "$kc" "$f"
done
if [ -d "$watch" ]; then
    cp "$watch_prof" "$watch/embedded.mobileprovision"
    ent "$watch_prof" "$out/ent-watch.plist" $bundle.watchkitapp
    for f in "$watch"/Frameworks/*; do
        [ -e "$f" ] && codesign --force --sign "$identity" --keychain "$kc" "$f"
    done
    codesign --force --sign "$identity" --keychain "$kc" --entitlements "$out/ent-watch.plist" "$watch"
fi
codesign --force --sign "$identity" --keychain "$kc" --entitlements "$out/ent-app.plist" "$app"
codesign --verify --deep --strict --verbose=1 "$app"
"$here/scripts/wellsstar/check-signed.sh" "$app"
(cd "$out/ipa" && zip -qry ../ABS.ipa Payload)
echo "built $out/ABS.ipa (build $build)"
[ $upload = 1 ] || exit 0
xcrun altool --upload-app -f "$out/ABS.ipa" -t ios \
    --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID" --p8-file-path "$ASC_KEY_PATH"
"$asc" testflight $bundle "$build"
