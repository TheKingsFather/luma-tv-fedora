"""One in-window video surface with glass overlays and keyboard/mouse controls."""
from PyQt6.QtCore import Qt,QTimer,QEvent,pyqtSignal
from PyQt6.QtWidgets import QWidget,QFrame,QLabel,QPushButton,QSlider,QVBoxLayout,QHBoxLayout,QGridLayout,QApplication,QSizeGrip
from player import VideoSurface

def clock(seconds):
    seconds=max(0,int(seconds))
    return f'{seconds//3600}:{seconds//60%60:02}:{seconds%60:02}' if seconds>=3600 else f'{seconds//60}:{seconds%60:02}'

class DragTitle(QLabel):
    restore=pyqtSignal()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.window().windowHandle():
            self.window().windowHandle().startSystemMove();event.accept()
        else:super().mousePressEvent(event)
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.restore.emit();event.accept()
        else:super().mouseDoubleClickEvent(event)

class MiniPlayer(QWidget):
    """An in-app, resizable always-on-top host for the existing video widget."""
    def __init__(self,view,restore,stop):
        super().__init__(None,Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.restore=restore;self.stop=stop
        self.setWindowTitle('Luma TV · Mini player');self.setMinimumSize(320,220);self.resize(520,320)
        self.setWindowIcon(QApplication.windowIcon())
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.addWidget(view)
    def closeEvent(self,event):
        event.ignore();self.stop()
    def keyPressEvent(self,event):
        key=event.key();player=self.layout().itemAt(0).widget().player
        if key==Qt.Key.Key_Space:player.pause()
        elif key in (Qt.Key.Key_Left,Qt.Key.Key_Right):player.seek(player.position+(-10 if key==Qt.Key.Key_Left else 10))
        elif key==Qt.Key.Key_M:player.send('cycle','mute')
        elif key in (Qt.Key.Key_Escape,Qt.Key.Key_F,Qt.Key.Key_P):self.restore()
        else:return super().keyPressEvent(event)
        event.accept()

class PlaybackView(QWidget):
    restore_requested=pyqtSignal()
    stop_requested=pyqtSignal()
    def __init__(self,player,title,back,tracks,sources,next_episode,sleep,fullscreen,parent=None,mini=None):
        super().__init__(parent)
        self.player=player;self.visible_controls=True;self.mini_mode=False;self.ignore_release=False
        self.setStyleSheet('PlaybackView {background:black;}')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        grid=QGridLayout(self);grid.setContentsMargins(0,0,0,0)
        self.video=VideoSurface(player,self);grid.addWidget(self.video,0,0)
        self.overlay=QWidget(self);grid.addWidget(self.overlay,0,0)
        layout=QVBoxLayout(self.overlay);layout.setContentsMargins(30,25,30,25)
        self.top=QFrame();self.top.setObjectName('glass');top=QHBoxLayout(self.top);top.setContentsMargins(18,14,18,14)
        def b(text,callback,primary=False):
            button=QPushButton(text);button.setCursor(Qt.CursorShape.PointingHandCursor);button.clicked.connect(callback)
            if primary:button.setObjectName('primary')
            return button
        top.addWidget(b('←  Back',back));self.title=QLabel(title);self.title.setStyleSheet('font-size:20px;font-weight:600;');top.addWidget(self.title,1)
        if mini:
            self.mini_button=b('▣  Mini player',mini);top.addWidget(self.mini_button)
        top.addWidget(QLabel('LUMA  /  CINEMA IN A NEW LIGHT'))
        layout.addWidget(self.top)
        layout.addStretch()
        self.status=QLabel('Opening your source…');self.status.setAlignment(Qt.AlignmentFlag.AlignCenter);self.status.setStyleSheet('font-size:18px;color:#C7F8E5;background:rgba(8,20,32,170);border-radius:18px;padding:14px;');layout.addWidget(self.status,alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        self.bottom=QFrame();self.bottom.setObjectName('glass');box=QVBoxLayout(self.bottom);box.setContentsMargins(22,17,22,18);box.setSpacing(14)
        time_row=QHBoxLayout();self.position=QLabel('0:00');self.source=QLabel('Finding the perfect frame…');self.source.setStyleSheet('color:#ACBED0;');self.total=QLabel('LIVE');time_row.addWidget(self.position);time_row.addWidget(self.source,1);time_row.addWidget(self.total);box.addLayout(time_row)
        self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,1000);self.seek.setEnabled(False);self.seek.sliderReleased.connect(lambda:player.seek(player.duration*self.seek.value()/1000));box.addWidget(self.seek)
        self.seek.actionTriggered.connect(lambda _:player.seek(player.duration*self.seek.sliderPosition()/1000) if player.duration>0 else None)
        controls=QHBoxLayout();self.play_button=b('Ⅱ  Pause',player.pause,True);controls.addWidget(b('−10s',lambda:player.seek(player.position-10)));controls.addWidget(self.play_button);controls.addWidget(b('+10s',lambda:player.seek(player.position+10)))
        controls.addSpacing(10);controls.addWidget(b('Audio & subtitles',tracks));controls.addWidget(b('Sources',sources));controls.addWidget(b('Next  →',next_episode));controls.addWidget(b('Sleep',sleep));controls.addStretch()
        controls.addWidget(QLabel('Volume'));self.volume=QSlider(Qt.Orientation.Horizontal);self.volume.setRange(0,100);self.volume.setValue(100);self.volume.setFixedWidth(100);self.volume.valueChanged.connect(lambda value:player.send('set_property','volume',value));controls.addWidget(self.volume)
        controls.addWidget(b('⛶',fullscreen));box.addLayout(controls)
        layout.addWidget(self.bottom)
        self.mini_overlay=QWidget(self);self.mini_overlay.setStyleSheet('QPushButton {padding:5px 10px;border-radius:13px;font-size:12px;} QLabel {font-size:12px;}')
        grid.addWidget(self.mini_overlay,0,0)
        mini_box=QVBoxLayout(self.mini_overlay);mini_box.setContentsMargins(10,10,10,10)
        self.mini_top=QFrame();self.mini_top.setObjectName('glass');mini_top=QHBoxLayout(self.mini_top);mini_top.setContentsMargins(10,6,6,6)
        self.mini_title=DragTitle(title);self.mini_title.setMinimumWidth(0);self.mini_title.restore.connect(self.restore_requested)
        mini_top.addWidget(self.mini_title,1)
        self.restore_button=b('↗',self.restore_requested.emit);self.restore_button.setToolTip('Return to full player (P)');mini_top.addWidget(self.restore_button)
        self.mini_close=b('×',self.stop_requested.emit);self.mini_close.setToolTip('Stop playback');mini_top.addWidget(self.mini_close);mini_box.addWidget(self.mini_top)
        mini_box.addStretch()
        self.mini_status=QLabel();self.mini_status.setWordWrap(True);self.mini_status.setAlignment(Qt.AlignmentFlag.AlignCenter);self.mini_status.setStyleSheet('background:rgba(8,20,32,185);padding:8px;border-radius:10px;color:#C7F8E5;');self.mini_status.hide();mini_box.addWidget(self.mini_status)
        mini_box.addStretch()
        self.mini_bottom=QFrame();self.mini_bottom.setObjectName('glass');mini_controls=QHBoxLayout(self.mini_bottom);mini_controls.setContentsMargins(8,6,6,6)
        mini_controls.addWidget(b('−10s',lambda:player.seek(player.position-10)))
        self.mini_pause=b('Ⅱ',player.pause,True);self.mini_pause.setToolTip('Play / pause (Space)');mini_controls.addWidget(self.mini_pause)
        mini_controls.addWidget(b('+10s',lambda:player.seek(player.position+10)))
        self.mini_mute=b('Mute',lambda:player.send('cycle','mute'));mini_controls.addWidget(self.mini_mute)
        mini_controls.addStretch();mini_controls.addWidget(QSizeGrip(self.mini_overlay));mini_box.addWidget(self.mini_bottom)
        self.mini_overlay.hide()
        self.click_timer=QTimer(self);self.click_timer.setSingleShot(True);self.click_timer.setInterval(QApplication.doubleClickInterval());self.click_timer.timeout.connect(player.pause)
        self.hide_timer=QTimer(self);self.hide_timer.setSingleShot(True);self.hide_timer.setInterval(4000);self.hide_timer.timeout.connect(self.hide_controls)
        for widget in [self,self.video,self.overlay]+self.overlay.findChildren(QWidget)+[self.mini_overlay]+self.mini_overlay.findChildren(QWidget):
            widget.setMouseTracking(True);widget.installEventFilter(self)
        player.changed.connect(self.update_state);player.message.connect(self.show_message);player.buffering.connect(self.set_buffering)
        self.video.failure.connect(self.show_message)
        self.show_controls()

    def update_state(self,position,duration,paused):
        self.position.setText(clock(position));self.total.setText(clock(duration) if duration>0 else 'LIVE')
        self.play_button.setText('▶  Play' if paused else 'Ⅱ  Pause')
        self.mini_pause.setText('▶' if paused else 'Ⅱ')
        self.mini_mute.setText('Unmute' if self.player.muted else 'Mute')
        self.mini_title.setText(self.mini_title.fontMetrics().elidedText(self.title.text(),Qt.TextElideMode.ElideRight,max(40,self.mini_title.width())))
        self.seek.setEnabled(duration>0)
        if duration>0 and not self.seek.isSliderDown():self.seek.setValue(min(1000,int(position/duration*1000)))
        if paused:self.show_controls()
        if self.player.streams:
            stream=self.player.streams[self.player.index]
            self.source.setText((stream.get('provider','')+' · '+stream.get('name','Source')).strip(' ·').replace('\n',' ')[:110])

    def show_message(self,message):
        if message=='Playing in Luma':self.status.hide();self.mini_status.hide()
        else:
            self.status.setText(message);self.status.show()
            self.mini_status.setText(message);self.mini_status.show()

    def set_buffering(self,value):
        if value:self.show_message('Buffering…')
        elif not self.player.loading:self.status.hide();self.mini_status.hide()

    def set_mini(self,value):
        self.click_timer.stop()
        self.mini_mode=value;self.overlay.setVisible(not value);self.mini_overlay.setVisible(value)
        self.show_controls()

    def show_controls(self):
        self.visible_controls=True;self.top.show();self.bottom.show();self.mini_top.show();self.mini_bottom.show();self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hide_timer.start()

    def hide_controls(self):
        if self.player.paused or self.player.loading or QApplication.activeModalWidget():self.hide_timer.start();return
        self.visible_controls=False;self.top.hide();self.bottom.hide();self.mini_top.hide();self.mini_bottom.hide();self.setCursor(Qt.CursorShape.BlankCursor)

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.MouseMove,QEvent.Type.KeyPress):self.show_controls()
        if self.mini_mode and obj in (self.video,self.mini_overlay) and event.type()==QEvent.Type.MouseButtonDblClick:
            self.click_timer.stop();self.ignore_release=True
            self.restore_requested.emit();return True
        if obj in (self.video,self.overlay,self.mini_overlay) and event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
            if self.ignore_release:self.ignore_release=False;return True
            if self.mini_mode:self.click_timer.start()
            elif obj is not self.mini_overlay:self.player.pause()
            self.show_controls();return True
        return super().eventFilter(obj,event)
