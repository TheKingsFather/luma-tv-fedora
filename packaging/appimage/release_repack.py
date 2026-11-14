"""Update application source using the verified, released Fedora 44 runtime."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build

def main():
    image = Path(sys.argv[1]).resolve()
    build.BUILD.mkdir(parents=True, exist_ok=True)
    offset = int(subprocess.check_output([str(image), '--appimage-offset'], text=True))
    runtime = image.read_bytes()[:offset]
    subprocess.run([str(image), '--appimage-extract'], cwd=build.BUILD, check=True, stdout=subprocess.DEVNULL)
    shutil.move(str(build.BUILD / 'squashfs-root'), str(build.APP))
    (build.BUILD / 'runtime-x86_64').write_bytes(runtime)
    manifest = json.loads((build.DATA / 'build-manifest.json').read_text())
    assert hashlib.sha256(runtime).hexdigest() == manifest['runtime']['sha256']
    build.repack()
    shutil.copy2(build.DATA / 'build-manifest.json', ROOT / 'dist/build-manifest-fedora.json')

if __name__ == '__main__':
    main()
