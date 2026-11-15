# Luma TV 0.6.0

- Display the current decoded stream resolution (1080p, 1440p, 2160p, etc.) in full and mini player controls. Updates when an adaptive stream changes resolution; clears when changing or stopping a source.
- Settings → Check for app updates checks stable GitHub Releases, downloads the matching platform package, verifies its SHA-256 digest and installs with a rollback copy before restarting. Supports macOS app bundles and Fedora AppImages in writable locations.
- Private repository access uses GH_TOKEN/GITHUB_TOKEN, an existing GitHub CLI login, or a token entered for this app session. Tokens are never saved to preferences or included in release artifacts. Fine-grained tokens need Contents: Read on this repository.
- Installation preserves Stremio account data and preferences. Stop a recording before updating. Source checkouts show guidance to use a packaged edition.
