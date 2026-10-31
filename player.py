"""In-process libmpv engine and Qt OpenGL rendering. No player subprocess/window."""
import locale
import tempfile
import time
import mpv
from PyQt6.QtCore import QObject,QTimer,pyqtSignal,Qt,QByteArray,QCoreApplication
from PyQt6.QtGui import QOpenGLContext,QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

# Set before QApplication: Qt then preserves a QOpenGLWidget's native context
# when moving it between the main window and picture-in-picture host.
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)

class Player(QObject):
    changed=pyqtSignal(float,float,bool)
    finished=pyqtSignal(bool)
    message=pyqtSignal(str)
    tracks_changed=pyqtSignal(object)
    buffering=pyqtSignal(bool)
    release_surface=pyqtSignal()
    received=pyqtSignal(int,object)
    def __init__(self,parent=None):
        super().__init__(parent)
        self.engine=None;self.folder=None;self.generation=0
        self.streams=[];self.index=0;self.position=self.duration=0.
        self.paused=False;self.resume=0.;self.loading=False;self.headless=False
        self.ready=False;self.tracks=[];self.volume=100.;self.muted=False;self.cache_paused=False
        self.received.connect(self._receive)
        self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.tick)

    def start(self,streams,index=0,resume=0):
        self.stop()
        locale.setlocale(locale.LC_NUMERIC,'C')
        self.streams=list(streams);self.index=index;self.resume=resume
        self.position=self.duration=0.;self.paused=False;self.loading=False
        self.folder=tempfile.TemporaryDirectory(prefix='luma-subtitles-')
        if self.engine is None:
            self.ready=self.headless
            options=dict(vo='null' if self.headless else 'libmpv',osc=False,input_default_bindings=False,
                         input_vo_keyboard=False,terminal=False,config=False,idle=True,keep_open=False,
                         hwdec='auto-safe',ytdl=False,network_timeout=15)
            if self.headless:options['ao']='null'
            self.engine=mpv.MPV(**options)
            epoch=self.generation
            for name in ('time-pos','duration','pause','track-list','paused-for-cache','volume','mute'):
                self.engine.observe_property(name,lambda prop,value,e=epoch:self.received.emit(e,{'event':'property-change','name':prop,'data':value}))
            @self.engine.event_callback('file-loaded','end-file')
            def event(ev):
                if ev.event_id.value==mpv.MpvEventID.FILE_LOADED:
                    self.received.emit(epoch,{'event':'file-loaded'})
                elif ev.event_id.value==mpv.MpvEventID.END_FILE:
                    self.received.emit(epoch,{'event':'end-file','reason':ev.data.reason})
            self._event_handler=event
        self.deadline=time.monotonic()+35;self.timer.start()
        if self.ready:self.load()

    def surface_ready(self):
        if self.engine and not self.ready:
            self.ready=True
            QTimer.singleShot(0,self.load)

    def send(self,*command):
        if not self.engine:return
        try:
            if command[0]=='set_property':self.engine[command[1]]=command[2]
            else:self.engine.command(*command)
        except (ValueError,RuntimeError,mpv.ShutdownError):
            self.message.emit('That playback action is not available for this source.')

    def load(self):
        if not self.engine or not self.ready or not self.streams:return
        stream=self.streams[self.index]
        headers=stream.get('behaviorHints',{}).get('proxyHeaders',{}).get('request',{})
        fields=[f'{k}: {v}' for k,v in headers.items() if '\n' not in str(k)+str(v) and '\r' not in str(k)+str(v)]
        self.send('set_property','http-header-fields',fields)
        self.send('set_property','pause',False)
        self.send('loadfile',stream['url'],'replace')
        self.loading=True;self.deadline=time.monotonic()+35
        self.buffering.emit(True)
        self.message.emit('Opening '+stream.get('name',stream.get('provider','your source')))

    def tick(self):
        if self.loading and time.monotonic()>self.deadline:self.failover()
        if not self.ready and time.monotonic()>self.deadline:
            self.timer.stop();self.message.emit('Could not initialize the embedded video renderer. Check your graphics driver.')

    def _receive(self,epoch,event):
        if epoch!=self.generation or self.engine is None or not self.streams:return
        if event['event']=='property-change':
            name,value=event['name'],event.get('data')
            if name=='time-pos' and isinstance(value,(int,float)):self.position=float(value)
            elif name=='duration' and isinstance(value,(int,float)):self.duration=float(value)
            elif name=='pause':self.paused=bool(value)
            elif name=='mute':self.muted=bool(value)
            elif name=='track-list':self.tracks=value or [];self.tracks_changed.emit(self.tracks)
            elif name=='paused-for-cache':self.cache_paused=bool(value);self.buffering.emit(self.cache_paused or self.loading)
            elif name=='volume' and isinstance(value,(int,float)):self.volume=float(value)
            self.changed.emit(self.position,self.duration,self.paused)
        elif event['event']=='file-loaded':
            self.loading=False
            if self.resume:self.seek(self.resume);self.resume=0
            self.buffering.emit(False);self.message.emit('Playing in Luma')
        elif event['event']=='end-file':
            if event['reason']==mpv.MpvEventEndFile.ERROR:self.failover()
            elif event['reason']==mpv.MpvEventEndFile.EOF:self.finished.emit(True)

    def failover(self):
        self.loading=False
        if self.index+1<len(self.streams):
            self.index+=1;self.resume=self.position;self.load()
        else:
            self.buffering.emit(False);self.message.emit('No source could play. Choose another source from the title page.')

    def pause(self):self.send('cycle','pause')
    def seek(self,position):self.send('seek',max(0,position),'absolute')
    def stop(self):
        """Unload media while retaining the window's single native render context."""
        self.timer.stop();self.streams=[];self.loading=False;self.tracks=[]
        self.send('stop')
        if self.folder:self.folder.cleanup();self.folder=None
        self.buffering.emit(False)

    def shutdown(self):
        """Dispose the render context before terminating libmpv at app close."""
        self.stop();self.generation+=1
        if self.engine:
            self.release_surface.emit()
            engine=self.engine;self.engine=None
            engine.terminate()
        self.ready=False

class VideoSurface(QOpenGLWidget):
    frame_ready=pyqtSignal()
    failure=pyqtSignal(str)
    def __init__(self,player,parent=None):
        super().__init__(parent)
        self.player=player;self.render_context=None;self.frames=0
        fmt=QSurfaceFormat();fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile);fmt.setSwapInterval(1);self.setFormat(fmt)
        self.frame_ready.connect(self._update_frame,Qt.ConnectionType.QueuedConnection)
        self.player.release_surface.connect(self.cleanup)
        self.setMinimumSize(240,135)
        self.setMouseTracking(True)

    def initializeGL(self):
        try:
            def get_address(_,name):
                context=QOpenGLContext.currentContext()
                return int(context.getProcAddress(QByteArray(name))) if context else 0
            self._get_address=mpv.MpvGlGetProcAddressFn(get_address)
            self.render_context=mpv.MpvRenderContext(self.player.engine,'opengl',opengl_init_params={'get_proc_address':self._get_address})
            self.render_context.update_cb=self.frame_ready.emit
            self.context().aboutToBeDestroyed.connect(self.cleanup)
            self.player.surface_ready()
        except Exception:
            self.failure.emit('The embedded renderer could not initialize. Check your OpenGL driver.')

    def _update_frame(self):
        if self.render_context:
            self.render_context.update()
            self.update()

    def paintGL(self):
        if self.render_context:
            ratio=self.devicePixelRatioF()
            self.render_context.render(flip_y=True,opengl_fbo={'fbo':int(self.defaultFramebufferObject()),'w':round(self.width()*ratio),'h':round(self.height()*ratio),'internal_format':0})
            self.frames+=1

    def cleanup(self):
        if self.render_context:
            self.makeCurrent()
            self.render_context.update_cb=None
            self.render_context.free();self.render_context=None
            self.doneCurrent()
