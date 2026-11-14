Luma TV 0.5.0 AppImage
====================

The finished executable is `~/Applications/Luma-TV-x86_64.AppImage`.
Double-click it, or launch without FUSE using:

```sh
~/Applications/Luma-TV-x86_64.AppImage --appimage-extract-and-run
```

The AppImage contains Luma TV's current source, Python, PyQt6/Qt, python-mpv,
libmpv, the Secret Service helper, certificates and native dependencies.
It uses the same saved connection and preferences as the existing launcher.
Personal account data, credentials, keys and screenshots are not bundled.
The original source launcher remains available.

This is an x86_64 Linux build assembled on Fedora 44. Other distributions have
not been validated. The desktop supplies X11/XWayland, OpenGL graphics drivers,
audio and a Secret Service compatible keyring such as GNOME Keyring. Unlock the
keyring to restore an existing connection. Python and native programs use the
bundled ELF loader and libraries. Fedora's absolute certificate paths are
redirected to the bundled CA roots, with TLS verification enabled.

Rebuild offline using an installed app environment on Fedora 44 with Python
3.14. The current builder explicitly targets that interpreter and refuses
other Python versions before changing the build directory:

```sh
cd ~/apps/luma-desktop
.venv/bin/python packaging/appimage/build.py
```

The builder requires the installed Fedora dependencies, `ffmpeg`, `mksquashfs`,
`rpm`, `ldd` and `desktop-file-validate`. It creates
`dist/Luma-TV-x86_64.AppImage` and its SHA-256 checksum. It reuses only the generic
type 2 AppImage runtime prefix from `~/Downloads/iloader-linux-amd64.AppImage`,
clears that app's update/signature/checksum metadata, and packages a fresh
SquashFS. Set `LUMA_RUNTIME_DONOR` to another compatible executable type 2
AppImage to change the runtime source. No iloader application files are included.

The bundle includes a source checksum inventory and native package inventory in
`usr/share/luma-tv/build-manifest.json`, with dependency licenses under
`usr/share/licenses` and Python distribution metadata directories.

For an application-only update, keep the existing AppDir and its native
dependencies and run:

```sh
python3 packaging/appimage/build.py --repack
```

This refreshes the application and launcher files, updates source checksums
and version metadata, and records the previous manifest checksum and repack
host separately. It verifies the retained AppImage runtime checksum before
packaging. This command can run on a newer host Python; it does not rebuild
or replace the bundled Python 3.14 or native dependencies. Version 0.5.0 uses
this application-only update of the existing Fedora 44 runtime.

Run the offline package check with:

```sh
QT_QPA_PLATFORM=offscreen ~/Applications/Luma-TV-x86_64.AppImage \
  --appimage-extract-and-run --self-test
```

This checks the GUI, icon, generated H.264/AAC playback through Luma's libmpv
engine, pause/seek, the real asynchronous recording dialog, recording start/stop,
playback of the recorded video/audio, shutdown, encrypted temporary vault,
isolated preferences and CA certificate loading. It does not contact Stremio, read personal account
data or open real speakers. The same check was also run in an empty filesystem
with host libraries hidden to detect missing dependencies.

The additional package check, `--self-test-render`, exercises the embedded
framebuffer and mini player when an X11 display is available:

```sh
QT_QPA_PLATFORM=xcb ~/Applications/Luma-TV-x86_64.AppImage \
  --appimage-extract-and-run --self-test-render
```

Release validation results are in `artifacts/RELEASE-0.4.0-VALIDATION.txt`.
