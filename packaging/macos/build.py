"""Build, test and package a standalone macOS app on a native macOS runner."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'build/macos'
DIST = ROOT / 'dist/macos'


def run(*args, **kwargs):
    return subprocess.run(list(map(str, args)), check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--arch', required=True, choices=['arm64', 'x86_64'])
    arch = parser.parse_args().arch
    if sys.platform != 'darwin' or platform.machine() != arch:
        raise SystemExit(f'Build requires a native macOS {arch} runner.')
    BUILD.mkdir(parents=True, exist_ok=True)
    DIST.mkdir(parents=True, exist_ok=True)
    version = re.search(r"VERSION = '([^']+)'", (ROOT / 'luma.py').read_text()).group(1)
    prefix = Path(subprocess.check_output(['brew', '--prefix', 'mpv'], text=True).strip())
    mpv = prefix / 'lib/libmpv.2.dylib'
    if not mpv.is_file():
        raise SystemExit('Homebrew libmpv.2.dylib is missing.')
    run('lipo', mpv, '-verify_arch', arch)

    # Render the existing vector logo into Apple's native icon format.
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QGuiApplication, QPixmap, QPainter
    from PyQt6.QtSvg import QSvgRenderer
    app = QGuiApplication([])
    renderer = QSvgRenderer(str(ROOT / 'luma.svg'))
    assert renderer.isValid()
    iconset = BUILD / 'Luma.iconset'
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            pix = QPixmap(size * scale, size * scale)
            pix.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pix)
            renderer.render(painter)
            painter.end()
            suffix = '@2x' if scale == 2 else ''
            assert pix.save(str(iconset / f'icon_{size}x{size}{suffix}.png'))
    run('iconutil', '-c', 'icns', iconset, '-o', BUILD / 'Luma.icns')
    app.quit()
    os.environ.pop('QT_QPA_PLATFORM', None)

    fixture = BUILD / 'playback-test.mp4'
    run('ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
        '-i', 'testsrc2=size=320x180:rate=24', '-f', 'lavfi', '-i',
        'anullsrc=channel_layout=stereo:sample_rate=48000', '-t', '10',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-shortest', fixture)
    import certifi
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--windowed', '--onedir', '--name', 'Luma TV',
               '--osx-bundle-identifier', 'tv.luma.desktop',
               '--target-architecture', arch, '--codesign-identity', '-',
               '--icon', str(BUILD / 'Luma.icns'), '--paths', str(ROOT),
               '--distpath', str(DIST), '--workpath', str(BUILD / 'pyinstaller'),
               '--specpath', str(BUILD), '--add-binary', f'{mpv}:.',
               '--add-data', f'{ROOT / "luma.svg"}:.',
               '--add-data', f'{fixture}:.',
               '--add-data', f'{certifi.where()}:.' ,
               '--hidden-import', 'keyring.backends.macOS',
               '--collect-submodules', 'keyring.backends.macOS']
    # certifi's source filename is cacert.pem, as expected by launch.py.
    assert Path(certifi.where()).name == 'cacert.pem'
    for package in ('PyQt6', 'PyQt6-Qt6', 'PyQt6-sip', 'python-mpv',
                    'requests', 'cryptography', 'certifi', 'keyring'):
        command.extend(['--copy-metadata', package])
    command.append(str(ROOT / 'packaging/macos/launch.py'))
    run(*command, cwd=ROOT)
    bundle = DIST / 'Luma TV.app'
    info_path = bundle / 'Contents/Info.plist'
    with info_path.open('rb') as source:
        info = plistlib.load(source)
    info.update(CFBundleShortVersionString=version, CFBundleVersion=version,
                NSHighResolutionCapable=True, LSMinimumSystemVersion='15.0',
                LSApplicationCategoryType='public.app-category.entertainment')
    with info_path.open('wb') as target:
        plistlib.dump(info, target)
    run('codesign', '--force', '--deep', '--sign', '-', bundle)
    run('codesign', '--verify', '--deep', '--strict', '--verbose=2', bundle)
    executable = bundle / 'Contents/MacOS/Luma TV'
    run('lipo', executable, '-verify_arch', arch)
    environment = dict(os.environ)
    # Catch accidental dependence on Homebrew at runtime.
    environment['PATH'] = '/usr/bin:/bin:/usr/sbin:/sbin'
    for key in ('DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'PYTHONPATH', 'PYTHONHOME'):
        environment.pop(key, None)
    for name, args in (('self-test', ['--self-test']),
                       ('render-test', ['--self-test-render'])):
        with (DIST / f'{name}-{arch}.log').open('w') as log:
            run(executable, *args, env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=120)

    stage = BUILD / f'dmg-{arch}'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir()
    run('ditto', bundle, stage / bundle.name)
    (stage / 'Applications').symlink_to('/Applications')
    (stage / 'Read Me.txt').write_text('Luma TV '+version+' for macOS ('+arch+')\n\n'
        'Drag Luma TV into Applications, then open it.\n'
        'This personal build is ad-hoc signed and is not Apple-notarized.\n'
        'If macOS blocks it, review it in System Settings > Privacy & Security.\n'
        'Connect your Stremio account using the QR code.\n')
    dmg = DIST / f'Luma-TV-{version}-macOS-{arch}.dmg'
    dmg.unlink(missing_ok=True)
    run('hdiutil', 'create', '-volname', 'Luma TV', '-srcfolder', stage,
        '-format', 'UDZO', '-fs', 'HFS+', dmg)
    run('hdiutil', 'verify', dmg)
    with (DIST / f'rea-summary-{arch}.json').open('w') as report:
        run('npx', '-y', 'rea-agents@6.8.0', 'inspect-artifact', dmg,
            '--detail', 'summary', '--evidence_output', DIST / f'rea-evidence-{arch}.json',
            '--format', 'json', stdout=report, timeout=240)
    digest = hashlib.sha256(dmg.read_bytes()).hexdigest()
    dmg.with_suffix('.dmg.sha256').write_text(f'{digest}  {dmg.name}\n')
    metadata = {'app': 'Luma TV', 'version': version, 'architecture': arch,
                'source_revision': os.getenv('GITHUB_SHA'), 'host': platform.platform(),
                'dmg': dmg.name, 'sha256': digest, 'bytes': dmg.stat().st_size,
                'signing': 'ad-hoc, not notarized',
                'checks': ['codesign verification', 'architecture', 'offline playback/recording',
                           'embedded OpenGL and mini player', 'hdiutil verify'],
                'python_packages': {p: importlib.metadata.version(p) for p in
                    ('PyInstaller', 'PyQt6', 'requests', 'cryptography', 'python-mpv', 'keyring')}}
    (DIST / f'build-manifest-{arch}.json').write_text(json.dumps(metadata, indent=2)+'\n')
    print(json.dumps(metadata), flush=True)


if __name__ == '__main__':
    main()
