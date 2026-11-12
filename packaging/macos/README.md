# macOS DMG builds from Fedora

Fedora controls the build through GitHub Actions. Native macOS runners assemble
the app, bundle Python/Qt/libmpv, run playback and recording checks, and create
the DMG using Apple's `hdiutil`. The workflow builds arm64 (Apple silicon) and
x86_64 (Intel) separately.

On a native macOS build host:

```sh
brew install mpv ffmpeg
python3 -m pip install -r packaging/macos/requirements.txt
python3 packaging/macos/build.py --arch arm64
```

Use `--arch x86_64` on an Intel host. Output is in `dist/macos/`. Each artifact
contains the DMG, checksum, build manifest and validation logs. The macOS app
uses Keychain for its encryption key and Application Support for encrypted
state. No Fedora runtime files or personal account data are included.

The app is ad-hoc signed for this personal build. Apple Developer signing and
notarization require the owner's Apple credentials and are not configured.
Build checks cover architecture, code signatures, generated H.264/AAC playback,
pause/seek, recording/replay, embedded OpenGL, mini-player transitions, encrypted
temporary storage, certificates and DMG integrity. External providers and live
account pairing are outside these checks.
