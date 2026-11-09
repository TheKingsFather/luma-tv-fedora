"""Aspect-aware artwork and a grid that follows the available viewport width."""
from PyQt6.QtCore import Qt, QRectF, QSize, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPixmap, QLinearGradient
from PyQt6.QtWidgets import QLabel, QFrame, QWidget, QVBoxLayout, QGridLayout, QSizePolicy, QLayout, QScrollArea, QHBoxLayout
from backend import LIVE_TYPES
from PyQt6 import sip

def artwork_ratio(title):
    if str(title.get('type', '')).lower() in LIVE_TYPES:
        return 16 / 9
    return {'landscape': 16 / 9, 'square': 1, 'poster': 2 / 3}.get(title.get('posterShape'), 2 / 3)

def fit_rect(source_w, source_h, bounds):
    if source_w <= 0 or source_h <= 0:
        return QRectF()
    scale = min(bounds.width() / source_w, bounds.height() / source_h)
    w, h = source_w * scale, source_h * scale
    return QRectF(bounds.center().x()-w/2, bounds.center().y()-h/2, w, h)

class Artwork(QLabel):
    """Paint the complete source inside the frame, never a centre-cropped derivative."""
    def __init__(self, title):
        super().__init__(title)
        self.source = QPixmap();self.preview=QPixmap();self.logo=QPixmap();self.progress=0.;self.metadata=""
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def setPixmap(self, pixmap):
        self.source = pixmap
        self.update()

    def setPreview(self,pixmap):
        self.preview=pixmap.scaled(1280,720,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) if pixmap.width()>1280 or pixmap.height()>720 else pixmap
        self.update()

    def setLogo(self,pixmap):
        self.logo=pixmap.scaled(640,240,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) if pixmap.width()>640 or pixmap.height()>240 else pixmap
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(self.rect())
        clip = QPainterPath();clip.addRoundedRect(bounds,14,14);p.setClipPath(clip)
        p.fillRect(bounds,QColor('#102130'))
        if not self.source.isNull() or (self.progress>0 and not self.preview.isNull()):
            source=self.preview if self.progress>0 and not self.preview.isNull() else self.source
            if source is self.preview:
                scale=max(bounds.width()/source.width(),bounds.height()/source.height())
                target=QRectF(bounds.center().x()-source.width()*scale/2,bounds.center().y()-source.height()*scale/2,source.width()*scale,source.height()*scale)
            else:target=fit_rect(source.width(),source.height(),bounds.adjusted(3,3,-3,-3))
            p.drawPixmap(target,source,QRectF(source.rect()))
        else:
            p.setPen(QColor('#AABED0'))
            p.drawText(self.rect().adjusted(8,8,-8,-8),Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,self.text())
        if self.progress>0:
            p.setOpacity(self.progress)
            gradient=QLinearGradient(0,bounds.height()*.3,0,bounds.height())
            gradient.setColorAt(0,QColor(0,0,0,0));gradient.setColorAt(1,QColor(3,10,19,240))
            p.fillRect(bounds,gradient)
            text_width=max(1,int(bounds.width()-28))
            if not self.logo.isNull():
                target=fit_rect(self.logo.width(),self.logo.height(),QRectF(14,bounds.height()-94,text_width*.82,54))
                p.drawPixmap(target,self.logo,QRectF(self.logo.rect()))
            else:
                font=p.font();font.setPixelSize(18);font.setBold(True);p.setFont(font);p.setPen(QColor('white'))
                text=p.fontMetrics().elidedText(self.text(),Qt.TextElideMode.ElideRight,text_width)
                p.drawText(QRectF(14,bounds.height()-72,text_width,32),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,text)
            font=p.font();font.setPixelSize(11);font.setBold(False);p.setFont(font);p.setPen(QColor('#C7F8E5'))
            p.drawText(QRectF(14,bounds.height()-38,text_width,24),Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(self.metadata,Qt.TextElideMode.ElideRight,text_width))

class MediaCard(QFrame):
    preview_requested=pyqtSignal()
    geometry_changed=pyqtSignal()
    navigation_requested=pyqtSignal(int)
    def __init__(self, title, activate, width=144):
        super().__init__()
        self.title = title
        self._progress=0.;self._hovered=False;self._focused=False;self.preview_target=False;self._requested=False
        self.max_preview_width=10000
        self.delay=QTimer(self);self.delay.setSingleShot(True);self.delay.setInterval(350);self.delay.timeout.connect(self.expand)
        self.animation=QPropertyAnimation(self,b'previewProgress',self);self.animation.setDuration(220);self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.activate = activate
        self.setObjectName('mediaCard')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title.get('name','Untitled'))
        self.setToolTip(title.get('name','Untitled'))
        box = QVBoxLayout(self);box.setContentsMargins(6,6,6,10);box.setSpacing(9)
        self.art = Artwork(title.get('name',''))
        self.art.metadata=' · '.join(str(v) for v in (title.get('releaseInfo'),str(title.get('type','')).title(),title.get('imdbRating')) if v)
        box.addWidget(self.art)
        self.caption = QLabel(title.get('name','Untitled'))
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setWordWrap(True)
        self.caption.setFixedHeight(40)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.caption.setStyleSheet('font-size:12px;font-weight:600;background:transparent;border:0;padding:0 5px;')
        self.caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        box.addWidget(self.caption)
        self.resize_content(width)

    def resize_content(self,width):
        self.base_width=width
        self.art_height=round((width-12)/artwork_ratio(self.title))
        self.setFixedHeight(self.art_height+65)
        self._apply_geometry()

    @pyqtProperty(float)
    def previewProgress(self):return self._progress

    @previewProgress.setter
    def previewProgress(self,value):
        self._progress=value;self._apply_geometry()

    def _apply_geometry(self):
        active=self._progress>0
        if self.property('previewActive')!=active:
            self.setProperty('previewActive',active);self.style().unpolish(self);self.style().polish(self)
        expanded=max(self.base_width,min(self.max_preview_width,round(self.art_height*16/9)+12))
        width=round(self.base_width+(expanded-self.base_width)*self._progress)
        self.setFixedWidth(width);self.art.setFixedSize(width-12,self.art_height)
        self.art.progress=self._progress;self.art.update();self.geometry_changed.emit()

    def _animate(self,active):
        self.preview_target=active;self.animation.stop()
        self.animation.setStartValue(self._progress);self.animation.setEndValue(1. if active else 0.);self.animation.start()

    def expand(self):
        if not (self._hovered or self._focused) or not self.isVisible() or artwork_ratio(self.title)>=1.7:return
        parent=self.parentWidget()
        if parent:
            for other in parent.findChildren(MediaCard,options=Qt.FindChildOption.FindDirectChildrenOnly):
                if other is not self:other.collapse()
        if not self._requested:self._requested=True;self.preview_requested.emit()
        self.raise_();self._animate(True)

    def collapse(self):
        self.delay.stop();self._animate(False)

    def schedule_preview(self):
        parent=self.parentWidget()
        if parent:
            for other in parent.findChildren(MediaCard,options=Qt.FindChildOption.FindDirectChildrenOnly):
                if other is not self:other.collapse()
        self.delay.start()

    def enterEvent(self,event):
        self._hovered=True;self.schedule_preview();super().enterEvent(event)

    def leaveEvent(self,event):
        self._hovered=False
        if not self._focused:self.collapse()
        super().leaveEvent(event)

    def focusInEvent(self,event):
        self._focused=True;self.schedule_preview();super().focusInEvent(event)

    def focusOutEvent(self,event):
        self._focused=False
        if not self._hovered:self.collapse()
        super().focusOutEvent(event)

    def hideEvent(self,event):
        # Qt can deliver hide events while a Python wrapper is being disposed.
        if hasattr(self,'delay') and hasattr(self,'art') and not sip.isdeleted(self.art):
            if not sip.isdeleted(self.delay):self.delay.stop()
            if not sip.isdeleted(self.animation):self.animation.stop()
            self._hovered=self._focused=self.preview_target=False
            self.previewProgress=0.
        super().hideEvent(event)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activate();event.accept()
        else:super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):
            self.activate();event.accept()
        elif event.key() in (Qt.Key.Key_Left,Qt.Key.Key_Right,Qt.Key.Key_Up,Qt.Key.Key_Down):
            self.navigation_requested.emit(event.key());event.accept()
        else:super().keyPressEvent(event)

class CardRow(QScrollArea):
    """A horizontal shelf whose neighbours move with the selected card."""
    def __init__(self,cards):
        super().__init__();self.cards=cards
        self.setWidgetResizable(False);self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content=QWidget();self.box=QHBoxLayout(self.content)
        self.box.setContentsMargins(2,4,2,8);self.box.setSpacing(16)
        for index,card in enumerate(cards):
            self.box.addWidget(card)
            card.geometry_changed.connect(lambda c=card:self.relayout(c))
            card.navigation_requested.connect(lambda key,i=index:self.navigate(i,key))
        self.setFixedHeight(max(card.height() for card in cards)+30)
        self.content.adjustSize();self.setWidget(self.content)

    def relayout(self,card):
        if sip.isdeleted(self) or sip.isdeleted(self.content) or sip.isdeleted(card):return
        self.box.invalidate();self.box.activate();self.content.adjustSize()
        if card.preview_target:self.ensureWidgetVisible(card,16,0)

    def navigate(self,index,key):
        if key in (Qt.Key.Key_Up,Qt.Key.Key_Down):
            rows=[row for row in self.window().findChildren(CardRow) if row.isVisible()]
            if self not in rows:return
            target=rows.index(self)+(-1 if key==Qt.Key.Key_Up else 1)
            if 0<=target<len(rows):
                card=rows[target].cards[min(index,len(rows[target].cards)-1)]
                card.setFocus(Qt.FocusReason.OtherFocusReason)
                parent=card.parentWidget()
                while parent:
                    if isinstance(parent,QScrollArea):parent.ensureWidgetVisible(card,16,16)
                    parent=parent.parentWidget()
            return
        if key not in (Qt.Key.Key_Left,Qt.Key.Key_Right):return
        target=index+(-1 if key==Qt.Key.Key_Left else 1)
        if 0<=target<len(self.cards):
            card=self.cards[target];card.setFocus(Qt.FocusReason.OtherFocusReason);self.ensureWidgetVisible(card,16,0)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        for card in self.cards:
            card.max_preview_width=max(card.base_width,self.viewport().width()-20)
            if card.preview_target:card._apply_geometry()


class ResponsiveGrid(QWidget):
    def __init__(self,items,make_card):
        super().__init__()
        self.cards=[make_card(item) for item in items]
        self.wide=any(str(item.get('type','')).lower() in LIVE_TYPES for item in items)
        self.slots=[]
        for i,card in enumerate(self.cards):
            card.setParent(self);slot=QWidget(self);slot.lower();slot.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents);self.slots.append(slot)
            card.geometry_changed.connect(lambda c=card:self.place_card(c))
            card.navigation_requested.connect(lambda key,i=i:self.navigate(i,key))
        self.columns=0
        self.last_width=-1
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(18)
        self.grid.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)

    def minimumSizeHint(self):
        return QSize(0,0)

    def sizeHint(self):
        # Do not advertise the previous row's total width as a new minimum.
        return QSize(480,self.height())

    def resizeEvent(self,event):
        super().resizeEvent(event)
        width=self.width()
        if width==self.last_width:return
        self.last_width=width
        columns=max(1,width//((244 if self.wide else 154)+18))
        card_width=max(100,(width-18*(columns-1))//columns)
        while self.grid.count():self.grid.takeAt(0)
        for i,card in enumerate(self.cards):
            card.resize_content(card_width)
            self.slots[i].setFixedSize(card_width,card.height())
            self.grid.addWidget(self.slots[i],i//columns,i%columns,Qt.AlignmentFlag.AlignTop)
        self.columns=columns
        self.grid.invalidate();self.grid.activate()
        self.setFixedHeight(self.grid.sizeHint().height())
        self.grid.activate()
        for card in self.cards:card.max_preview_width=width;card._apply_geometry();self.place_card(card)

    def place_card(self,card):
        if sip.isdeleted(self) or sip.isdeleted(card):return
        if not self.columns:return
        slot=self.slots[self.cards.index(card)]
        if sip.isdeleted(slot):return
        card.move(max(0,min(slot.x(),self.width()-card.width())),slot.y())
        if card.preview_target:card.raise_()

    def navigate(self,index,key):
        step={Qt.Key.Key_Left:-1,Qt.Key.Key_Right:1,Qt.Key.Key_Up:-self.columns,Qt.Key.Key_Down:self.columns}[key]
        target=index+step
        if 0<=target<len(self.cards):
            card=self.cards[target];card.setFocus(Qt.FocusReason.OtherFocusReason)
            parent=self.parentWidget()
            while parent:
                if hasattr(parent,'ensureWidgetVisible'):parent.ensureWidgetVisible(card,16,16);break
                parent=parent.parentWidget()
