"""One in-window video surface with glass overlays and keyboard/mouse controls."""
from PyQt6.QtCore import Qt,QTimer,QEvent
from PyQt6.QtWidgets import QWidget,QFrame,QLabel,QPushButton,QSlider,QVBoxLayout,QHBoxLayout,QGridLayout,QApplication
from player import VideoSurface

def clock(seconds):
    seconds=max(0,int(seconds))
    return f'{seconds//3600}:{seconds//60%60:02}:{seconds%60:02}' if seconds>=3600 else f'{seconds//60}:{seconds%60:02}'

class PlaybackView(QWidget):
    def __init__(self,player,title,back,tracks,sources,next_episode,sleep,fullscreen,parent=None):
        super().__init__(parent)
        self.player=player;self.visible_controls=True
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
        self.hide_timer=QTimer(self);self.hide_timer.setSingleShot(True);self.hide_timer.setInterval(4000);self.hide_timer.timeout.connect(self.hide_controls)
        for widget in [self,self.video,self.overlay]+self.overlay.findChildren(QWidget):
            widget.setMouseTracking(True);widget.installEventFilter(self)
        player.changed.connect(self.update_state);player.message.connect(self.show_message);player.buffering.connect(self.set_buffering)
        self.video.failure.connect(self.show_message)
        self.show_controls()

    def update_state(self,position,duration,paused):
        self.position.setText(clock(position));self.total.setText(clock(duration) if duration>0 else 'LIVE')
        self.play_button.setText('▶  Play' if paused else 'Ⅱ  Pause')
        self.seek.setEnabled(duration>0)
        if duration>0 and not self.seek.isSliderDown():self.seek.setValue(min(1000,int(position/duration*1000)))
        if paused:self.show_controls()
        if self.player.streams:
            stream=self.player.streams[self.player.index]
            self.source.setText((stream.get('provider','')+' · '+stream.get('name','Source')).strip(' ·').replace('\n',' ')[:110])

    def show_message(self,message):
        if message=='Playing in Luma':self.status.hide()
        else:self.status.setText(message);self.status.show()

    def set_buffering(self,value):
        if value:self.status.setText('Finding the perfect frame…');self.status.show()
        elif not self.player.loading:self.status.hide()

    def show_controls(self):
        self.visible_controls=True;self.top.show();self.bottom.show();self.setCursor(Qt.CursorShape.ArrowCursor)
        self.hide_timer.start()

    def hide_controls(self):
        if self.player.paused or self.player.loading or QApplication.activeModalWidget():self.hide_timer.start();return
        self.visible_controls=False;self.top.hide();self.bottom.hide();self.setCursor(Qt.CursorShape.BlankCursor)

    def eventFilter(self,obj,event):
        if event.type() in (QEvent.Type.MouseMove,QEvent.Type.KeyPress):self.show_controls()
        if obj in (self.video,self.overlay) and event.type()==QEvent.Type.MouseButtonRelease and event.button()==Qt.MouseButton.LeftButton:
            self.player.pause();self.show_controls();return True
        return super().eventFilter(obj,event)
