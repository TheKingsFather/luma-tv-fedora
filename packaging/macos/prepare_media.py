"""Stage a matched, Ventura-compatible media library closure from IINA 1.3.5."""
from pathlib import Path
import shutil
import subprocess
import sys

def stage(source, output):
    source, output = Path(source), Path(output)
    index = {p.name: p for p in source.rglob('*.dylib')}
    selected = {}

    def dependencies(path):
        lines = subprocess.check_output(['otool', '-L', str(path)], text=True).splitlines()[1:]
        return [line.strip().split(' (compatibility')[0] for line in lines]

    def collect(path):
        if path.name in selected:
            return
        selected[path.name] = path
        for dep in dependencies(path):
            if dep.startswith(('/usr/lib/', '/System/Library/')):
                continue
            name = Path(dep).name
            if name not in index:
                raise RuntimeError('Unresolved IINA dependency: ' + dep)
            collect(index[name])

    collect(index['libmpv.2.dylib'])
    output.mkdir(parents=True, exist_ok=True)
    for name, original in selected.items():
        target = output / name
        shutil.copy2(original.resolve(), target)
        target.chmod(0o755)
        changes = []
        for dep in dependencies(target):
            if Path(dep).name in selected:
                changes += ['-change', dep, '@loader_path/' + Path(dep).name]
        subprocess.run(['install_name_tool', '-id', '@loader_path/' + name, *changes, str(target)], check=True)
        subprocess.run(['codesign', '--force', '--sign', '-', str(target)], check=True)

    (output / 'libmpv.dylib').symlink_to('libmpv.2.dylib')

if __name__ == '__main__':
    stage(*sys.argv[1:])
