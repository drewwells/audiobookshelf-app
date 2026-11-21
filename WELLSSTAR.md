# Building the fork (beast, Xcode 27)

The fork of [advplyr/audiobookshelf-app](https://github.com/advplyr/audiobookshelf-app) that TestFlight hands
out as "ABS Fork" (`dev.wellsstar.abs`, team 8943DPB6NM), with its Apple Watch app (`dev.wellsstar.abs.watchkitapp`,
from [drewwells/abs-watch](https://github.com/drewwells/abs-watch)). Server: `https://read.wellsstar.dev/abs`.

1. Web bundle: `npm ci`, `npm run generate`, `npx cap copy ios`.
2. Pods: `cd ios/App && pod install` (CocoaPods 1.17; Brewfile line `brew "cocoapods"`).
3. Simulator: `xcodebuild -workspace ios/App/App.xcworkspace -scheme App -destination 'platform=iOS Simulator,name=iPhone 17'
   CODE_SIGNING_ALLOWED=NO IPHONEOS_DEPLOYMENT_TARGET=15.0 build`. Pass the deployment target: the pods ask for 14.0,
   which Xcode 27 refuses.
4. TestFlight: `scripts/wellsstar/testflight.sh` archives unsigned, signs every Mach-O by hand with the Apple
   Distribution identity in `~/Library/Keychains/deej-signing.keychain-db` and the App Store profiles in
   `~/.config/abs-signing/`, uploads with `altool` and the App Store Connect API key, and gives the build to the
   internal group "abs internal" (`scripts/wellsstar/asc.py`). Profiles: `scripts/wellsstar/provision.sh`.

Changes from upstream: bundle ids and display name; `SceneDelegate` + `UIApplicationSceneManifest` (iOS 27 requires
UIScene; Main.storyboard is now the scene's); iOS 15 minimum; the watch app in `watch/` (a git submodule).
