"""Offline AppImage builder for the installed Fedora x86_64 Luma TV runtime.

Run with the app's virtualenv Python. No provider settings or keyring data are read.
The explicit bundled ELF loader keeps native dependencies together, including libc.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import sysconfig

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent
BUILD = SOURCE / 'build' / 'appimage'
APP = BUILD / 'Luma-TV.AppDir'
OUTPUT = SOURCE / 'dist' / 'Luma-TV-x86_64.AppImage'
LIB = APP / 'usr/lib'
PYTHON = APP / 'usr/lib/python3.14'
SITE = PYTHON / 'site-packages'
DATA = APP / 'usr/share/luma-tv'
NATIVE_SOURCES = set()


def copy(source, destination):
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    else:
        shutil.copy2(source, destination)
    return destination


def native(source, destination):
    result = copy(source, destination)
    NATIVE_SOURCES.add(Path(source).resolve())
    return result


def bundled_program(name):
    native(shutil.which(name), APP / 'usr/libexec' / name)
    wrapper = APP / 'usr/bin' / name
    wrapper.write_text('#!/bin/sh\nset -eu\n'
                       'exec "$APPDIR/usr/lib/ld-linux-x86-64.so.2" --inhibit-cache '
                       '--library-path "$APPDIR/usr/lib" '
                       f'"$APPDIR/usr/libexec/{name}" "$@"\n')
    wrapper.chmod(0o755)


def collect_dependencies():
    checked = set()
    missing = set()
    queue = list(NATIVE_SOURCES)
    while queue:
        source = queue.pop()
        if source in checked:
            continue
        checked.add(source)
        result = subprocess.run(['ldd', str(source)], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if '=> not found' in line:
                missing.add(line.strip())
            match = re.search(r'=> (/\S+)', line) or re.match(r'\s*(/\S+)\s+\(', line)
            if not match:
                continue
            dependency = Path(match[1])
            target = LIB / dependency.name
            if target.exists():
                if target.resolve().read_bytes() != dependency.read_bytes():
                    raise RuntimeError(f'Conflicting native library: {dependency}')
                continue
            native(dependency, target)
            queue.append(dependency.resolve())
    if missing:
        raise RuntimeError('Missing libraries: ' + ', '.join(sorted(missing)))
    print(f'Collected {len(NATIVE_SOURCES)} native files', flush=True)


def extract_runtime():
    donor = Path(os.environ.get('LUMA_RUNTIME_DONOR',
                                str(Path.home() / 'Downloads/iloader-linux-amd64.AppImage')))
    with donor.open('rb') as source:
        assert source.read(4) == b'\x7fELF', 'Runtime donor is not an ELF AppImage'
    offset = int(subprocess.check_output([str(donor), '--appimage-offset'], text=True))
    with donor.open('rb') as source:
        runtime = bytearray(source.read(offset))
    assert runtime[8:11] == b'AI\x02', 'Expected a type 2 AppImage runtime'
    # Remove the donor app's update information, signature and checksum sections.
    section_offset = struct.unpack_from('<Q', runtime, 40)[0]
    section_size, section_count, names_index = struct.unpack_from('<HHH', runtime, 58)
    names_header = section_offset + section_size * names_index
    names_offset, names_size = struct.unpack_from('<QQ', runtime, names_header + 24)
    names = runtime[names_offset:names_offset + names_size]
    for number in range(section_count):
        header = section_offset + number * section_size
        name_offset = struct.unpack_from('<I', runtime, header)[0]
        name = names[name_offset:].split(b'\0', 1)[0]
        if name in (b'.upd_info', b'.sha256_sig', b'.sig_key', b'.digest_md5'):
            start, size = struct.unpack_from('<QQ', runtime, header + 24)
            runtime[start:start + size] = b'\0' * size
    path = BUILD / 'runtime-x86_64'
    path.write_bytes(runtime)
    path.chmod(0o755)
    return path, {'source': str(donor), 'runtime_version': subprocess.check_output(
        [str(donor), '--appimage-version'], text=True, stderr=subprocess.STDOUT).strip(),
        'sha256': hashlib.sha256(runtime).hexdigest()}


def write_image(runtime):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    squash = BUILD / 'luma-tv.squashfs'
    subprocess.run(['mksquashfs', str(APP), str(squash), '-noappend', '-comp', 'zstd',
                    '-Xcompression-level', '10', '-all-root', '-processors', '4', '-no-progress'],
                   check=True)
    with OUTPUT.open('wb') as target:
        for part in (runtime, squash):
            with part.open('rb') as source:
                shutil.copyfileobj(source, target)
    OUTPUT.chmod(0o755)
    checksum = hashlib.sha256(OUTPUT.read_bytes()).hexdigest()
    OUTPUT.with_suffix('.AppImage.sha256').write_text(f'{checksum}  {OUTPUT.name}\n')
    print(json.dumps({'appimage': str(OUTPUT), 'bytes': OUTPUT.stat().st_size,
                      'sha256': checksum}), flush=True)


def main():
    if sys.version_info[:2] != (3, 14):
        raise SystemExit('This AppImage builder requires Python 3.14 on Fedora 44. '
                         'Use that build environment; the source launcher can use the current Fedora Python.')
    if APP.exists():
        shutil.rmtree(APP)
    SITE.mkdir(parents=True)
    (APP / 'usr/lib64').symlink_to('lib')
    (APP / 'usr/bin').mkdir(parents=True)
    DATA.mkdir(parents=True)
    stdlib = Path(sysconfig.get_path('stdlib'))
    for item in stdlib.iterdir():
        if item.name in ('site-packages', '__pycache__', 'test', 'idlelib', 'tkinter',
                         'turtledemo', 'ensurepip', 'config-3.14-x86_64-linux-gnu'):
            continue
        copy(item, PYTHON / item.name)
    for name in ('requests', 'certifi', 'cryptography', 'cffi', '_cffi_backend',
                 'mpv', 'urllib3', 'charset_normalizer', 'idna',
                 'pycparser', 'brotli', '_brotli'):
        spec = importlib.util.find_spec(name)
        if spec is None:
            if name in ('brotli', '_brotli'):
                continue
            raise RuntimeError('Missing Python module: ' + name)
        source = Path(spec.origin)
        source = source.parent if spec.submodule_search_locations else source
        copy(source, SITE / source.name)
    qt_source = Path(importlib.util.find_spec('PyQt6').origin).parent
    for name in ('__init__.py', 'QtCore.abi3.so', 'QtGui.abi3.so', 'QtWidgets.abi3.so',
                 'QtNetwork.abi3.so', 'QtSvg.abi3.so', 'QtOpenGL.abi3.so', 'QtOpenGLWidgets.abi3.so'):
        copy(qt_source / name, SITE / 'PyQt6' / name)
    for item in qt_source.glob('sip*.so'):
        copy(item, SITE / 'PyQt6' / item.name)
    for item in PYTHON.rglob('*.so'):
        NATIVE_SOURCES.add(item)
    native('/usr/bin/python3.14', APP / 'usr/bin/python3.14')
    for program in ('secret-tool',):
        bundled_program(program)
    native('/usr/lib64/libmpv.so.2', LIB / 'libmpv.so.2')
    for group, names in {
        'platforms': ['libqxcb.so', 'libqoffscreen.so', 'libqminimal.so'],
        'imageformats': ['libqgif.so', 'libqico.so', 'libqjpeg.so', 'libqsvg.so', 'libqwebp.so'],
        'xcbglintegrations': ['libqxcb-glx-integration.so', 'libqxcb-egl-integration.so'],
        'tls': ['libqopensslbackend.so'],
    }.items():
        for name in names:
            path = Path('/usr/lib64/qt6/plugins') / group / name
            if path.exists():
                native(path, LIB / 'qt6/plugins' / group / name)
    for directory in ('pipewire-0.3', 'spa-0.2', 'alsa-lib', 'gio/modules', 'gconv'):
        for item in (Path('/usr/lib64') / directory).rglob('*.so'):
            native(item, LIB / directory / item.relative_to(Path('/usr/lib64') / directory))
    copy('/usr/lib64/gconv/gconv-modules', LIB / 'gconv/gconv-modules')
    copy('/usr/lib64/gconv/gconv-modules.d', LIB / 'gconv/gconv-modules.d')
    native('/usr/lib64/ossl-modules/legacy.so', LIB / 'ossl-modules/legacy.so')
    for name in ('libnss_dns.so.2', 'libnss_files.so.2', 'libresolv.so.2',
                 'libGL.so.1', 'libEGL.so.1', 'libGLX.so.0', 'libGLX_mesa.so.0',
                 'libGLdispatch.so.0', 'libSDL3.so.0'):
        if (Path('/usr/lib64') / name).exists():
            native(Path('/usr/lib64') / name, LIB / name)
    collect_dependencies()
    copy('/usr/share/alsa', APP / 'usr/share/alsa')
    copy('/usr/share/pipewire', APP / 'usr/share/pipewire')
    copy('/usr/lib/locale/C.utf8', APP / 'usr/lib/locale/C.utf8')
    copy('/usr/share/fonts/abattis-cantarell-fonts', APP / 'usr/share/fonts/cantarell')
    copy('/usr/share/licenses/abattis-cantarell-fonts',
         APP / 'usr/share/licenses/abattis-cantarell-fonts')
    fonts = APP / 'usr/etc/fonts/fonts.conf'
    fonts.parent.mkdir(parents=True)
    fonts.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">'
                     '<fontconfig><dir prefix="relative">../../share/fonts</dir>'
                     '<dir>/usr/share/fonts</dir><dir prefix="xdg">fonts</dir>'
                     '<cachedir prefix="xdg">fontconfig</cachedir>'
                     '<include ignore_missing="yes">/etc/fonts/conf.d</include></fontconfig>')
    import certifi
    copy(certifi.where(), DATA / 'cacert.pem')
    for name in ('luma.py', 'backend.py', 'cards.py', 'player.py', 'player_view.py'):
        copy(SOURCE / name, DATA / name)
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                    '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10',
                    '-f', 'lavfi', '-i', 'anullsrc=channel_layout=stereo:sample_rate=48000',
                    '-t', '8', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest',
                    str(DATA / 'playback-test.mp4')], check=True)
    copy(HERE / 'launch.py', DATA / 'launch.py')
    copy(HERE / 'AppRun', APP / 'AppRun').chmod(0o755)
    copy(HERE / 'tv.luma.Fedora.desktop', APP / 'tv.luma.Fedora.desktop')
    copy(SOURCE / 'luma.svg', APP / 'luma.svg')
    copy(APP / 'luma.svg', DATA / 'luma.svg')
    (APP / '.DirIcon').symlink_to('luma.svg')
    (APP / 'usr/bin/luma-tv').symlink_to('../../AppRun')
    (APP / 'usr/bin/qt.conf').write_text('[Paths]\nPrefix=..\nPlugins=lib/qt6/plugins\n')
    subprocess.run(['desktop-file-validate', str(APP / 'tv.luma.Fedora.desktop')], check=True)
    runtime, provenance = extract_runtime()
    owners = subprocess.run(['rpm', '-qf', '--qf', '%{NAME}\n',
                             *map(str, sorted(NATIVE_SOURCES))], capture_output=True, text=True)
    packages = sorted({line for line in owners.stdout.splitlines()
                       if line and 'not owned' not in line and '/' not in line})
    listing = subprocess.run(['rpm', '-ql', *packages], capture_output=True, text=True)
    for line in listing.stdout.splitlines():
        if line.startswith('/usr/share/licenses/') and Path(line).is_file():
            copy(line, APP / line.lstrip('/'))
    for parent in {Path(importlib.util.find_spec(name).origin).parent.parent for name in
                   ('requests', 'certifi', 'cryptography', 'mpv', 'PyQt6')}:
        for metadata in parent.glob('*.dist-info'):
            if any(metadata.name.lower().startswith(prefix) for prefix in
                   ('requests-', 'certifi-', 'cryptography-', 'python_mpv-', 'pyqt6-',
                    'cffi-', 'urllib3-', 'idna-', 'charset_normalizer-')):
                copy(metadata, SITE / metadata.name)
    # python-mpv is a single module, so its distribution metadata sits next to it.
    for metadata in Path(importlib.util.find_spec('mpv').origin).parent.glob('*.dist-info'):
        if metadata.name.lower().startswith('python_mpv-'):
            copy(metadata, SITE / metadata.name)
    manifest = {'app': 'Luma TV', 'version': '0.3.0', 'architecture': 'x86_64',
                'build_os': Path('/etc/os-release').read_text(),
                'python': sys.version, 'runtime': provenance, 'rpm_packages': packages,
                'source_sha256': {name: hashlib.sha256((SOURCE / name).read_bytes()).hexdigest()
                                  for name in ('luma.py', 'backend.py', 'cards.py', 'player.py', 'player_view.py')}}
    (DATA / 'build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (DATA / 'THIRD_PARTY.txt').write_text(
        'This personal Linux bundle includes CPython, PyQt6/Qt, libmpv, python-mpv, '
        'cryptography, Requests and Fedora shared libraries. Package licenses '
        'are under usr/share/licenses and Python *.dist-info directories. '
        'RPM package inventory is in build-manifest.json. Fedora package sources: '
        'https://src.fedoraproject.org/ . The unmodified AppImage type2 runtime '
        '(apart from clearing donor update/signature fields) is from '
        'https://github.com/AppImage/type2-runtime/commit/75849dc . '
        'AppImage runtime source and license: https://github.com/AppImage/type2-runtime .\n')
    write_image(runtime)


if __name__ == '__main__':
    main()
