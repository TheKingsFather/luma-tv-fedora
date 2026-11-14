# Luma TV 0.5.1

- Fixed clipped and misplaced dropdown arrows. Season, audio/subtitle, and More controls now use the same right-aligned chevron, with space reserved so it cannot overlap text or curved edges.
- Fixed the More popup's square outer window by clipping the actual popup surface to its rounded outline, with a transparent backing surface.
- Retains the 0.5.0 playback, pairing, and macOS OpenGL improvements.

Downloads: Fedora x86_64 AppImage/source archive, and Intel macOS 13+ DMG. No Apple silicon build. The Mac app is ad-hoc signed, not notarized.

Offline interaction, popup geometry, playback, recording/replay, OpenGL, mini-player, and Ventura native deployment-target checks must pass before publication. Real provider streams and account pairing are outside the offline tests.
