# Luma TV 0.5.0

- Simplified playback: Sources, Next episode, and Sleep timer now live in More.
- Darker playback overlays improve readability over bright video.
- Consistent 36px playback buttons, rounded navigation, accessible control names, and compact mini-player access.
- Clearer desktop connection instructions, QR loading and retry messages, and expired-code handling. Stale pairing responses and QR images cannot replace a newer code.
- Uses the platform font instead of requesting missing Inter/Noto font families.
- The macOS shared OpenGL context fix is now part of the source, preserving embedded playback.

Downloads:

- Fedora x86_64: AppImage, or the source archive with `install.py` and `launch.sh`. The AppImage retains the verified 0.4.0 Fedora 44 Python/native runtime and updates the application source; host graphics/audio and a desktop keyring are required.
- Intel Mac: DMG for macOS 13 Ventura or newer. Media libraries come from the official IINA 1.3.5 release, matching the previous Ventura compatibility build.
- Apple silicon: DMG for macOS 15 or newer, with native Homebrew media libraries.

macOS builds are ad-hoc signed, not Apple-notarized. Drag Luma TV into Applications. If macOS blocks launch, review it in System Settings > Privacy & Security.

Each package must pass offline GUI, H.264/AAC playback, pause/seek, recording/replay, and embedded OpenGL/mini-player checks before publication. Build logs and SHA-256 checksums accompany downloads. Offline tests use temporary preferences and synthetic media; real account pairing and external provider streams are not covered.
