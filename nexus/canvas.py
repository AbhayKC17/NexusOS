"""
nexus/canvas.py — Obsidian-style interactive knowledge graph.

Interaction
───────────
  Zoom  : scroll wheel (any direction, no modifier needed)
  Pan   : left-click drag on empty background, OR middle-button drag
  Move  : left-click drag on a node
  Select: left-click on a node
  Open  : double-click on a node

Visuals
───────
  • Dot-grid background
  • Glowing circular nodes — colour-coded by type, radial gradient fill
  • Bezier curved edges with gradient stroke + arrowhead
  • Force-directed spring layout — runs ONCE, then saves all positions so
    the layout never runs again on subsequent startups
"""

import math
import random
from PyQt6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QGraphicsPathItem,
    QMenu,
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QTimer, pyqtSignal, QObject,
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QRadialGradient,
    QPainterPath, QLinearGradient, QFont, QPolygonF,
)

# ── Type → (hex color, icon glyph) ───────────────────────────────────────────
_TYPE = {
    "APP":        ("#0067C0", "⊡"),
    "FUNCTION":   ("#107C10", "ƒ"),
    "FILE_EXCEL": ("#217346", "⊞"),
    "FILE_PDF":   ("#C42B1C", "⊟"),
    "FILE_TEXT":  ("#0078D4", "≡"),
    "FILE_CODE":  ("#0EA5E9", "<>"),
    "FILE_IMAGE": ("#EA580C", "⊕"),
    "NOTE":       ("#6E4FBE", "✎"),
    "API":        ("#9D5D00", "@"),
    "DATA":       ("#0067C0", "⊡"),
    "DOC":        ("#2B579A", "📄"),
    "PPT":        ("#D24726", "📊"),
    "DEFAULT":    ("#6B7280", "○"),
}

_RADIUS  = 26
_GRID    = 30

_CANVAS_BG   = QColor("#F4F4FA")
_GRID_DOT    = QColor(80, 80, 130, 28)
_LABEL_FG    = QColor(30, 30, 50, 210)
_GLOW_ALPHAS = [0.14, 0.22, 0.38]

_ZOOM_MIN = 0.08
_ZOOM_MAX = 6.0


def _type_color(t: str) -> QColor:
    return QColor(_TYPE.get(t, _TYPE["DEFAULT"])[0])


def _type_icon(t: str) -> str:
    return _TYPE.get(t, _TYPE["DEFAULT"])[1]


# ── Signals carrier ───────────────────────────────────────────────────────────

class _Sig(QObject):
    clicked        = pyqtSignal(dict)
    double_clicked = pyqtSignal(dict)
    moved          = pyqtSignal(str, float, float)


# ── Node ──────────────────────────────────────────────────────────────────────

class NodeItem(QGraphicsItem):

    def __init__(self, data: dict):
        super().__init__()
        self.data   = data
        self.sig    = _Sig()
        self._vx    = random.uniform(-0.5, 0.5)
        self._vy    = random.uniform(-0.5, 0.5)
        self._hover = False
        self._sel   = False
        self._pulse = 0.0
        self._edges: list["EdgeItem"] = []

        px = data.get("pos_x", 0) or 0
        py = data.get("pos_y", 0) or 0
        self._has_saved_pos = (px != 0 or py != 0)
        if not self._has_saved_pos:
            px = random.uniform(-280, 280)
            py = random.uniform(-220, 220)
        self.setPos(px, py)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def boundingRect(self) -> QRectF:
        r = _RADIUS + 22
        return QRectF(-r, -r, r * 2, r * 2 + 20)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for e in self._edges:
                e.update_path()
        return super().itemChange(change, value)

    def paint(self, painter: QPainter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = _type_color(self.data.get("type", "DEFAULT"))
        r = _RADIUS * (1.12 if self._hover else 1.0)
        glow_extra = 4 + self._pulse * 6 if self._sel else 0

        for ring_r, alpha in [
            (r + 18 + glow_extra, _GLOW_ALPHAS[0]),
            (r + 11, _GLOW_ALPHAS[1]),
            (r + 5,  _GLOW_ALPHAS[2]),
        ]:
            g = QColor(c)
            g.setAlphaF(min(alpha * (1.5 if self._sel else 1.0), 1.0))
            painter.setBrush(QBrush(g))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(0, 0), ring_r, ring_r)

        if self._sel:
            ring = QColor(255, 255, 255, 80)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(ring, 1.8))
            painter.drawEllipse(QPointF(0, 0), r + 5, r + 5)

        grad = QRadialGradient(QPointF(-r * 0.3, -r * 0.3), r * 1.6)
        grad.setColorAt(0.0, c.lighter(145))
        grad.setColorAt(1.0, c.darker(115))
        painter.setBrush(QBrush(grad))
        painter.setPen(QPen(c.lighter(160), 1.4))
        painter.drawEllipse(QPointF(0, 0), r, r)

        painter.setPen(QPen(QColor(255, 255, 255, 230)))
        painter.setFont(QFont("SF Pro Display", 11, QFont.Weight.Bold))
        painter.drawText(
            QRectF(-r, -r, r * 2, r * 2),
            Qt.AlignmentFlag.AlignCenter,
            _type_icon(self.data.get("type", "DEFAULT")),
        )

        label = (self.data.get("label") or "")[:20]
        painter.setPen(QPen(_LABEL_FG))
        painter.setFont(QFont("SF Pro Display", 9, QFont.Weight.Medium))
        painter.drawText(
            QRectF(-54, r + 4, 108, 16),
            Qt.AlignmentFlag.AlignCenter,
            label,
        )

    def hoverEnterEvent(self, event):
        self._hover = True; self.update(); super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hover = False; self.update(); super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.sig.clicked.emit(self.data)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.sig.double_clicked.emit(self.data)
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        self._has_saved_pos = True
        self.sig.moved.emit(self.data["id"], self.x(), self.y())
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu()
        menu.setStyleSheet(
            "QMenu { background: #FFFFFF; border: 1px solid rgba(0,0,0,0.12); "
            "color: #1A1A1A; border-radius: 8px; padding: 4px; }"
            "QMenu::item { padding: 6px 18px; border-radius: 5px; }"
            "QMenu::item:selected { background: rgba(0,103,192,0.12); color: #0067C0; }"
        )
        menu.addAction("Open in tab").triggered.connect(
            lambda: self.sig.double_clicked.emit(self.data)
        )
        menu.addAction("Connect to…").triggered.connect(
            lambda: self.sig.clicked.emit({**self.data, "_connect_mode": True})
        )
        menu.addSeparator()
        menu.addAction("Delete node").triggered.connect(
            lambda: self.sig.clicked.emit({**self.data, "_delete": True})
        )
        menu.exec(event.screenPos().toPoint())

    def set_selected(self, v: bool):
        self._sel = v; self.update()

    def set_pulse(self, v: float):
        self._pulse = v; self.update()


# ── Edge ──────────────────────────────────────────────────────────────────────

class EdgeItem(QGraphicsPathItem):

    def __init__(self, src: NodeItem, tgt: NodeItem, label: str = ""):
        super().__init__()
        self._src   = src
        self._tgt   = tgt
        self._label = label
        self._hover = False
        self.setZValue(-1)
        self.setAcceptHoverEvents(True)
        self.update_path()

    def update_path(self):
        s = self._src.scenePos()
        t = self._tgt.scenePos()
        p = QPainterPath()
        p.moveTo(s)
        mid_x = (s.x() + t.x()) * 0.5
        p.cubicTo(QPointF(mid_x, s.y()), QPointF(mid_x, t.y()), t)
        self.setPath(p)

    def paint(self, painter: QPainter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        s  = self._src.scenePos()
        t  = self._tgt.scenePos()
        sc = _type_color(self._src.data.get("type", "DEFAULT"))
        tc = _type_color(self._tgt.data.get("type", "DEFAULT"))
        a  = 0.8 if self._hover else 0.45

        grad = QLinearGradient(s, t)
        sc.setAlphaF(a); grad.setColorAt(0, QColor(sc))
        tc.setAlphaF(a); grad.setColorAt(1, QColor(tc))
        pen = QPen(QBrush(grad), 1.8 if self._hover else 1.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self.path())

        pp    = self.path()
        ap    = pp.pointAtPercent(0.96)
        bp    = pp.pointAtPercent(0.88)
        angle = math.atan2(ap.y() - bp.y(), ap.x() - bp.x())
        tip   = pp.pointAtPercent(1.0)
        sz    = 8
        p1    = tip - QPointF(math.cos(angle - 0.42) * sz, math.sin(angle - 0.42) * sz)
        p2    = tip - QPointF(math.cos(angle + 0.42) * sz, math.sin(angle + 0.42) * sz)
        ar    = QColor(tc); ar.setAlphaF(a)
        painter.setBrush(QBrush(ar))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPolygon(QPolygonF([tip, p1, p2]))

        if self._hover and self._label:
            mid = pp.pointAtPercent(0.5)
            painter.setPen(QPen(QColor(30, 30, 60, 180)))
            painter.setFont(QFont("SF Pro Display", 9))
            painter.drawText(
                QRectF(mid.x() - 50, mid.y() - 12, 100, 16),
                Qt.AlignmentFlag.AlignCenter,
                self._label,
            )

    def hoverEnterEvent(self, event):
        self._hover = True; self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False; self.update()


# ── Canvas ────────────────────────────────────────────────────────────────────

class GraphCanvas(QGraphicsView):
    """Interactive force-directed knowledge graph view."""

    node_clicked        = pyqtSignal(dict)
    node_double_clicked = pyqtSignal(dict)
    node_moved          = pyqtSignal(str, float, float)
    background_clicked  = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.setSceneRect(-4000, -4000, 8000, 8000)

        self._nodes: dict[str, NodeItem] = {}
        self._edges: list[EdgeItem]      = []
        self._selected: NodeItem | None  = None
        self._connect_from: str | None   = None

        # Manual pan state
        self._panning   = False
        self._pan_start = QPointF()

        # Force layout timer
        self._layout_timer = QTimer(self)
        self._layout_timer.timeout.connect(self._layout_step)
        self._iter = 0

        # Pulse animation
        self._pulse_timer = QTimer(self)
        self._pulse_phase = 0.0
        self._pulse_timer.timeout.connect(self._pulse_step)
        self._pulse_timer.start(50)

        self._setup_view()

    # ── View setup ────────────────────────────────────────────────────────────

    def _setup_view(self):
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        # NoDrag: we handle pan manually so it doesn't interfere with node moves
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet(f"background: {_CANVAS_BG.name()}; border: none;")

    def drawBackground(self, painter: QPainter, rect):
        painter.fillRect(rect, _CANVAS_BG)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_GRID_DOT))
        l = int(rect.left()  - rect.left()  % _GRID)
        t = int(rect.top()   - rect.top()   % _GRID)
        r = int(rect.right() + _GRID)
        b = int(rect.bottom()+ _GRID)
        for x in range(l, r, _GRID):
            for y in range(t, b, _GRID):
                painter.drawEllipse(QPointF(x, y), 1.1, 1.1)

    # ── Zoom ──────────────────────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            # Try horizontal delta (some trackpads send it this way)
            delta = event.angleDelta().x()
        if delta == 0:
            return

        factor = 1.15 if delta > 0 else 1 / 1.15
        current_scale = self.transform().m11()

        # Clamp zoom
        if factor > 1 and current_scale >= _ZOOM_MAX:
            return
        if factor < 1 and current_scale <= _ZOOM_MIN:
            return

        self.scale(factor, factor)

    # ── Pan (left-click drag on background, or middle-button) ────────────────

    def mousePressEvent(self, event):
        item = self.itemAt(event.pos())

        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and item is None:
            # Click on empty background — start pan
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.background_clicked.emit()
            if self._connect_from:
                self._connect_from = None
            event.accept()
            return

        # Click landed on an item — let Qt/scene handle it (node select / move)
        if item is None:
            self.background_clicked.emit()
            if self._connect_from:
                self._connect_from = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and event.button() in (
            Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton
        ):
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ── Node / edge management ────────────────────────────────────────────────

    def load_graph(self, nodes: list[dict], edges: list[dict]):
        self._scene.clear()
        self._nodes.clear()
        self._edges.clear()
        self._selected = None
        for nd in nodes:
            self._add_node_item(nd)
        for ed in edges:
            self._add_edge_item(ed["src_id"], ed["tgt_id"], ed.get("label", ""))

        # Count how many nodes lack saved positions
        unsaved = sum(
            1 for n in nodes
            if (n.get("pos_x") or 0) == 0 and (n.get("pos_y") or 0) == 0
        )
        if unsaved > 0:
            # Run layout to place unsaved nodes, then persist all positions
            self._restart_layout()

    def add_node(self, data: dict) -> NodeItem:
        item = self._add_node_item(data)
        self._restart_layout()
        return item

    def add_edge_by_ids(self, src_id: str, tgt_id: str, label: str = ""):
        self._add_edge_item(src_id, tgt_id, label)

    def remove_node(self, nid: str):
        item = self._nodes.pop(nid, None)
        if item:
            self._edges = [
                e for e in self._edges
                if e._src.data["id"] != nid and e._tgt.data["id"] != nid
            ]
            self._scene.removeItem(item)

    def _add_node_item(self, data: dict) -> NodeItem:
        item = NodeItem(data)
        item.sig.clicked.connect(self._on_node_click)
        item.sig.double_clicked.connect(self._on_node_dbl)
        item.sig.moved.connect(self.node_moved)
        self._scene.addItem(item)
        self._nodes[data["id"]] = item
        return item

    def _add_edge_item(self, src_id: str, tgt_id: str, label: str = "") -> "EdgeItem | None":
        src = self._nodes.get(src_id)
        tgt = self._nodes.get(tgt_id)
        if not src or not tgt:
            return None
        edge = EdgeItem(src, tgt, label)
        src._edges.append(edge)
        tgt._edges.append(edge)
        self._scene.addItem(edge)
        self._edges.append(edge)
        return edge

    # ── Selection ─────────────────────────────────────────────────────────────

    def _on_node_click(self, data: dict):
        if data.get("_delete"):
            self.remove_node(data["id"])
            from nexus.graph_db import delete_node
            delete_node(data["id"])
            return
        if data.get("_connect_mode"):
            self._connect_from = data["id"]
            return
        if self._connect_from and self._connect_from != data["id"]:
            src_id = self._connect_from
            tgt_id = data["id"]
            self._connect_from = None
            from nexus.graph_db import add_edge
            add_edge(src_id, tgt_id, "")
            self._add_edge_item(src_id, tgt_id, "")
            return
        self._select(data["id"])
        self.node_clicked.emit(data)

    def _on_node_dbl(self, data: dict):
        self.node_double_clicked.emit(data)

    def _select(self, nid: str | None):
        if self._selected:
            self._selected.set_selected(False)
        self._selected = self._nodes.get(nid) if nid else None
        if self._selected:
            self._selected.set_selected(True)

    def deselect(self):
        self._select(None)

    def fit(self):
        """Fit view to all nodes, but never zoom out past 20% scale."""
        if not self._nodes:
            return
        rect = self._scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        # If fitting zoomed out too far, restore a reasonable minimum scale
        if self.transform().m11() < 0.20:
            self.resetTransform()
            self.scale(0.20, 0.20)
            self.centerOn(rect.center())

    # ── Pulse animation ───────────────────────────────────────────────────────

    def _pulse_step(self):
        self._pulse_phase = (self._pulse_phase + 0.08) % (2 * math.pi)
        if self._selected:
            self._selected.set_pulse(0.5 + 0.5 * math.sin(self._pulse_phase))

    # ── Force-directed layout ─────────────────────────────────────────────────

    def _restart_layout(self):
        self._iter = 0
        if not self._layout_timer.isActive():
            self._layout_timer.start(33)

    def _layout_step(self):
        nodes = list(self._nodes.values())
        if not nodes:
            self._layout_timer.stop()
            return

        self._iter += 1
        if self._iter > 400:
            self._layout_timer.stop()
            # Persist all positions to DB so layout never runs again next startup
            self._save_all_positions()
            return

        K_REP = 7500
        K_SPR = 0.05
        REST  = 200
        DAMP  = 0.80
        G_CTR = 0.009
        cool  = max(0.2, 1.0 - self._iter / 400)

        forces: dict[str, list[float]] = {n.data["id"]: [0.0, 0.0] for n in nodes}

        # Repulsion between all node pairs
        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                dx = a.x() - b.x()
                dy = a.y() - b.y()
                d  = max(math.hypot(dx, dy), 1.0)
                f  = K_REP / d / d
                fx, fy = (dx / d) * f, (dy / d) * f
                forces[a.data["id"]][0] += fx
                forces[a.data["id"]][1] += fy
                forces[b.data["id"]][0] -= fx
                forces[b.data["id"]][1] -= fy

        # Spring attraction along edges
        for edge in self._edges:
            a, b = edge._src, edge._tgt
            dx = b.x() - a.x()
            dy = b.y() - a.y()
            d  = max(math.hypot(dx, dy), 1.0)
            f  = K_SPR * (d - REST)
            fx, fy = (dx / d) * f, (dy / d) * f
            forces[a.data["id"]][0] += fx
            forces[a.data["id"]][1] += fy
            forces[b.data["id"]][0] -= fx
            forces[b.data["id"]][1] -= fy

        # Apply forces — skip frozen nodes
        for node in nodes:
            if node._hover or node._has_saved_pos:
                continue
            nid = node.data["id"]
            fx  = forces[nid][0] - node.x() * G_CTR
            fy  = forces[nid][1] - node.y() * G_CTR
            node._vx = (node._vx + fx) * DAMP * cool
            node._vy = (node._vy + fy) * DAMP * cool
            node.setPos(node.x() + node._vx * 0.12,
                        node.y() + node._vy * 0.12)

    def _save_all_positions(self):
        """Persist current positions for ALL nodes so layout won't re-run next startup."""
        try:
            from nexus.graph_db import update_node
            for node in self._nodes.values():
                node._has_saved_pos = True
                update_node(node.data["id"], pos_x=round(node.x(), 1), pos_y=round(node.y(), 1))
        except Exception as e:
            print(f"[Canvas] Position save error: {e}")
