#!/usr/bin/env python3
"""Register the extracted project for the current desktop user; no root required."""
import os
import shutil
import subprocess
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication,QPixmap,QPainter
from PyQt6.QtSvg import QSvgRenderer

root=Path(__file__).resolve().parent
# Keep the mpv Python binding isolated while using Fedora's Qt packages.
python=root/'.venv/bin/python'
if not python.exists():subprocess.run([sys.executable,'-m','venv','--system-site-packages',str(root/'.venv')],check=True)
subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check','-r',str(root/'requirements.txt')],check=True)
data=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))
apps=data/'applications';icons=data/'icons/hicolor/scalable/apps'
apps.mkdir(parents=True,exist_ok=True);icons.mkdir(parents=True,exist_ok=True)
launcher=root/'launch.sh';launcher.chmod(0o755)
shutil.copyfile(root/'luma.svg',icons/'tv.luma.Fedora.svg')
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
app=QGuiApplication([])
renderer=QSvgRenderer(str(root/'luma.svg'))
if not renderer.isValid():raise RuntimeError('Invalid Luma icon')
for size in (16,24,32,48,64,96,128,256,512):
    target=data/f'icons/hicolor/{size}x{size}/apps';target.mkdir(parents=True,exist_ok=True)
    pix=QPixmap(size,size);pix.fill(Qt.GlobalColor.transparent);paint=QPainter(pix);renderer.render(paint);paint.end();pix.save(str(target/'tv.luma.Fedora.png'))
icon_path=data/'icons/hicolor/512x512/apps/tv.luma.Fedora.png'
# Desktop Entry string escaping, not shell interpolation.
executable=str(launcher).replace('\\','\\\\').replace('"','\\"').replace('`','\\`').replace('$','\\$').replace('%','%%')
(apps/'tv.luma.Fedora.desktop').write_text('[Desktop Entry]\nType=Application\nName=Luma TV\nGenericName=Stremio media client\nComment=Your Stremio library in a glass desktop interface\nExec="'+executable+'"\nIcon='+str(icon_path)+'\nStartupWMClass=tv.luma.Fedora\nTerminal=false\nCategories=AudioVideo;Video;Player;\nKeywords=Stremio;Luma;Movies;Series;TV;\nStartupNotify=true\n')
bin_dir=Path.home()/'.local/bin';bin_dir.mkdir(parents=True,exist_ok=True)
link=bin_dir/'luma-tv'
if link.is_symlink():link.unlink()
if not link.exists():link.symlink_to(launcher)
if shutil.which('update-desktop-database'):subprocess.run(['update-desktop-database',str(apps)],check=True)
if shutil.which('gtk-update-icon-cache'):subprocess.run(['gtk-update-icon-cache','--force','--ignore-theme-index',str(data/'icons/hicolor')],check=True)
print('Installed Luma TV in your applications menu.')
