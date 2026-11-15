#!/usr/bin/env python3
"""Luma for Fedora: native Qt glass UI, Stremio linking and mpv playback."""
import concurrent.futures as futures
import json
import math
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from PyQt6 import sip
from PyQt6.QtCore import Qt, QTimer, QObject, pyqtSignal, QSettings, QSize, QStandardPaths
from PyQt6.QtGui import QColor, QPainter, QLinearGradient, QRadialGradient, QPixmap, QIcon, QShortcut, QKeySequence, QTextDocument, QTextOption
from PyQt6.QtWidgets import (QApplication, QMainWindow, QStackedWidget, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QLineEdit, QDialog, QComboBox, QMessageBox, QSlider, QSizePolicy, QFileDialog, QStyleOptionButton, QStyle)
from backend import Client, request, browseable, extra, future_video, UA, LIVE_TYPES, catalog_choices
import updater
from player import Player
from cards import MediaCard, Artwork, ResponsiveGrid, CardRow
from player_view import PlaybackView,MiniPlayer

ROOT = Path(__file__).resolve().parent
VERSION = '0.6.1'
POOL = futures.ThreadPoolExecutor(8)
IMAGES = futures.ThreadPoolExecutor(4)
WRITES = futures.ThreadPoolExecutor(1)

STYLE = '''
QWidget {color:#F1F7FF; font-size:14px;}
QMainWindow, QDialog {background:#0B1423;}
QFrame#glass {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(99,123,151,65),stop:1 rgba(35,57,78,110)); border:1px solid rgba(224,250,255,55);border-radius:24px;}
QFrame#mediaCard {background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(99,123,151,65),stop:1 rgba(35,57,78,110));border:1px solid rgba(224,250,255,55);border-radius:20px;}
QFrame#mediaCard:hover,QFrame#mediaCard:focus {background:rgba(95,154,153,95);border:1px solid #C2F8E4;}
QFrame#mediaCard[previewActive="true"] {background:#183241;border:1px solid #C2F8E4;}
QPushButton {background:rgba(101,131,153,28);border:1px solid rgba(225,245,255,45);border-radius:18px;padding:11px 22px;font-weight:600;}
QPushButton:hover,QPushButton:focus {background:rgba(147,209,205,65);border:1px solid #C2F8E4;}
QPushButton:checked {background:rgba(174,225,220,45);color:#C6F9E8;border:1px solid #A6D8D4;}
QPushButton#primary {background:#C7F8E5;color:#10272C;border:1px solid #D8FFF0;}
QPushButton:disabled {color:#72869c;}
QLineEdit {background:rgba(62,83,108,100);border:1px solid rgba(224,250,255,65);border-radius:16px;padding:12px 18px;selection-background-color:#4A827D;}
QComboBox {background:rgba(62,83,108,100);border:1px solid rgba(224,250,255,65);border-radius:21px;min-height:18px;padding:11px 46px 11px 18px;selection-background-color:#4A827D;}
QComboBox::drop-down {subcontrol-origin:padding;subcontrol-position:center right;width:36px;border:0;margin-right:7px;}
QComboBox::down-arrow {image:url("__CHEVRON__");width:12px;height:8px;}
QPushButton::menu-indicator {image:url("__CHEVRON__");width:12px;height:8px;subcontrol-origin:padding;subcontrol-position:center right;right:14px;}
QComboBox QAbstractItemView {background:#172A3D;color:white;selection-background-color:#3F6368;}
QScrollArea {border:0;background:transparent;}
QScrollArea > QWidget > QWidget {background:transparent;}
QScrollBar:vertical {width:7px;background:transparent;} QScrollBar::handle:vertical {background:#425A6D;border-radius:3px;min-height:30px;}
QScrollBar:horizontal {height:6px;background:transparent;} QScrollBar::handle:horizontal {background:#425A6D;border-radius:3px;}
QScrollBar::add-line,QScrollBar::sub-line {width:0;height:0;}
QMenu {background:#132838;color:#F1F7FF;border:1px solid #54717F;border-radius:12px;padding:6px;}
QMenu::item {padding:10px 18px;border-radius:6px;}
QMenu::item:selected {background:#315758;}
QMenu::item:disabled {color:#72869c;}
QToolTip {background:#213B4B;color:white;border:1px solid #789893;padding:8px;}
QSlider::groove:horizontal {height:5px;background:#3D5366;border-radius:2px;} QSlider::handle:horizontal {background:#CCF9E8;width:14px;margin:-5px 0;border-radius:7px;}
'''.replace('__CHEVRON__', (ROOT / 'chevron.svg').as_posix())

class Signals(QObject):
    done = pyqtSignal(object, object, object, int)

class Ambient(QWidget):
    def __init__(self):
        super().__init__()
        self.art = None
    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor('#0A1422'))
        for x,y,r,color in ((.05,.4,.9,'#163C49'),(.9,.2,.75,'#302A51'),(.6,1,.7,'#143C3D')):
            grad = QRadialGradient(self.width()*x,self.height()*y,self.width()*r)
            grad.setColorAt(0,QColor(color));grad.setColorAt(1,QColor(10,20,34,0))
            p.fillRect(self.rect(),grad)
        if self.art:
            art=self.art.scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
            p.setOpacity(.6);p.drawPixmap((self.width()-art.width())//2,0,art);p.setOpacity(1)
            grad=QLinearGradient(0,0,self.width(),self.height())
            grad.setColorAt(0,QColor(7,20,32,245));grad.setColorAt(.55,QColor(7,20,32,170));grad.setColorAt(1,QColor(7,20,32,235));p.fillRect(self.rect(),grad)

def label(text,size=14,color='#F1F7FF',bold=False):
    v=QLabel(text);v.setWordWrap(True)
    v.setStyleSheet(f'font-size:{size}px;color:{color};font-weight:{600 if bold else 400};background:transparent;border:0;')
    v.setTextFormat(Qt.TextFormat.PlainText)
    return v

def button(text, callback, primary=False):
    b=QPushButton(text);b.setCursor(Qt.CursorShape.PointingHandCursor)
    if '\n' not in text:b.setFixedHeight(42);b.setStyleSheet('border-radius:21px;padding:0 22px;')
    if primary:b.setObjectName('primary')
    b.clicked.connect(callback)
    return b

def glass():
    f=QFrame();f.setObjectName('glass');return f

class SourceButton(QPushButton):
    """Native keyboard/click handling with width-aware, plain-text source details."""
    padding_x=22
    padding_y=14
    def __init__(self,text,parent=None):
        super().__init__(parent)
        self.source_text=text
        self.setAccessibleName(text)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        policy=QSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True);self.setSizePolicy(policy)
        self.setMinimumWidth(0)
        self.setStyleSheet('border-radius:18px;padding:0;')

    def document(self,width):
        document=QTextDocument();document.setDocumentMargin(0)
        document.setDefaultFont(self.font())
        option=QTextOption();option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        option.setAlignment(Qt.AlignmentFlag.AlignLeft)
        document.setDefaultTextOption(option);document.setPlainText(self.source_text)
        document.setTextWidth(max(1,width-2*self.padding_x))
        return document

    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return math.ceil(self.document(width).size().height())+2*self.padding_y
    def sizeHint(self):return QSize(400,self.heightForWidth(400))
    def minimumSizeHint(self):return QSize(0,self.heightForWidth(400))
    def paintEvent(self,event):
        painter=QPainter(self);option=QStyleOptionButton();self.initStyleOption(option)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton,option,painter,self)
        painter.translate(self.padding_x,self.padding_y)
        document=self.document(self.width())
        # Plain text prevents provider filenames from becoming markup or links.
        painter.setPen(self.palette().buttonText().color())
        context=document.documentLayout().PaintContext()
        context.palette=self.palette()
        document.documentLayout().draw(painter,context)

class SourceDialog(QDialog):
    def __init__(self,streams,select,parent=None):
        super().__init__(parent)
        self.setWindowTitle('Choose your source');self.resize(760,500);self.setMinimumSize(320,260)
        box=QVBoxLayout(self);box.addWidget(label('Choose your source',28,bold=True))
        self.scroll=QScrollArea();self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content=QWidget();items=QVBoxLayout(content);items.setContentsMargins(8,8,8,8);items.setSpacing(8)
        self.options=[]
        for i,stream in enumerate(streams):
            name=str(stream.get('name') or stream.get('provider') or 'Source')
            details=str(stream.get('description') or stream.get('title') or '')
            option=SourceButton(name+('\n'+details if details else ''))
            def chosen(_,index=i):self.accept();select(index)
            option.clicked.connect(chosen);items.addWidget(option);self.options.append(option)
        items.addStretch();self.scroll.setWidget(content);box.addWidget(self.scroll)

class Window(QMainWindow):
    def __init__(self, preview=False, start_live=False):
        super().__init__()
        self.setWindowTitle('Luma TV');self.setWindowIcon(QIcon(str(ROOT/'luma.svg')))
        self.resize(1360,860);self.setMinimumSize(980,700)
        self._update_busy=False;self._update_token='';self._update_dialog=None
        self.client=Client();self.settings=QSettings('Luma','Desktop');self.generation=0
        self.bus=Signals();self.bus.done.connect(self.deliver)
        self.pair_timer=QTimer(self);self.pair_timer.setInterval(2500);self.pair_timer.timeout.connect(self.poll_pair)
        self.player=Player(self);self.player.changed.connect(self.playback_changed);self.player.finished.connect(self.playback_finished);self.player.message.connect(self.notice)
        self.play_title=None;self.play_video='';self.last_position=0;self.watched=0;self.last_sync=0;self.play_key='';self.episode_count=0
        self._record_dialog=None
        self.playback_sync=QTimer(self);self.playback_sync.setInterval(15000);self.playback_sync.timeout.connect(self.sync_progress);self.playback_sync.start()
        self.sleep_timer=QTimer(self);self.sleep_timer.setSingleShot(True);self.sleep_timer.timeout.connect(self.player.pause)
        self.image_cache={};self.tab='Home'
        self._page_serial=0;self._history=[];self._cached_pages={}
        self.stack=QStackedWidget();self.setCentralWidget(self.stack);self.playback_view=None;self.root=None;self.mini_window=None;self.mini_mode=False
        self.statusBar().setStyleSheet('color:#A2B8C9;background:#0A1422;border:0;padding:6px;')
        self.return_player_button=button('↗  Return to player',self.restore_player)
        self.statusBar().addPermanentWidget(self.return_player_button);self.return_player_button.hide()
        QShortcut(QKeySequence('Ctrl+Shift+P'),self,activated=self.toggle_mini_player)
        QShortcut(QKeySequence('F11'),self,activated=lambda:self.showNormal() if self.isFullScreen() else self.showFullScreen())
        QShortcut(QKeySequence('Escape'),self,activated=self.back)
        QShortcut(QKeySequence('Ctrl+F'),self,activated=self.search_page)
        self.page();self.layout.addWidget(label('Opening your cinema…',30),alignment=Qt.AlignmentFlag.AlignCenter)
        if preview:
            self.work(self.client.refresh,lambda _:self.home())
        else:
            self.work(self.client.restore,lambda _:self.home('Live' if start_live else 'Home') if self.client.connected else self.pair(),lambda e:(self.notice('Unlock your desktop keyring to restore your connection, or connect again.'),self.pair()))

    def work(self, func, success=lambda _:None, failure=None, token=None, pool=None):
        token=self.generation if token is None else token
        def run():
            try:result=func();error=None
            except Exception as e:result=None;error=e
            self.bus.done.emit(success,failure,(result,error),token)
        (pool or POOL).submit(run)

    # Keep the actual browse widgets: decoded artwork, pagination, focus and both
    # scroll axes survive a trip through details/playback without another request.
    _page_fields=('generation','root','layout','current','hero','hero_title','hero_meta','hero_desc')

    def page_state(self):
        return {name:getattr(self,name,None) for name in self._page_fields}

    def apply_page_state(self,state):
        for name in self._page_fields:setattr(self,name,state.get(name))

    def clear_browse_cache(self):
        for state in self._history:
            self.stack.removeWidget(state['root']);state['root'].deleteLater()
        self._history.clear();self._cached_pages.clear()

    def leave_page(self,remember=True):
        if getattr(self,'current','')=='Playing' and not self.mini_mode:
            self.sync_progress();self.player.stop();self.play_title=None
        if self.root is not None:
            if remember and getattr(self,'current','') in ('Home','Catalog'):
                state=self.page_state();focus=QApplication.focusWidget()
                state['focus']=focus if focus is not None and self.root.isAncestorOf(focus) else None
                self._history.append(state);self._cached_pages[self.generation]=state
            else:
                self.stack.removeWidget(self.root);self.root.deleteLater()
        self.root=None

    def restore_browse_page(self,section_root=False):
        if not self._history:return False
        self.leave_page(remember=False)
        state=self._history[0] if section_root else self._history[-1]
        while self._history:
            removed=self._history.pop();self._cached_pages.pop(removed['generation'],None)
            if removed is state:break
            self.stack.removeWidget(removed['root']);removed['root'].deleteLater()
        self.apply_page_state(state);self.stack.setCurrentWidget(self.root)
        self.statusBar().show();self.statusBar().clearMessage()
        focus=state.get('focus')
        if focus is not None and not sip.isdeleted(focus):focus.setFocus(Qt.FocusReason.OtherFocusReason)
        return True

    def deliver(self, success, failure, result, token):
        # A hidden cached page can finish loading. Render its results into that
        # page's widgets without moving the user away from the active screen.
        state=self._cached_pages.get(token) if token>=0 and token!=self.generation else None
        if token>=0 and token!=self.generation and state is None:return
        active=self.page_state() if state else None
        if state:self.apply_page_state(state)
        value,error=result
        try:
            if error:
                if failure:failure(error)
                else:self.notice('Couldn’t complete the request. Check your connection and try again.')
            else:success(value)
        except RuntimeError:
            pass  # The owner widget can have been deleted by a screen transition.
        finally:
            if state:
                state.update(self.page_state());self.apply_page_state(active)

    def page(self,remember=True):
        self.leave_page(remember)
        self.statusBar().show()
        self._page_serial+=1;self.generation=self._page_serial
        self.pair_timer.stop();self.pair_code='';self.hero=None
        root=Ambient();self.stack.addWidget(root);self.stack.setCurrentWidget(root);self.root=root
        self.layout=QVBoxLayout(root);self.layout.setContentsMargins(46,28,46,25);self.layout.setSpacing(24)
        return self.layout

    def header(self, nav=False, back=False):
        row=QHBoxLayout();brand=QHBoxLayout();mark=QLabel();mark.setPixmap(QIcon(str(ROOT/'luma.svg')).pixmap(42,42));mark.setFixedSize(42,42);brand.addWidget(mark);brand.addSpacing(5);brand.addWidget(label('luma',30,bold=True));row.addLayout(brand);row.addStretch()
        if nav:
            pane=glass();links=QHBoxLayout(pane);links.setContentsMargins(6,5,6,5);links.setSpacing(3)
            for name in ('Home','Movies','Series','Live','Library'):
                b=button(name,lambda _,n=name:self.home(n));b.setFixedHeight(42);b.setStyleSheet('border-radius:21px;padding:0 22px;');b.setCheckable(True);b.setChecked(name==self.tab);links.addWidget(b)
            row.addWidget(pane);row.addStretch();row.addWidget(button('⌕  Search',self.search_page));row.addWidget(button('⚙',self.settings_page))
        elif back:row.addWidget(button('←  Back',self.back))
        else:
            tagline=label('YOUR STREMIO, REIMAGINED',11,'#ACBED0',True);tagline.setWordWrap(False);tagline.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter);row.addWidget(tagline)
        self.layout.addLayout(row)

    def notice(self, message):
        self.statusBar().showMessage(message,12000)
        if (getattr(self,'current','')=='Playing' or self.mini_mode) and self.playback_view:
            self.playback_view.show_message(message)

    def image(self, url, widget, width=250, height=360, backdrop=False, role='poster',current=None):
        if not url:return
        token=self.generation;owner=self.root
        def apply(data):
            if sip.isdeleted(widget) or (current and not current()):return
            pix=QPixmap();pix.loadFromData(data)
            if pix.isNull():return
            if backdrop:owner.art=pix;owner.update()
            elif isinstance(widget,Artwork):
                {'poster':widget.setPixmap,'preview':widget.setPreview,'logo':widget.setLogo}[role](pix)
            else:widget.setPixmap(pix.scaled(width,height,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        if url in self.image_cache:apply(self.image_cache[url]);return
        def fetch():
            if urlsplit(url).scheme not in ('http','https'):return b''
            with requests.get(url,headers={'User-Agent':UA},timeout=(8,12),stream=True) as r:
                r.raise_for_status();data=bytearray()
                for chunk in r.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>12*1024*1024:raise ValueError('Image too large')
                return bytes(data)
        def done(data):
            if len(self.image_cache)>90:self.image_cache.clear()
            self.image_cache[url]=data;apply(data)
        self.work(fetch,done,lambda _:None,token,pool=POOL if backdrop else IMAGES)

    def pair(self):
        if self.mini_mode:self.stop_playback()
        self.clear_browse_cache();self.page(remember=False);self.current='Connect';self.header()
        body=QHBoxLayout();body.setSpacing(65)
        left=QVBoxLayout();left.addStretch();left.addWidget(label('A LITTLE GLASS. A LOT OF CINEMA.',12,'#C0F4E1',True));left.addSpacing(18)
        left.addWidget(label('Everything you love.\nIn a new light.',52,bold=True));left.addSpacing(18)
        left.addWidget(label('Connect Stremio to bring your library, add-ons\nand continue watching on this desktop.',18,'#AEBED1'));left.addSpacing(30)
        left.addWidget(label('1. Open your phone’s camera\n2. Scan the code and connect Stremio',16,'#D9E8EC'));left.addSpacing(28)
        left.addWidget(button('Explore the interface  →',self.explore),alignment=Qt.AlignmentFlag.AlignLeft);left.addStretch();body.addLayout(left,3)
        panel=glass();panel.setFixedWidth(350);right=QVBoxLayout(panel);right.setContentsMargins(28,26,28,28);right.setSpacing(20)
        qr_heading=label('CONNECT WITH STREMIO',12,'#C0F4E1',True);qr_heading.setWordWrap(False);qr_heading.setFixedSize(290,26);qr_heading.setAlignment(Qt.AlignmentFlag.AlignCenter);right.addWidget(qr_heading)
        self.qr=QLabel();self.qr.setFixedSize(290,290);self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter);self.qr.setStyleSheet('background:#F7FFFB;color:#183241;border-radius:20px;font-size:16px;padding:0;');self.qr.setText('Creating your QR code…');right.addWidget(self.qr)
        self.code_label=label('· · · ·',28,bold=True);self.code_label.setAlignment(Qt.AlignmentFlag.AlignCenter);right.addWidget(self.code_label)
        self.pair_status=label('Creating your connection…',13,'#C0F4E1');self.pair_status.setAlignment(Qt.AlignmentFlag.AlignCenter);right.addWidget(self.pair_status)
        self.new_code_button=button('New code',self.new_code);right.addWidget(self.new_code_button);body.addWidget(panel,1,Qt.AlignmentFlag.AlignVCenter)
        self.layout.addLayout(body,1);self.layout.addWidget(label('Your phone handles sign-in. Or enter the code at link.stremio.com.',12,'#A2B8C9'))
        self.new_code()

    def new_code(self):
        self.pair_timer.stop();self.pair_code='';self.pair_busy=False;self.pair_serial=getattr(self,'pair_serial',0)+1;serial=self.pair_serial
        self.qr.clear();self.qr.setText('Creating your QR code…');self.code_label.setText('· · · ·');self.pair_status.setText('Creating your connection…');self.new_code_button.setEnabled(False)
        def done(value):
            if serial!=self.pair_serial:return
            self.new_code_button.setEnabled(True);self.qr.setText('Enter the code below at\nlink.stremio.com');self.pair_code=value['code'];self.pair_started=time.monotonic();self.code_label.setText(' '.join(self.pair_code.upper()));self.pair_status.setText('●  Waiting for your phone')
            qr=value.get('qrcode','')
            if urlsplit(qr).netloc=='link.stremio.com':self.image(qr,self.qr,290,290,current=lambda:serial==self.pair_serial and bool(self.pair_code))
            self.pair_timer.start()
        def failed(_):
            if serial!=self.pair_serial:return
            self.new_code_button.setEnabled(True);self.qr.setText('Connection unavailable');self.pair_status.setText('Couldn’t connect. Select New code to retry.')
        self.work(self.client.create_link,done,failed)

    def poll_pair(self):
        if self.pair_busy or not self.pair_code:return
        if time.monotonic()-self.pair_started>600:self.pair_timer.stop();self.pair_code='';self.qr.clear();self.qr.setText('Code expired');self.code_label.setText('—');self.pair_status.setText('Select New code to reconnect.');return
        self.pair_busy=True;code=self.pair_code
        def done(key):
            self.pair_busy=False
            if code!=self.pair_code:return
            if key:
                self.pair_timer.stop();self.pair_status.setText('Connected. Bringing your library in…')
                self.work(lambda:self.client.connect(key),lambda _:self.home(),lambda _:self.pair_status.setText('Couldn’t save the connection. Unlock the desktop keyring, then try a new code.'))
        self.work(lambda:self.client.read_link(code),done,lambda _:(setattr(self,'pair_busy',False),self.pair_status.setText('Reconnecting…')))

    def explore(self):
        self.notice('Opening the public catalog…');self.work(self.client.refresh,lambda _:self.home())

    def scroll(self):
        sc=QScrollArea();sc.setWidgetResizable(True);content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(3,6,3,15);box.setSpacing(24);sc.setWidget(content);self.layout.addWidget(sc,1);return box

    def home(self,tab='Home'):
        if tab==self.tab:
            if getattr(self,'current','')=='Home':return
            if self.restore_browse_page(section_root=True):return
        else:
            self.clear_browse_cache()
        self.tab=tab;self.page(remember=False);self.current='Home';self.header(nav=True)
        self.hero_title=label('Live TV & events' if tab=='Live' else 'A world worth getting lost in.',40,bold=True);self.hero_meta=label('YOUR LIVE ADD-ONS' if tab=='Live' else 'YOUR NEXT GREAT WATCH',12,'#C0F4E1',True);self.hero_desc=label('Your channels and live events, together in one place.' if tab=='Live' else 'Your films, series and favourites, together in a different light.',16,'#AEBED1');self.hero_desc.setMaximumWidth(800)
        hero=QVBoxLayout();hero.setSpacing(12);hero.addSpacing(12);hero.addWidget(self.hero_meta);hero.addWidget(self.hero_title);hero.addWidget(self.hero_desc);hero.addSpacing(10);self.layout.addLayout(hero)
        rows=self.scroll()
        def populate(_=None):self.populate_home(tab,rows)
        if tab=='Live' and self.client.connected:
            loading=label('Loading your live channels…',20,'#AEBED1');rows.addWidget(loading)
            def ready(_=None):loading.hide();populate()
            self.work(self.client.refresh_addons,ready,lambda _:(self.notice('Couldn’t refresh add-ons. Showing the saved live catalogs.'),ready()))
        elif not self.client.addons:
            self.work(self.client.refresh,populate)
        else:populate()

    def populate_home(self,tab,rows):
        if tab=='Library':
            if not self.client.connected:rows.addWidget(label('Connect Stremio to see your saved titles.',22));rows.addWidget(button('Connect Stremio',self.pair));return
            self.add_row(rows,'Your library',self.client.library());return
        continuing=self.client.library(True)
        if continuing and tab=='Home':self.add_row(rows,'Continue watching',continuing)
        choices=catalog_choices(self.client.addons,tab)
        if not choices:rows.addWidget(label('No catalogs here yet. Add a compatible provider in Stremio, then refresh in Settings.',20,'#AEBED1'))
        for addon,catalog in choices:
            row_name=catalog.get('name','Catalog')+(' · '+addon.get('manifest',{}).get('name','Live add-on') if tab=='Live' else '')
            section=QWidget();box=QVBoxLayout(section);box.setContentsMargins(0,0,0,0);loading=label(row_name+' · Loading…',18);box.addWidget(loading);rows.addWidget(section)
            def loaded(items,box=box,loading=loading,addon=addon,catalog=catalog):
                loading.hide();self.add_row(box,catalog.get('name',catalog['id'])+' · '+(addon.get('manifest',{}).get('name','Live add-on') if tab=='Live' else 'Series' if catalog.get('type')=='series' else 'Movies' if catalog.get('type')=='movie' else catalog.get('type','')),items,lambda:self.catalog_page(addon,catalog))
                if items and not self.hero:self.set_hero(items[0])
            self.work(lambda a=addon,c=catalog:self.client.catalog(a,c),loaded,lambda _,w=loading,n=row_name:w.setText(n+' · Unavailable. Refresh to try again.'))
        if tab=='Live':
            for addon in self.client.addons:
                manifest=addon.get('manifest',{})
                if set(manifest.get('types') or []) & LIVE_TYPES and not manifest.get('catalogs'):
                    rows.addWidget(label(manifest.get('name','Live add-on')+' · This add-on currently publishes no catalogs. Enable its TV catalogs in the provider’s Stremio configuration, then refresh here.',15,'#AEBED1'))
        rows.addStretch();self.layout.addWidget(label('YOUR STREMIO  ·  '+('Connected as '+self.client.state['name'] if self.client.connected else 'Preview · Connect in Settings')+'                 F11  Fullscreen    Ctrl+F  Search',11,'#91A7BA'))

    def set_hero(self,title):
        self.hero=title;self.hero_title.setText(title.get('name','Untitled'));self.hero_meta.setText((title.get('type','movie').upper())+'   ·   '+str(title.get('releaseInfo','YOUR STREMIO')))
        self.hero_desc.setText(title.get('description','Choose a title, find your source and settle in.')[:300]);self.image(title.get('background',''),self.hero_title,backdrop=True)

    def add_row(self,parent,name,items,more=None):
        top=QHBoxLayout();top.addWidget(label(name,21,bold=True));top.addStretch()
        if more:top.addWidget(button('View all  →',more))
        parent.addLayout(top)
        if not items:parent.addWidget(label('Nothing here yet.',14,'#AEBED1'));return
        parent.addWidget(CardRow([self.poster(title,248 if str(title.get('type','')).lower() in LIVE_TYPES else 144) for title in items[:14]]))

    def poster(self,title,width=144):
        card=MediaCard(title,lambda:self.details(title),width)
        self.image(title.get('poster',''),card.art,width,card.art.height())
        def artwork(meta):
            if sip.isdeleted(card):return
            self.image(meta.get('landscapePoster') or meta.get('background') or meta.get('backdrop'),card.art,role='preview')
            self.image(meta.get('logo'),card.art,role='logo')
        def preview():
            artwork(title)
            if not any(title.get(key) for key in ('landscapePoster','background','backdrop')):
                self.work(lambda:self.client.meta(title),artwork,lambda _:None)
        card.preview_requested.connect(preview)
        return card

    def grid(self,parent,items):
        parent.addWidget(ResponsiveGrid(items,self.poster))

    def catalog_page(self,addon,catalog):
        self.page();self.current='Catalog';self.header(back=True);self.layout.addWidget(label(catalog.get('name','Catalog'),34,bold=True));rows=self.scroll()
        def load(offset=0):
            self.work(lambda:self.client.catalog(addon,catalog,offset),lambda items:render(items,offset))
        def render(items,offset):
            self.grid(rows,items)
            if items and extra(catalog,'skip'):
                more=button('Load more',lambda:(more.hide(),load(offset+len(items))));rows.addWidget(more)
        load()

    def search_page(self):
        self.page();self.current='Search';self.header(back=True);self.layout.addWidget(label('Find your next obsession.',36,bold=True));row=QHBoxLayout();field=QLineEdit();field.setPlaceholderText('Search films and series');row.addWidget(field);row.addWidget(button('Search',lambda:search()));self.layout.addLayout(row);area=self.scroll()
        def search():
            query=field.text().strip()
            if not query:return
            self.search_id=getattr(self,'search_id',0)+1;serial=self.search_id
            while area.count():
                item=area.takeAt(0)
                if item.widget():item.widget().deleteLater()
                elif item.layout():
                    layout=item.layout()
                    while layout.count():
                        child=layout.takeAt(0)
                        if child.widget():child.widget().deleteLater()
            status=label('Searching…',18,'#AEBED1');area.addWidget(status)
            def results(items):
                if serial!=self.search_id:return
                status.setText(f'{len(items)} results for “{query}”');self.grid(area,items[:80])
            self.work(lambda:self.client.search(query),results)
        field.returnPressed.connect(search);field.setFocus()

    def details(self,title,loaded=False):
        self.page();self.current='Details';self.detail=title;self.header(back=True)
        self.image(title.get('background',''),self.root,backdrop=True)
        self.layout.addWidget(label(title.get('type','movie').upper()+'   /   '+str(title.get('releaseInfo','YOUR STREMIO')),12,'#C0F4E1',True))
        self.layout.addWidget(label(title.get('name','Untitled'),44,bold=True))
        self.layout.addWidget(label('   ·   '.join(str(x) for x in [title.get('runtime'),('★ '+str(title['imdbRating'])) if title.get('imdbRating') else None]+title.get('genres',[])[:3] if x),14,'#C0F4E1'))
        description=label(title.get('description','Loading title information…' if not loaded else 'Choose a source to start watching.'),17,'#AEBED1');description.setMaximumWidth(1000);self.layout.addWidget(description)
        videos=sorted(title.get('videos',[]),key=lambda v:(v.get('season',0),v.get('episode',0)))
        ident=title.get('id',title.get('_id'));state=self.client.state['library'].get(ident,{}).get('state',{})
        video=state.get('video_id') or next((v['id'] for v in videos if v.get('season',0)>0 and not future_video(v)),ident)
        actions=QHBoxLayout();actions.addWidget(button('▶  Resume' if self.client.resume(ident,video) else '▶  Watch now',lambda:self.sources(title,video),True));actions.addWidget(button('Choose source',lambda:self.sources(title,video,choose=True)))
        if self.client.connected:
            saved=button('✓  In library' if self.client.saved(ident) else '＋  Library',lambda:self.work(lambda:self.client.toggle(title),lambda yes:saved.setText('✓  In library' if yes else '＋  Library'),pool=WRITES));actions.addWidget(saved)
        actions.addStretch();self.layout.addLayout(actions)
        if videos:
            seasons=sorted({v.get('season',0) for v in videos});selector=QComboBox()
            for season in seasons:selector.addItem(f'Season {season}' if season else 'Specials',season)
            self.layout.addWidget(selector,alignment=Qt.AlignmentFlag.AlignLeft);episodes=self.scroll()
            def populate():
                while episodes.count():
                    item=episodes.takeAt(0)
                    if item.widget():item.widget().deleteLater()
                for v in videos:
                    if v.get('season',0)!=selector.currentData():continue
                    text=f"E{v.get('episode',0)}   {v.get('title',v.get('name','Episode'))}"
                    b=button(text,lambda _,v=v:self.sources(title,v['id'],included=v.get('streams')));b.setEnabled(not future_video(v));episodes.addWidget(b)
                episodes.addStretch()
            selector.currentIndexChanged.connect(populate);selector.setCurrentIndex(seasons.index(1) if 1 in seasons else 0);populate()
        else:self.layout.addStretch();self.layout.addWidget(label('STARRING   '+'  ·  '.join(title.get('cast',[])[:6]),13,'#AEBED1'))
        if not loaded:self.work(lambda:self.client.meta(title),lambda meta:self.details(meta,True))

    def sources(self,title,video,choose=False,included=None):
        if not self.client.connected:self.pair();return
        if title.get('type')=='series' and video==title.get('id'):self.notice('Choose an episode from the list.');return
        self.notice('Finding your sources…')
        def ready(streams):
            if not streams:self.notice('No playable direct streams. Check your streaming add-ons in Stremio.');return
            if choose or self.settings.value('chooseSource',False,type=bool):
                SourceDialog(streams,lambda index:self.play(title,video,streams,index),self).exec()
            else:self.play(title,video,streams,0)
        self.work(lambda:self.client.streams(title,video,included if included is not None else title.get('streams') if video==title.get('id') else None),ready)

    def play(self,title,video,streams,index=0,resume=None):
        if self.mini_mode:self.stop_playback()
        self.page();self.play_title=title;self.play_video=video;self.play_key=self.client.state['key'];self.watched=0;self.last_position=0
        position=self.client.resume(title.get('id',title.get('_id')),video) if resume is None else resume
        try:
            self.player.start(streams,index,position);self.now_playing()
        except Exception:
            self.player.stop();self.play_title=None;self.notice('The embedded player could not start. Check the libmpv installation.')

    def now_playing(self,restoring=False):
        self.current='Playing';self.statusBar().hide()
        if self.playback_view is None:
            self.playback_view=PlaybackView(self.player,self.play_title.get('name',''),self.stop_playback,self.tracks,self.player_sources,self.next_episode,self.sleep_menu,self.toggle_fullscreen,mini=self.enter_mini_player,record=self.toggle_recording)
            self.stack.addWidget(self.playback_view)
            self.playback_view.restore_requested.connect(self.restore_player)
            self.playback_view.stop_requested.connect(self.stop_playback)
        self.playback_view.title.setText(self.play_title.get('name',''))
        self.playback_view.show_message('Playing in Luma' if restoring and not self.player.loading else 'Opening your source…');self.playback_view.show_controls()
        self.stack.setCurrentWidget(self.playback_view)
        self.playback_view.setFocus()

    def toggle_mini_player(self):
        if self.mini_mode:self.restore_player()
        else:self.enter_mini_player()

    def enter_mini_player(self):
        if not self.play_title or not self.playback_view:return
        if self.mini_mode:
            self.mini_window.raise_();return
        if self.isFullScreen():self.showNormal()
        self.mini_mode=True
        self.stack.removeWidget(self.playback_view)
        self.mini_window=MiniPlayer(self.playback_view,self.restore_player,self.stop_playback)
        self.playback_view.set_mini(True)
        area=self.screen().availableGeometry()
        self.mini_window.move(area.right()-self.mini_window.width()-24,area.bottom()-self.mini_window.height()-24)
        self.mini_window.show();self.playback_view.show()
        self.return_player_button.show()
        if not self.restore_browse_page():self.home(self.tab)

    def dock_player(self):
        if not self.mini_mode:return
        mini=self.mini_window;self.mini_window=None;self.mini_mode=False
        mini.layout().removeWidget(self.playback_view)
        self.playback_view.hide();self.playback_view.setParent(self.stack)
        self.stack.addWidget(self.playback_view);self.playback_view.set_mini(False)
        mini.hide();mini.deleteLater();self.return_player_button.hide()

    def restore_player(self):
        if not self.mini_mode:return
        self.page()  # Remember the page browsed while the mini player was open.
        self.dock_player();self.now_playing(restoring=True)
        if self.isMinimized():self.showNormal()
        self.raise_();self.activateWindow()

    def playback_changed(self,position,duration,paused):
        delta=position-self.last_position
        if not paused and 0<delta<3:self.watched+=delta
        self.last_position=position

    def sync_progress(self,ended=False):
        if not self.play_title or not self.play_key:return
        args=(dict(self.play_title),self.play_video,self.player.position,self.player.duration,self.watched,ended);key=self.play_key;self.watched=0
        def save():
            if key==self.client.state.get('key'):self.client.progress(*args)
        WRITES.submit(save)

    def playback_finished(self,ended):
        self.sync_progress(ended)
        if ended and self.play_title and str(self.play_title.get('type','')).lower() in LIVE_TYPES and (self._history or self.mini_mode):
            self.stop_playback();return
        if ended and self.settings.value('autoplay',True,type=bool):self.next_episode(automatic=True)
        else:self.notice('Playback finished.')

    def next_episode(self,automatic=False):
        if not self.play_title:return
        videos=sorted(self.play_title.get('videos',[]),key=lambda v:(v.get('season',0),v.get('episode',0)))
        for i,v in enumerate(videos[:-1]):
            if v['id']==self.play_video:
                next_v=videos[i+1]
                if future_video(next_v):break
                if automatic and self.episode_count>=2:
                    if QMessageBox.question(self,'Still watching?','Your next episode is ready. Keep watching?')!=QMessageBox.StandardButton.Yes:return
                    self.episode_count=0
                self.episode_count+=1;self.sources(self.play_title,next_v['id'],included=next_v.get('streams'));return
        self.notice('You’re all caught up.')

    def tracks(self):
        dialog=QDialog(self);dialog.setWindowTitle('Audio & subtitles');dialog.resize(560,380);box=QVBoxLayout(dialog);box.addWidget(label('Audio & subtitles',26,bold=True))
        for kind,prop,heading in [('audio','aid','Audio track'),('sub','sid','Subtitles')]:
            box.addWidget(label(heading,15,'#C0F4E1',True));choices=QComboBox();choices.addItem('Automatic' if kind=='audio' else 'Off','auto' if kind=='audio' else 'no')
            for track in self.player.tracks:
                if track.get('type')!=kind:continue
                name=track.get('title') or track.get('lang') or f'Track {track["id"]}'
                choices.addItem(name+' · '+str(track.get('codec','')),track['id'])
                if track.get('selected'):choices.setCurrentIndex(choices.count()-1)
            choices.currentIndexChanged.connect(lambda _,c=choices,p=prop:self.player.send('set_property',p,c.currentData()));box.addWidget(choices)
        def found(subtitles):
            for sub in subtitles[:30]:box.addWidget(button(sub.get('lang','Subtitle')+' · '+str(sub.get('id','')),lambda _,s=sub:self.external_subtitle(s)))
        if self.play_title:self.work(lambda:self.client.subtitles(self.play_title,self.play_video),found)
        dialog.exec()

    def external_subtitle(self,sub):
        folder=self.player.folder
        if not folder:return
        path=Path(folder.name)/'subtitle.srt'
        def download():
            # Never reuse video-provider headers for subtitle hosts.
            with requests.get(sub['url'],headers={'User-Agent':UA},timeout=15,stream=True) as r:
                r.raise_for_status();data=bytearray()
                for chunk in r.iter_content(65536):
                    data.extend(chunk)
                    if len(data)>5*1024*1024:raise ValueError('Subtitle too large')
            path.write_bytes(data)
        self.work(download,lambda _:self.player.send('sub-add',str(path),'select'))

    def sleep_menu(self):
        dialog=QDialog(self);dialog.setWindowTitle('Sleep timer');box=QVBoxLayout(dialog)
        for name,minutes in [('Off',0),('In 30 minutes',30),('In 60 minutes',60)]:box.addWidget(button(name,lambda _,m=minutes:(self.sleep_timer.stop(),self.sleep_timer.start(m*60000) if m else None,dialog.accept())))
        dialog.exec()

    def toggle_recording(self):
        if self.player.recording:
            self.player.stop_recording();return
        if self._record_dialog is not None:
            self._record_dialog.raise_();self._record_dialog.activateWindow();return
        if not self.play_title or not self.player.media_loaded:return
        source=self.player.streams
        movies=QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MoviesLocation) or str(Path.home()/'Videos')
        folder=Path(self.settings.value('recordingDirectory',str(Path(movies)/'Luma Recordings')))
        try:folder.mkdir(parents=True,exist_ok=True)
        except OSError:folder=Path.home()
        title=re.sub(r'[^\w\s.()-]','',self.play_title.get('name','Recording')).strip(' .')[:90] or 'Recording'
        while len(title.encode('utf-8'))>160:title=title[:-1]
        name=title+' — '+time.strftime('%Y-%m-%d %H-%M-%S')+'.mkv'
        # Keep Qt's normal event loop rendering video while choosing a file.
        # A native, blocking picker can stall the embedded GL player or appear
        # behind the always-on-top mini player. Own it from the visible player.
        parent=self.playback_view.window() if self.playback_view else self
        dialog=QFileDialog(parent)
        dialog.setOptions(QFileDialog.Option.DontUseNativeDialog|QFileDialog.Option.DontConfirmOverwrite)
        dialog.setStyleSheet('QAbstractItemView {background:#132334;color:#F1F7FF;selection-background-color:#3F6368;selection-color:white;border:1px solid #425A6D;} '
                             'QHeaderView::section {background:#213B4B;color:#F1F7FF;border:0;padding:6px;} '
                             'QToolButton {background:#8BA6B7;color:#10272C;border-radius:6px;padding:4px;} '
                             'QToolButton:hover,QToolButton:checked {background:#C7F8E5;}')
        dialog.setWindowTitle('Save recording');dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile);dialog.setNameFilter('Matroska video (*.mkv)')
        dialog.setDefaultSuffix('mkv');dialog.setDirectory(str(folder));dialog.selectFile(name)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        def selected(chosen):
            if self.player.streams is not source:
                self.player.recording_error.emit('The source changed. Start a new recording.');return
            path=Path(chosen)
            if path.suffix.lower()!='.mkv':path=Path(str(path)+'.mkv')
            if self.player.start_recording(path):self.settings.setValue('recordingDirectory',str(path.parent))
        def finished(_):
            if self._record_dialog is dialog:self._record_dialog=None
        dialog.fileSelected.connect(selected);dialog.finished.connect(finished);dialog.destroyed.connect(finished)
        self._record_dialog=dialog;dialog.open()

    def stop_playback(self):
        if self.mini_mode:
            self.sync_progress();self.player.stop();self.play_title=None;self.dock_player();return
        title=self.play_title
        if self.isFullScreen():self.showNormal()
        self.statusBar().show()
        if self.tab=='Live' and self.restore_browse_page():return
        if title:self.details(title,True)
        else:self.home(self.tab)

    def player_sources(self):
        streams=list(self.player.streams)
        def select(index):
            self.play(self.play_title,self.play_video,streams,index,self.player.position)
        SourceDialog(streams,select,self).exec()

    def toggle_fullscreen(self):
        if self.isFullScreen():self.showNormal()
        else:self.showFullScreen()

    def keyPressEvent(self,event):
        if getattr(self,'current','')=='Playing':
            key=event.key()
            if key==Qt.Key.Key_Space:self.player.pause()
            elif key in (Qt.Key.Key_Left,Qt.Key.Key_Right):self.player.seek(self.player.position+(-10 if key==Qt.Key.Key_Left else 10))
            elif key==Qt.Key.Key_F:self.toggle_fullscreen()
            elif key==Qt.Key.Key_M:self.player.send('cycle','mute')
            elif key==Qt.Key.Key_P:self.enter_mini_player()
            else:return super().keyPressEvent(event)
            self.playback_view.show_controls();event.accept();return
        super().keyPressEvent(event)

    def settings_page(self):
        self.page();self.current='Settings';self.header(back=True);self.layout.addWidget(label('Make yourself at home.',36,bold=True))
        panel=glass();box=QVBoxLayout(panel);box.setContentsMargins(28,25,28,25);box.setSpacing(20)
        box.addWidget(label('YOUR STREMIO',12,'#C0F4E1',True));box.addWidget(label(self.client.state['name'] if self.client.connected else 'A cinema with your name on it.',26,bold=True));box.addWidget(label(f'{len(self.client.addons)} add-ons · Library sync enabled' if self.client.connected else 'Scan a code to connect your library and add-ons.',15,'#AEBED1'))
        box.addWidget(button('Refresh Stremio' if self.client.connected else 'Connect Stremio',lambda:self.refresh_stremio() if self.client.connected else self.pair(),True))
        if self.client.connected:box.addWidget(button('Disconnect this desktop',self.disconnect))
        for key,name,default in [('chooseSource','Always choose a source',False),('autoplay','Play the next episode',True)]:
            enabled=self.settings.value(key,default,type=bool);b=button(name+('  ·  On' if enabled else '  ·  Off'),lambda _,k=key,e=enabled:(self.settings.setValue(k,not e),self.settings_page()));box.addWidget(b)
        box.addWidget(button('Check for app updates',self.check_updates))
        box.addWidget(label('Manage add-ons in Stremio on your phone, then refresh them here.',13,'#AEBED1'));self.layout.addWidget(panel);self.layout.addStretch();platform_name='macOS' if sys.platform=='darwin' else 'Fedora';self.layout.addWidget(label(f'Luma TV for {platform_name}  {VERSION}    ·    F11 fullscreen    ·    Playback powered by mpv',12,'#A2B8C9'))

    def check_updates(self):
        if self._update_dialog is not None:
            self._update_dialog.raise_();self._update_dialog.activateWindow();return
        dialog=QDialog(self);dialog.setWindowTitle('Luma TV updates');dialog.resize(530,240)
        box=QVBoxLayout(dialog);box.addWidget(label('App updates',26,bold=True))
        status=label('Checking GitHub Releases…');box.addWidget(status)
        token=QLineEdit();token.setEchoMode(QLineEdit.EchoMode.Password)
        token.setPlaceholderText('GitHub token · Contents: Read for luma-tv-fedora');token.hide();box.addWidget(token)
        action=button('Checking…',lambda:None,True);action.setEnabled(False);box.addWidget(action)
        box.addWidget(button('Close',dialog.close))
        self._update_dialog=dialog
        dialog.finished.connect(lambda _:setattr(self,'_update_dialog',None))
        def set_action(text,callback):
            action.setText(text);action.setEnabled(True)
            try:action.clicked.disconnect()
            except TypeError:pass
            action.clicked.connect(callback)
        def failed(error):
            self._update_busy=False
            status.setText(str(error) if isinstance(error,updater.UpdateError) else 'Could not complete the update. Check your connection and available disk space, then try again.')
            if isinstance(error,updater.AuthenticationRequired):
                token.show();set_action('Check with token',lambda:check(token.text().strip()))
            else:set_action('Try again',lambda:check(self._update_token))
        def checked(update):
            self._update_busy=False
            if update is None:
                status.setText(f'You’re up to date. Luma TV {VERSION} is installed.');action.hide();return
            status.setText('Luma TV '+update['version']+' is available. Download, verify and restart to install. Your account and preferences will be kept.')
            set_action('Install and restart',lambda:download(update))
        def check(credential=None):
            if self._update_busy:return
            self._update_busy=True;action.setEnabled(False);status.setText('Checking GitHub Releases…')
            def task():
                self._update_token=credential if credential is not None else updater.local_token()
                return updater.check(VERSION,self._update_token)
            self.work(task,checked,failed,token=-1)
        def downloaded(update,result):
            folder,staged=result
            try:
                self.sync_progress();self.player.shutdown()
                updater.install(update['target'],staged)
            except Exception as error:
                failed(error);return
            finally:
                import shutil
                shutil.rmtree(folder,ignore_errors=True)
            self._update_busy=False;dialog.accept();self.close();updater.restart(update['target'])
        def download(update):
            if self._update_busy:return
            if self.player.recording:
                status.setText('Stop and save your recording before installing the update.');return
            self._update_busy=True;action.setEnabled(False);status.setText('Downloading and verifying the update… Luma will restart when ready.')
            self.work(lambda:updater.stage(update,self._update_token),lambda result:downloaded(update,result),failed,token=-1)
        # Keep the callback owner alive until an in-progress operation finishes.
        def finish_close(event):
            if self._update_busy:event.ignore()
            else:QDialog.closeEvent(dialog,event)
        dialog.closeEvent=finish_close
        dialog.reject=lambda:None if self._update_busy else QDialog.reject(dialog)
        dialog.show();check()

    def refresh_stremio(self):
        self.clear_browse_cache()
        self.work(self.client.refresh,lambda _:self.settings_page())

    def disconnect(self):
        if QMessageBox.question(self,'Disconnect Stremio?','Remove this desktop’s saved account connection?')!=QMessageBox.StandardButton.Yes:return
        if self.mini_mode:self.stop_playback()
        self.sync_progress();self.player.stop();self.play_title=None
        self.work(self.client.disconnect,lambda _:self.pair(),pool=WRITES)

    def back(self):
        if self.isFullScreen():self.showNormal()
        elif getattr(self,'current','')=='Playing':self.stop_playback()
        elif self.restore_browse_page():pass
        elif self.client.addons:self.home(self.tab)
        else:self.pair()

    def closeEvent(self,event):
        if self._update_busy:
            event.ignore();self.notice('Wait for the app update to finish before closing Luma.');return
        if self._record_dialog is not None:self._record_dialog.reject()
        self._page_serial+=1;self.generation=self._page_serial;self.clear_browse_cache()
        self.pair_timer.stop();self.sync_progress();self.dock_player();self.player.shutdown();self.playback_sync.stop();event.accept()

def main():
    app=QApplication(sys.argv);app.setApplicationName('tv.luma.Fedora');app.setApplicationDisplayName('Luma TV');app.setDesktopFileName('tv.luma.Fedora');app.setWindowIcon(QIcon(str(ROOT/'luma.svg')));app.setOrganizationName('Luma');app.setStyle('Fusion');app.setStyleSheet(STYLE)
    window=Window('--preview' in sys.argv,'--live' in sys.argv);window.show()
    if '--smoke' in sys.argv:
        def capture():
            window.grab().save(str(ROOT/'artifacts/desktop.png'));window.close();app.quit()
        QTimer.singleShot(12000,capture)
    result=app.exec()
    POOL.shutdown(wait=False,cancel_futures=True)
    IMAGES.shutdown(wait=False,cancel_futures=True)
    WRITES.shutdown(wait=True)
    return result

if __name__=='__main__':
    sys.exit(main())
