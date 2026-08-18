"""Дорожка плеера: перемотка и выделение фрагмента прямо на ней."""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from .i18n import tr

TRACK_BG = QColor("#232a3a")
TRACK_OUT = QColor("#12151c")      # части ролика вне выделения
SELECTION = QColor("#4c8dff")
SELECTION_FILL = QColor(76, 141, 255, 46)
HANDLE = QColor("#4c8dff")
HANDLE_HOT = QColor("#8fbcff")
PLAYHEAD = QColor("#ff5252")
TEXT = QColor("#868ea4")

HANDLE_W = 8
TRACK_H = 30
LABEL_H = 16
GRAB_PX = 9                        # на таком расстоянии курсор цепляет метку


class TimelineWidget(QWidget):
    """Полоса времени: тянем метки — получаем фрагмент, тянем фон — перематываем."""

    positionMoved = Signal(int)          # перемотка мышью, мс
    rangeChanged = Signal(int, int)      # начало/конец фрагмента, мс
    scrubFinished = Signal()
    previewRequested = Signal(int)       # показать кадр под меткой, пока её тянут
    previewFinished = Signal()           # метку отпустили — вернуться к позиции плеера

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._duration = 0
        self._position = 0
        self._in = 0
        self._out = 0
        self._drag: str | None = None    # in | out | scrub
        self._hover: str | None = None
        self.setMouseTracking(True)
        # Дорожке нужен фокус: пока он в поле ссылки, клавиши I, O и пробел
        # принадлежат тексту, а не плееру.
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(TRACK_H + LABEL_H + 8)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(
            "Тяните синие метки — это начало и конец фрагмента.\n"
            "Клик по дорожке — перемотка. I и O — метки, ← → — шаг 1 с, с Shift — 0,1 с."
        )

    # ------------------------------------------------------------- данные ---
    def duration(self) -> int:
        return self._duration

    def set_duration(self, ms: int) -> None:
        self._duration = max(0, int(ms))
        if not self._out:
            self._out = self._duration
        self._clamp()
        self.update()

    def position(self) -> int:
        return self._position

    def set_position(self, ms: int) -> None:
        self._position = max(0, int(ms))
        self.update()

    def range(self) -> tuple[int, int]:
        return self._in, self._out

    def set_range(self, in_ms: int, out_ms: int) -> None:
        self._in, self._out = int(in_ms), int(out_ms)
        self._clamp()
        self.update()

    def is_dragging(self) -> bool:
        return self._drag is not None

    def _clamp(self) -> None:
        span = self._duration
        if not span:
            return
        self._in = max(0, min(self._in, span))
        self._out = max(0, min(self._out or span, span))
        if self._out < self._in:
            self._in, self._out = self._out, self._in

    # ---------------------------------------------------------- геометрия ---
    def _track_rect(self) -> QRectF:
        return QRectF(HANDLE_W, LABEL_H + 2, max(1, self.width() - 2 * HANDLE_W), TRACK_H)

    def _x_of(self, ms: int) -> float:
        track = self._track_rect()
        if not self._duration:
            return track.left()
        return track.left() + track.width() * (ms / self._duration)

    def _ms_at(self, x: float) -> int:
        track = self._track_rect()
        if not self._duration or track.width() <= 0:
            return 0
        ratio = (x - track.left()) / track.width()
        return int(max(0.0, min(1.0, ratio)) * self._duration)

    def _hit(self, x: float) -> str | None:
        if not self._duration:
            return None
        near_in = abs(x - self._x_of(self._in)) <= GRAB_PX
        near_out = abs(x - self._x_of(self._out)) <= GRAB_PX
        if near_in and near_out:
            # Метки слиплись — берём ту, в сторону которой тянут.
            return "in" if x < self._x_of(self._in) else "out"
        if near_in:
            return "in"
        if near_out:
            return "out"
        return None

    # --------------------------------------------------------------- мышь ---
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or not self._duration:
            return
        x = event.position().x()
        self._drag = self._hit(x) or "scrub"
        self._apply_drag(x)

    def mouseMoveEvent(self, event) -> None:
        x = event.position().x()
        if self._drag:
            self._apply_drag(x)
            return
        hover = self._hit(x)
        if hover != self._hover:
            self._hover = hover
            self.setCursor(Qt.SizeHorCursor if hover else Qt.PointingHandCursor)
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag == "scrub":
            self.scrubFinished.emit()
        elif self._drag in ("in", "out"):
            self.previewFinished.emit()
        self._drag = None
        self.update()

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()

    def _apply_drag(self, x: float) -> None:
        ms = self._ms_at(x)
        if self._drag == "in":
            self._in = min(ms, max(0, self._out - 50))
            self.rangeChanged.emit(self._in, self._out)
            self.previewRequested.emit(self._in)
        elif self._drag == "out":
            self._out = max(ms, min(self._duration, self._in + 50))
            self.rangeChanged.emit(self._in, self._out)
            self.previewRequested.emit(self._out)
        else:
            self._position = ms
            self.positionMoved.emit(ms)
        self.update()

    # ----------------------------------------------------------- отрисовка ---
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = self._track_rect()

        painter.setPen(Qt.NoPen)
        painter.setBrush(TRACK_OUT)
        painter.drawRoundedRect(track, 8, 8)

        if not self._duration:
            painter.setPen(QPen(TEXT.darker(160)))
            painter.drawText(track, Qt.AlignCenter, tr("Видео не загружено"))
            return

        x_in, x_out = self._x_of(self._in), self._x_of(self._out)
        selection = QRectF(x_in, track.top(), max(1.0, x_out - x_in), track.height())
        painter.setBrush(TRACK_BG)
        painter.drawRoundedRect(selection, 7, 7)
        painter.setBrush(SELECTION_FILL)
        painter.drawRoundedRect(selection, 7, 7)
        painter.setPen(QPen(SELECTION, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(selection, 7, 7)

        if self._drag in ("in", "out"):
            self._draw_preview_marker(painter, track)
        self._draw_playhead(painter, track)
        self._draw_handle(painter, x_in, track, "in")
        self._draw_handle(painter, x_out, track, "out")
        self._draw_labels(painter, x_in, x_out)

    def _draw_preview_marker(self, painter: QPainter, track: QRectF) -> None:
        """Пунктир там, где сейчас стоит показанный в плеере кадр."""
        x = self._x_of(self._in if self._drag == "in" else self._out)
        pen = QPen(HANDLE_HOT, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.drawLine(int(x), 0, int(x), int(track.top()))

    def _draw_playhead(self, painter: QPainter, track: QRectF) -> None:
        x = self._x_of(self._position)
        painter.setPen(QPen(PLAYHEAD, 2))
        painter.drawLine(int(x), int(track.top()) - 3, int(x), int(track.bottom()) + 3)

    def _draw_handle(self, painter: QPainter, x: float, track: QRectF, kind: str) -> None:
        active = self._hover == kind or self._drag == kind
        rect = QRectF(x - HANDLE_W / 2, track.top() - 3, HANDLE_W, track.height() + 6)
        painter.setPen(Qt.NoPen)
        painter.setBrush(HANDLE_HOT if active else HANDLE)
        painter.drawRoundedRect(rect, 4, 4)
        # Одна тонкая насечка вместо двух — так метка выглядит спокойнее.
        painter.setPen(QPen(QColor("#0b1220"), 1))
        painter.drawLine(int(x), int(rect.top()) + 9, int(x), int(rect.bottom()) - 9)

    def _draw_labels(self, painter: QPainter, x_in: float, x_out: float) -> None:
        font = QFont("Consolas")
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QPen(TEXT))
        metrics = painter.fontMetrics()
        for x, text, to_left in ((x_in, _tc(self._in), False), (x_out, _tc(self._out), True)):
            width = metrics.horizontalAdvance(text)
            left = x - width - 4 if to_left else x + 4
            left = max(0.0, min(left, self.width() - width))
            painter.drawText(QRectF(left, 0, width, LABEL_H),
                             Qt.AlignVCenter | Qt.AlignLeft, text)


def _tc(ms: int) -> str:
    total = ms / 1000
    hours, rest = divmod(int(total), 3600)
    minutes, seconds = divmod(rest, 60)
    millis = int(round((total - int(total)) * 1000))
    return f"{hours:d}:{minutes:02d}:{seconds:02d}.{millis:03d}"
