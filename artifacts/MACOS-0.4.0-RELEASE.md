# Luma TV 0.4.0 for macOS

Standalone macOS builds of the desktop app, orchestrated from Fedora and
built on native GitHub macOS runners.

| Mac | Download | Size |
| --- | --- | --- |
| Intel | `Luma-TV-0.4.0-macOS-x86_64.dmg` | 77,171,450 bytes |
| Apple silicon (M-series) | `Luma-TV-0.4.0-macOS-arm64.dmg` | 70,392,709 bytes |

Requires **macOS 15 or later**. Open the matching DMG and drag **Luma TV**
into **Applications**. Python, Qt and libmpv are bundled. The vault key uses
macOS Keychain, and encrypted account data is stored in
`~/Library/Application Support/Luma TV/session.enc`.

The apps are **ad-hoc signed, not Apple-notarized**. If macOS blocks the app,
review it in **System Settings → Privacy & Security**.

Both builds passed code-signature and architecture checks, startup,
generated H.264/AAC playback, pause/seek, recording/replay, embedded OpenGL,
mini-player transitions, encrypted temporary storage, certificate loading
and `hdiutil verify`. REA inspected each finished DMG with complete
container-entry coverage and no integrity contradictions. Static inventory
does not establish runtime behavior; playback was checked by the separate
native self-tests. Live account pairing and external provider streams were
not tested.

The release includes SHA-256 files, build manifests, self-test/render logs,
and complete REA evidence with its summary for each architecture.

```text
f89200e1efb5beab60a0406b80bb4c5f31665fa6e577f31fe2418c5f8ae0003c  Luma-TV-0.4.0-macOS-x86_64.dmg
811e55c16feb5105cbc42d055fc1e8c6b503de47ff5acde43dc291e7b5927619  Luma-TV-0.4.0-macOS-arm64.dmg
```

Source revision: [`486c8808`](https://github.com/TheKingsFather/luma-tv-fedora/commit/486c8808c0fdd0a35223cd448c06deea000ff7bb).
Native build and validation: [GitHub Actions run 43284529939](https://github.com/TheKingsFather/luma-tv-fedora/actions/runs/43284529939).

REA inspection Evidence:

- Intel: `ev_3843d60f158b841b55ff320e584419eb0d25187a5528ed0ca98588d5aa5e987e`
- Apple silicon: `ev_6753a00fb24b5fbc9c17063ddf20fc9b9904625b3be47df48233f39a6612b564`
