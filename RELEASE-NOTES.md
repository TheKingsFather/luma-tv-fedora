# Luma TV 0.5.2

- Fixed unintended playback pauses when clicking empty control-panel space, labels, or disabled controls. Panel clicks no longer bubble into the video's click-to-pause handler.
- Applied the same protection to mini-player controls and recording notices. Play/pause buttons and clicks on the unobstructed video retain their existing behavior.
- Added regression coverage for real Qt mouse-event propagation through full-size and mini-player panels, and native packaged playback checks.
- Retains the dropdown arrow and rounded popup corrections from 0.5.1.

Downloads: Fedora x86_64 AppImage/source archive and Intel macOS 13+ DMG. No Apple silicon build. The Mac app is ad-hoc signed, not notarized.

Packages must pass offline GUI, control interaction, H.264/AAC playback, recording/replay, OpenGL, mini-player, and macOS native deployment-target checks before publication. Real provider streams and account pairing are outside the offline tests.
