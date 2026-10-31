"""Aspect-aware artwork and a grid that follows the available viewport width."""
from PyQt6.QtCore import Qt, QRectF, QSize
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPixmap
from PyQt6.QtWidgets import QLabel, QFrame, QWidget, QVBoxLayout, QGridLayout, QSizePolicy, QLayout
from backend import LIVE_TYPES

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
        self.source = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def setPixmap(self, pixmap):
        self.source = pixmap
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        bounds = QRectF(self.rect())
        clip = QPainterPath();clip.addRoundedRect(bounds,14,14);p.setClipPath(clip)
        p.fillRect(bounds,QColor('#102130'))
        if not self.source.isNull():
            target = fit_rect(self.source.width(),self.source.height(),bounds.adjusted(3,3,-3,-3))
            p.drawPixmap(target,self.source,QRectF(self.source.rect()))
        else:
            p.setPen(QColor('#AABED0'))
            p.drawText(self.rect().adjusted(8,8,-8,-8),Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,self.text())

class MediaCard(QFrame):
    def __init__(self, title, activate, width=144):
        super().__init__()
        self.title = title
        self.activate = activate
        self.setObjectName('mediaCard')
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(title.get('name','Untitled'))
        self.setToolTip(title.get('name','Untitled'))
        box = QVBoxLayout(self);box.setContentsMargins(6,6,6,10);box.setSpacing(9)
        self.art = Artwork(title.get('name',''))
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
        self.setFixedWidth(width)
        self.art.setFixedSize(width-12,round((width-12)/artwork_ratio(self.title)))
        self.setFixedHeight(self.art.height()+65)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activate();event.accept()
        else:super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter,Qt.Key.Key_Space):
            self.activate();event.accept()
        else:super().keyPressEvent(event)

class ResponsiveGrid(QWidget):
    def __init__(self,items,make_card):
        super().__init__()
        self.cards=[make_card(item) for item in items]
        self.wide=any(str(item.get('type','')).lower() in LIVE_TYPES for item in items)
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
            self.grid.addWidget(card,i//columns,i%columns,Qt.AlignmentFlag.AlignTop)
        self.columns=columns
        self.grid.invalidate();self.grid.activate()
        self.setFixedHeight(self.grid.sizeHint().height())
