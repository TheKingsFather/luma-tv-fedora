# Intel macOS DMG builds

The 0.5.0 release workflow builds Fedora x86_64 and Intel macOS only. GitHub's
native Intel Mac runner packages Python, Qt, and libmpv, validates playback and
recording, and creates the DMG with Apple's `hdiutil`.

The Intel build targets macOS 13 Ventura or newer. Its matched media libraries
come from the official IINA 1.3.5 distribution, staged by `prepare_media.py`.
The build rejects any native dependency requiring a newer OS than the bundle's
declared minimum. Native playback tests run on the GitHub macOS 15 Intel host;
the minimum deployment-target check is separate from an actual Ventura runtime test.

On a native Intel macOS build host, install the Python requirements and ffmpeg,
then stage the IINA libraries and build:

```sh
brew install ffmpeg
python3 -m pip install -r packaging/macos/requirements.txt
python3 packaging/macos/prepare_media.py /Volumes/IINA/IINA.app/Contents/Frameworks build/ventura-media
LUMA_MPV_LIBRARY="$PWD/build/ventura-media/libmpv.2.dylib" LUMA_MACOS_MINIMUM=13.0 python3 packaging/macos/build.py --arch x86_64
```

Output is in `dist/macos/`: the DMG, checksum, build manifest, offline test logs,
and synthetic pairing/player previews. The app uses Keychain for the vault key
and Application Support for encrypted state. Account data is not bundled.

The app is ad-hoc signed, not Apple-notarized. Tests cover architecture, code
signatures, H.264/AAC playback, pause/seek, recording/replay, embedded OpenGL,
mini-player transitions, temporary encrypted storage, certificates, and DMG
integrity. Real account pairing and external providers remain outside these checks.
