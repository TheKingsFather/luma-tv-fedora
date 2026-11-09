# Luma TV for Fedora

Native Qt desktop edition of Luma, with the teal/violet glass theme, Stremio QR pairing and mpv video playback. Version 0.4.0.

Source repository: [TheKingsFather/luma-tv-fedora](https://github.com/TheKingsFather/luma-tv-fedora) (private).

To install from a clone, follow the Fedora dependency instructions below, then run `python3 install.py` and `./launch.sh`. Release source archives and validation results are in `artifacts/`. Personal account and pairing screenshots remain local; the included embedded-player preview uses a generated test clip.

## Open

Search **Luma TV** in the Fedora applications menu, run `luma-tv`, or run `./launch.sh` from this folder. Scan the QR code with your phone and connect on Stremio's official linking page. You can also enter the displayed code at `link.stremio.com`. The desktop uses its own connection; it does not extract the Android app's credentials.

The **Explore the interface** button opens public Cinemeta catalogs before connecting. Once connected, the app imports your installed Stremio add-ons and library. Manage add-ons in Stremio on your phone, then use **Settings → Refresh Stremio** here.

## Features

- Native resizable Qt window, artwork-backed glass panels, poster rows, mouse and keyboard navigation.
- Home, Movies, Series, Live catalogs, search, catalog pagination, library, details and season/episode selection.
- Direct stream discovery, provider request headers, source selection and failover.
- Embedded libmpv playback inside Luma, with pause, seek, audio/subtitle selection, add-on subtitle downloads, next episode and sleep timer controls in Luma.
- Floating, resizable mini player with compact glass controls; keep watching while browsing or using other apps.
- Record the current source to a local video file, with an elapsed timer and a persistent indicator in full and mini player modes.
- Continue watching and watch-state sync. Offline changes are saved locally and retried on refresh or subsequent writes.
- Encrypted account/cache file. Its encryption key is stored in Fedora's Secret Service keyring. The app never writes an unencrypted Stremio auth key to disk or passes stream URLs in mpv's command-line arguments.

Playback renders directly into Luma’s video surface with glass controls. It supports direct HTTP(S) streams, not raw torrent/infoHash-only sources. DRM setup and Alder's native FFmpeg/chapter extensions are not included. Connect your account using QR pairing to import your add-ons and library.

## Record a stream

During playback, click **● Record** in the player header, or press **Ctrl+R** while the player has focus. Choose a filename; the default folder is **Videos/Luma Recordings**, and Luma remembers your chosen folder. Recordings use Matroska (`.mkv`) and preserve the source's original quality without re-encoding or opening a second stream connection.

The control turns **red** and becomes **Stop** with an elapsed timer. A red recording badge remains visible when the playback controls fade, and the mini player has its own red stop control. Click **Stop** or press **Ctrl+R** again to finish the file. The saved notice includes **Open folder**.

The save window opens asynchronously inside Qt so video keeps playing while you choose a filename. It belongs to the visible player window, including the always-on-top mini player. Cancelling leaves playback running without starting a recording.

Seeking, changing source or tracks, stopping playback, reaching the end, and closing Luma finish the current recording. Moving between the full and mini player keeps it running. Existing files are never overwritten.

Recording uses mpv's continuous cache dump, so clips can begin at a nearby keyframe and include buffered video ahead of the playhead. Some source formats cannot be recorded into Matroska; unsupported recordings report an error, and empty output files are removed. If recording ends with an error after writing data, Luma keeps the partial file. See the [mpv recording reference](https://mpv.io/manual/stable/).

## Controls

- Luma: **F11** fullscreen, **Ctrl+F** search, **Escape** back.
- In-app player: **Space** pause, **←/→** seek ten seconds, **F** fullscreen, **M** mute.
- Use the glass controls for source selection, volume, audio tracks, subtitles, next episode and sleep timer.
- Click **Mini player** or press **P** during playback. **Ctrl+Shift+P** toggles mini/full mode from the main window.
- Mini player: drag the title to move, drag the bottom-right grip to resize, use **↗** or double-click video to restore. **Escape/P/F** restores from the mini window. **×** stops playback. The main window’s **Return to player** button restores it too.
- Closing Luma also stops playback. Settings → Disconnect removes this desktop's saved account data.

## Dependencies on another Fedora machine

```bash
sudo dnf install python3-pyqt6-base python3-requests python3-cryptography libsecret mpv python3-pip
python3 install.py
./launch.sh
```

To register the applications-menu entry after extracting the source on another machine, run `python3 install.py` once from the extracted folder. Keep the folder in place afterward; the launcher points to it.

Your desktop must provide a Secret Service keyring (GNOME Keyring or an equivalent). The installer creates a local `.venv` that uses Fedora’s installed Qt packages and pins `python-mpv` from `requirements.txt`. It does not modify the system Python environment.

Data: `$XDG_DATA_HOME/luma-desktop/session.enc` (normally `~/.local/share/luma-desktop/session.enc`). Preferences: Qt's `Luma/Desktop` settings. Video runs in-process; no external player or IPC socket is created. Downloaded subtitle files use a private temporary directory removed on stop. Subtitle downloads use separate requests without video-provider headers.

### Repair after a Fedora Python upgrade

If Luma stops opening with `ModuleNotFoundError: No module named 'mpv'` after a Python upgrade, run these commands from the project folder:

```bash
python3 install.py
./launch.sh
```

The virtual environment's Python symlink can follow Fedora's new interpreter while its locally installed packages remain under the previous Python version. Rerunning the installer installs the pinned playback binding for the current interpreter. Your saved account and preferences are stored outside `.venv`.

## AppImage packaging

Download the x86_64 AppImage or source archive from [GitHub Releases](https://github.com/TheKingsFather/luma-tv-fedora/releases/latest). The [AppImage build instructions](packaging/appimage/README.md) describe the bundled runtime, checks and build requirements. A full runtime build targets Fedora 44 with Python 3.14; application files can also be refreshed in an existing AppDir using `--repack`.

## Validation

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=xcb .venv/bin/python -m unittest discover -s tests -p test_embedded.py -v
QT_QPA_PLATFORM=offscreen ./launch.sh --preview --smoke
```

The offscreen checks cover browsing, navigation, recording and local engine playback. Recording fixtures verify playable audio/video files, an authenticated local HTTP transport stream without another connection, existing-file protection, error cleanup and finishing recordings on seek, source changes, end-of-playback and shutdown. A separate xcb run verifies decoded frames inside Luma’s framebuffer, playback controls, resizing, repeated browse/play transitions, mini-player recording and final cleanup. See `artifacts/tests.log`, `artifacts/render-tests.log` and the UI screenshots.

Live API tests create an unclaimed temporary pairing code; they never connect an account or write to a real library.

## Files

- `luma.py`: native screens and UI workers
- `backend.py`: Stremio protocol, library state, keyring-backed encrypted storage
- `player.py`: in-process libmpv and Qt OpenGL rendering
- `player_view.py`: glass playback overlays and controls
- `launch.sh`: desktop entry point
- `tests/test_luma.py`: automated checks

Protocol references: [Stremio add-on protocol](https://github.com/Stremio/stremio-addon-sdk/blob/master/docs/protocol.md), [linking API definitions](https://stremio.github.io/stremio-core/src/stremio_core/types/api/request.rs.html), [mpv IPC and playback options](https://mpv.io/manual/stable/).

## 0.1.1 — Live catalog correction

Live uses explicit TV/channel/sport/event categories rather than treating every custom type as live. Anime, generic download libraries, replays and highlights are excluded. The eight-catalog cutoff is removed from Live. Entering Live refreshes the account add-on list and the configured live-provider manifests without flushing pending library writes. Providers that declare live types but return no catalogs are shown with an explanation. Catalog items missing a type inherit it from their catalog so channel playback uses the right provider resource.

## 0.1.2 — Identity and adaptive cards

An original folded-light Luma monogram replaces the placeholder mark. Installed icons include SVG plus PNG sizes from 16 to 512 pixels. The desktop file uses an explicit icon path, and Qt now sets the matching desktop application ID so GNOME can associate its window with Luma rather than Python. Logo research: [Dribbble app-logo references](https://dribbble.com/tags/app-logo); no reference artwork is bundled.

Live cards use landscape frames. Artwork is painted from the original image with aspect-preserving containment instead of centre-cropping. Square logos remain complete; movie posters retain portrait proportions and explicit square/landscape poster shapes are respected. The grid reflows with the viewport, and titles have two lines plus full-name tooltips. Cards support mouse and keyboard activation.

Validation includes both edges of a wide image painted into a portrait frame, live-card proportions, keyboard activation, grid expansion/shrinking and icon rendering at launcher sizes. Real live-feed screenshots were reviewed at 1920 and 1100 pixel window widths. Restart the app to load these UI changes; the active player was not interrupted during installation.


## 0.2.0 — Playback inside Luma

Replaced the external mpv process with libmpv rendering into a persistent Qt OpenGL video surface. Browsing unloads the current video; returning to playback reuses the same engine and renderer. The renderer is released before the engine at app close. Glass controls overlay the video and hide during playback. The video keeps its native aspect ratio, with letterboxing where needed.


## 0.2.1 — Instant Back navigation

During a section visit, Luma keeps browse pages alive in memory, including their decoded artwork, loaded catalog pages, focus and scroll positions. Back from details restores the last listing. Stopping or finishing Live playback returns directly to that cached listing without refreshing add-ons, catalogs or artwork. Selecting the current section again also reuses it. Switching to another section discards the previous section’s browse cache; returning to Live then refreshes its add-ons and catalogs. Settings → Refresh Stremio explicitly invalidates cached pages too.

Pending catalog and artwork requests can complete on retained pages without navigating away from the active screen. Results from discarded sections are ignored. Five navigation checks verify pagination and both scroll axes, repeated Back navigation without requests, section invalidation, late responses and Live end-of-stream navigation. A real OpenGL playback check verifies the embedded player returns to the same card widgets.


## 0.3.0 — Floating mini player

The full player’s Mini player button moves the existing video surface into a resizable, always-on-top window with glass pause, seek, mute, restore and close controls. The main window returns to its cached listing and remains usable while playback continues. Returning to full playback preserves position, pause state, tracks, volume and the same libmpv engine and render context. Starting another title replaces the current stream. Closing the mini player stops playback and leaves the current browse page intact; closing Luma shuts down both windows. Live end-of-stream closes the mini player without reloading browse cards.

Qt OpenGL context sharing is enabled before application creation so moving the video widget between windows preserves its render context ([Qt resource-sharing documentation](https://doc.qt.io/qt-6/qopenglwidget.html#resource-sharing)). Real video checks cover repeated mini/full transitions without reloading the source, pause/play, resizing, independent visibility when Luma is minimized, browsing, Live completion, closing PiP and closing Luma while PiP is active. The fixture screenshot is `artifacts/mini-player.png`.

## 0.4.0 — Recording and responsive controls

Record the current source to Matroska with Ctrl+R or the player’s Record button. Full-player, mini-player and hidden-controls indicators turn solid red while recording, with an elapsed timer and a saved-file folder action. Seeking, source or track changes, stopping playback and closing Luma finish the recording cleanly.

The save window opens asynchronously in Qt, keeping the video event loop active and attaching to the visible player window. Recording buttons are restyled only when their state changes. The release includes the updated x86_64 AppImage, a source archive and SHA-256 checksums.
