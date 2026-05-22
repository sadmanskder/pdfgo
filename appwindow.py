import sys
import os
import fitz  # PyMuPDF
import urllib.request
import urllib.error
import json

from PyQt6.QtCore import Qt, QTimer, QPoint, QRect, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QFont, QKeySequence, QShortcut, QIcon
from PyQt6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QLineEdit, QPushButton, QFileDialog, QScrollArea, QLabel,
    QComboBox, QSizePolicy, QFrame, QMainWindow, QToolBar, QProgressBar
)

# ── Try qframelesswindow, fall back to plain QMainWindow gracefully ────────────
try:
    from qframelesswindow import FramelessMainWindow
    from qframelesswindow.titlebar import TitleBar
    _HAS_FRAMELESS = True
except Exception:
    _HAS_FRAMELESS = False

API_ENDPOINT = "API_HERE"  # <-- Set your API endpoint URL here

# ── Palette ────────────────────────────────────────────────────────────────────
BG_BASE    = "#1E1E1E"
BG_SURFACE = "#252526"
BG_ITEM    = "#2D2D30"
BORDER     = "#3C3C3C"
ACCENT     = "#007ACC"
TEXT       = "#D4D4D4"
TEXT_DIM   = "#858585"
GREEN      = "#4EC9B0"
RED_ERR    = "#F48771"
TITLEBAR_H = 44        # height of our combined title+toolbar row


# ── Custom title bar (subclass qframelesswindow's TitleBar) ───────────────────
# Layout inside TitleBar.hBoxLayout (left→right):
#   [logo][app_name][sep][toolbar_controls …][stretch already there][min][max][close]
# The stretch is inserted at index 0 by TitleBar; we insert our stuff before it.

class AppTitleBar(TitleBar):
    """VS Code-style title bar with embedded toolbar controls."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(TITLEBAR_H)

        # Zero out the inherited layout margins/spacing so buttons sit flush
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(0)
        self.hBoxLayout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Style the inherited window buttons — height must equal 32px for internal alignment
        for btn in (self.minBtn, self.maxBtn, self.closeBtn):
            btn.setFixedSize(46, 32)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setNormalColor(QColor(180, 180, 180))
            btn.setHoverColor(QColor(255, 255, 255))
            btn.setPressedColor(QColor(255, 255, 255))
            btn.setNormalBackgroundColor(QColor(0, 0, 0, 0))
            btn.setHoverBackgroundColor(QColor(55, 55, 61))
            btn.setPressedBackgroundColor(QColor(70, 70, 78))

        self.closeBtn.setHoverBackgroundColor(QColor(196, 43, 28))
        self.closeBtn.setPressedBackgroundColor(QColor(180, 30, 15))

        # ── Logo + app name (insert at front of hBoxLayout) ──────────────
        left = QWidget()
        left.setStyleSheet("background:transparent;")
        left.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        ll = QHBoxLayout(left)
        ll.setContentsMargins(8, 0, 6, 0)
        ll.setSpacing(6)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(20, 20)
        self.logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_logo()

        self.app_name = QLabel("pdfGo")
        self.app_name.setStyleSheet(
            f"color:{TEXT}; font-size:13px; font-weight:600; letter-spacing:0.5px;")

        vsep = QFrame()
        vsep.setFrameShape(QFrame.Shape.VLine)
        vsep.setFixedHeight(22)
        vsep.setStyleSheet(f"color:{BORDER};")

        ll.addWidget(self.logo_lbl)
        ll.addWidget(self.app_name)
        ll.addWidget(vsep)

        # insert left block before the stretch (which is at index 0)
        self.hBoxLayout.insertWidget(0, left, 0, Qt.AlignmentFlag.AlignVCenter)

        # ── Toolbar controls (inserted after left block, before stretch) ──
        self._tb = QWidget()
        self._tb.setStyleSheet("background:transparent;")
        self._tb.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self._tb_lay = QHBoxLayout(self._tb)
        self._tb_lay.setContentsMargins(4, 0, 4, 0)
        self._tb_lay.setSpacing(4)
        # inserted at index 1 — after left, before stretch
        self.hBoxLayout.insertWidget(1, self._tb, 0, Qt.AlignmentFlag.AlignVCenter)

    def _load_logo(self):
        for p in ["logo/main.logo", "logo/main_white.png", "logo/main.png"]:
            if os.path.exists(p):
                pix = QPixmap(p)
                if not pix.isNull():
                    self.logo_lbl.setPixmap(
                        pix.scaled(18, 18,
                                   Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
                    return
        self.logo_lbl.setText("◉")
        self.logo_lbl.setStyleSheet(f"color:{ACCENT}; font-size:14px;")

    def add_toolbar_widget(self, widget):
        self._tb_lay.addWidget(widget)


# ── TTS Worker ────────────────────────────────────────────────────────────────
class TTSWorker(QThread):
    finished = pyqtSignal()
    error    = pyqtSignal(str)

    def __init__(self, text):
        super().__init__()
        self.text  = text
        self._stop = False

    def stop(self): self._stop = True

    def run(self):
        try:
            import pyttsx3, re
            engine = pyttsx3.init()
            engine.setProperty('rate', 175)
            engine.setProperty('volume', 1.0)
            for s in re.split(r'(?<=[.!?])\s+', self.text.strip()):
                if self._stop: break
                engine.say(s); engine.runAndWait()
            self.finished.emit()
        except ImportError:
            self.error.emit("pyttsx3 not installed.")
        except Exception as e:
            self.error.emit(str(e))


# ── AI Worker ─────────────────────────────────────────────────────────────────
class APIWorker(QThread):
    finished = pyqtSignal(str)
    error    = pyqtSignal(str)

    def __init__(self, action, text, query="", image_b64=""):
        super().__init__()
        self.action = action
        self.text = text
        self.query = query
        self.image_b64 = image_b64

    def run(self):
        try:
            import base64
            payload_data = {
                "action": self.action,
                "b64_text": base64.b64encode(self.text.encode('utf-8')).decode('utf-8'),
                "b64_query": base64.b64encode(self.query.encode('utf-8')).decode('utf-8') if self.query else ""
            }
            if self.image_b64:
                payload_data["b64_image"] = self.image_b64
                
            payload = json.dumps(payload_data).encode('utf-8')
            
            req = urllib.request.Request(
                API_ENDPOINT, 
                data=payload, 
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                }, 
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = response.read().decode('utf-8')
                data = json.loads(res_body)
                if "response" in data:
                    self.finished.emit(data["response"])
                elif "error" in data:
                    self.error.emit(f"[Server Error]: {data['error']}")
                else:
                    self.error.emit("Invalid response format from server.")
        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode('utf-8')
                err_data = json.loads(err_body)
                err_msg = err_data.get("error", e.reason)
                if "details" in err_data and isinstance(err_data["details"], dict):
                    if "error" in err_data["details"] and isinstance(err_data["details"]["error"], dict):
                        err_msg += " - " + str(err_data["details"]["error"].get("message", ""))
            except Exception:
                err_msg = e.reason
            self.error.emit(f"[HTTP {e.code}]: {err_msg}")
        except urllib.error.URLError as e:
            self.error.emit(f"[Network Error]: {e.reason}")
        except Exception as e:
            self.error.emit(f"[Error]: {e}")


# ── Annotation Overlay ────────────────────────────────────────────────────────
class AnnotationOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.mode       = "view"
        self.drawing    = False
        self.last_point = QPoint()
        self.selection_rect = QRect()
        self.drawings   = []
        self.highlights = []
        self.text_notes = []
        self.undo_stack = []
        self.redo_stack = []

    def set_mode(self, mode):
        self.mode = mode
        cursors = {"view": Qt.CursorShape.ArrowCursor, "write": Qt.CursorShape.CrossCursor,
                   "highlight": Qt.CursorShape.CrossCursor, "text": Qt.CursorShape.IBeamCursor,
                   "select": Qt.CursorShape.IBeamCursor}
        self.setCursor(cursors.get(mode, Qt.CursorShape.ArrowCursor))

    def push_state(self, t, d): self.undo_stack.append((t, d)); self.redo_stack.clear()

    def undo(self):
        if not self.undo_stack: return
        t, d = self.undo_stack.pop(); self.redo_stack.append((t, d))
        if   t == "write"     and d in self.drawings:   self.drawings.remove(d)
        elif t == "highlight" and d in self.highlights: self.highlights.remove(d)
        elif t == "text"      and d in self.text_notes: self.text_notes.remove(d)
        self.update()

    def redo(self):
        if not self.redo_stack: return
        t, d = self.redo_stack.pop(); self.undo_stack.append((t, d))
        if   t == "write":     self.drawings.append(d)
        elif t == "highlight": self.highlights.append(d)
        elif t == "text":      self.text_notes.append(d)
        self.update()

    def rescale_annotations(self, scale):
        for stroke in self.drawings:
            for i in range(len(stroke)):
                stroke[i] = QPoint(int(stroke[i].x()*scale), int(stroke[i].y()*scale))
        for rect in self.highlights:
            rect.setRect(int(rect.left()*scale), int(rect.top()*scale),
                         int(rect.width()*scale), int(rect.height()*scale))
        for note in self.text_notes:
            note["pos"] = QPoint(int(note["pos"].x()*scale), int(note["pos"].y()*scale))
        self.update()

    def mousePressEvent(self, event):
        if self.mode == "view": event.ignore(); return
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.last_point = event.position().toPoint()
            if self.mode == "write":
                s = [self.last_point]; self.drawings.append(s); self.push_state("write", s)
            elif self.mode == "highlight":
                r = QRect(self.last_point, self.last_point)
                self.highlights.append(r); self.push_state("highlight", r)
            elif self.mode == "text":
                n = {"pos": self.last_point, "text": "Type Note Here"}
                self.text_notes.append(n); self.push_state("text", n); self.update()
            elif self.mode == "select":
                self.selection_rect = QRect(self.last_point, self.last_point)
                self.update()

    def mouseMoveEvent(self, event):
        if not self.drawing or self.mode == "view": return
        p = event.position().toPoint()
        if self.mode == "write":       self.drawings[-1].append(p)
        elif self.mode == "highlight": self.highlights[-1] = QRect(self.highlights[-1].topLeft(), p)
        elif self.mode == "select":    self.selection_rect = QRect(self.selection_rect.topLeft(), p).normalized()
        self.last_point = p; self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drawing = False
            if self.mode == "select" and not self.selection_rect.isNull():
                self.parentWidget().extract_text(self.selection_rect)
                self.selection_rect = QRect()
                self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        if self.mode == "select" and not self.selection_rect.isNull():
            painter.setPen(QPen(QColor(0, 120, 215), 1, Qt.PenStyle.SolidLine))
            painter.setBrush(QColor(0, 120, 215, 60))
            painter.drawRect(self.selection_rect)
            
        painter.setPen(QPen(QColor(231, 76, 60), 2, Qt.PenStyle.SolidLine))
        for stroke in self.drawings:
            for i in range(len(stroke)-1): painter.drawLine(stroke[i], stroke[i+1])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(241, 196, 15, 90))
        for rect in self.highlights: painter.drawRect(rect)
        painter.setPen(QColor(44, 62, 80))
        painter.setFont(QFont("Segoe UI", 11))
        for item in self.text_notes: painter.drawText(item["pos"], item["text"])


# ── PDF Page Container ────────────────────────────────────────────────────────
class PDFPageContainer(QWidget):
    def __init__(self, pixmap, page_num, parent=None):
        super().__init__(parent)
        self.page_num = page_num
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        self.img_label = QLabel()
        self.img_label.setPixmap(pixmap)
        layout.addWidget(self.img_label)
        self.overlay = AnnotationOverlay(self)
        self.overlay.setGeometry(0, 10, pixmap.width(), pixmap.height())
        self.overlay.raise_()

    def extract_text(self, rect):
        self.window().extract_text_from_page(self.page_num, rect, self.overlay.width(), self.overlay.height())


# ── Zoom Controller ───────────────────────────────────────────────────────────
class ZoomController:
    def __init__(self, app_ref):
        self.app = app_ref
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._apply_zoom)

    def zoom_by(self, delta):
        self.app.current_zoom = max(0.4, min(4.0, self.app.current_zoom + delta))
        self.app.zoom_label.setText(f"{int(self.app.current_zoom*100)}%")
        self.timer.start(150)  # Debounce: wait 150ms after last click to render

    def _apply_zoom(self):
        self.app._redraw_pages_at_current_zoom()


# ── Choose base class at runtime ──────────────────────────────────────────────
_BaseWindow = FramelessMainWindow if _HAS_FRAMELESS else QMainWindow


class StudyCompanionApp(_BaseWindow):
    def __init__(self):
        super().__init__()

        # Window icon
        for p in ["logo/main.logo", "logo/main_white.png", "logo/main.png"]:
            if os.path.exists(p):
                self.setWindowIcon(QIcon(p)); break

        self.setWindowTitle("pdfGo")
        self.resize(1400, 900)
        
        # Center the window on the screen
        screen = QApplication.primaryScreen()
        if screen:
            geo = self.frameGeometry()
            geo.moveCenter(screen.availableGeometry().center())
            self.move(geo.topLeft())

        # ── State ──────────────────────────────────────────────────────────
        self.doc                   = None
        self.page_widgets          = []
        self.current_visible_page  = -1
        self.api_worker            = None
        self.tts_worker            = None
        self.current_file_path     = ""
        self.current_zoom          = 1.4
        self.is_reading            = False
        self.chat_history          = []
        self._pending_summary_page = -1
        self._ai_panel_visible     = True
        self._splitter_sizes       = [860, 540]   # last known open sizes

        self.scroll_debounce = QTimer()
        self.scroll_debounce.setSingleShot(True)
        self.scroll_debounce.timeout.connect(self.analyze_current_viewport)

        self.zoom_ctrl = ZoomController(self)

        self._build_ui()
        self._setup_shortcuts()
        self._apply_stylesheet()

        # Attach custom title bar (only when frameless lib is present)
        if _HAS_FRAMELESS:
            self._title_bar = AppTitleBar(self)
            self.setTitleBar(self._title_bar)
            self._title_bar.raise_()
            self._populate_titlebar_toolbar()
            # Push central widget down so it isn't hidden under title bar
            self.centralWidget().setContentsMargins(0, TITLEBAR_H, 0, 0)

    # ── Populate title-bar toolbar controls ───────────────────────────────────
    def _populate_titlebar_toolbar(self):
        tb = self._title_bar

        def _btn(label, w=None, h=28, tip=""):
            b = QPushButton(label)
            b.setFixedHeight(h)
            if w: b.setFixedWidth(w)
            if tip: b.setToolTip(tip)
            return b

        def _sep():
            s = QFrame(); s.setFrameShape(QFrame.Shape.VLine)
            s.setFixedHeight(20); s.setStyleSheet(f"color:{BORDER};")
            return s

        def _lbl(t):
            l = QLabel(t); l.setStyleSheet(f"color:{TEXT_DIM}; font-size:12px;")
            return l

        btn_open = _btn("File", tip="Open a PDF file")
        btn_open.clicked.connect(self.open_pdf)
        tb.add_toolbar_widget(btn_open)
        tb.add_toolbar_widget(_sep())

        tb.add_toolbar_widget(_lbl("Page"))
        self.page_input = QLineEdit()
        self.page_input.setFixedSize(38, 26)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.jump_to_entered_page)
        tb.add_toolbar_widget(self.page_input)
        self.total_page_label = _lbl("/ 0")
        tb.add_toolbar_widget(self.total_page_label)
        tb.add_toolbar_widget(_sep())

        btn_zo = _btn("−", w=26, tip="Zoom Out (Ctrl+-)")
        btn_zo.clicked.connect(self.zoom_out)
        tb.add_toolbar_widget(btn_zo)
        self.zoom_label = _lbl(f"{int(self.current_zoom*100)}%")
        self.zoom_label.setFixedWidth(36)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tb.add_toolbar_widget(self.zoom_label)
        btn_zi = _btn("+", w=26, tip="Zoom In (Ctrl+=)")
        btn_zi.clicked.connect(self.zoom_in)
        tb.add_toolbar_widget(btn_zi)
        tb.add_toolbar_widget(_sep())

        self.tool_selector = QComboBox()
        self.tool_selector.setFixedHeight(26)
        self.tool_selector.addItems(["View Mode", "Select Text", "Highlight", "Pen/Write", "Text Note"])
        self.tool_selector.currentIndexChanged.connect(self.change_tool_mode)
        tb.add_toolbar_widget(self.tool_selector)
        tb.add_toolbar_widget(_sep())

        self.btn_read = _btn("Read Aloud", tip="Read page aloud (Ctrl+R)")
        self.btn_read.setObjectName("btn_read")
        self.btn_read.clicked.connect(self.toggle_reading)
        tb.add_toolbar_widget(self.btn_read)
        tb.add_toolbar_widget(_sep())

        # ── Quiz Me button ────────────────────────────────────────────────
        btn_quiz = _btn("Quiz Me", tip="Generate quiz questions from current page (Ctrl+Q)")
        btn_quiz.setObjectName("btn_quiz")
        btn_quiz.clicked.connect(self.quiz_current_page)
        tb.add_toolbar_widget(btn_quiz)
        tb.add_toolbar_widget(_sep())

        # ── AI panel toggle ───────────────────────────────────────────────
        self.btn_ai_toggle = _btn("Hide Ai", tip="Toggle AI panel (Ctrl+\\)")
        self.btn_ai_toggle.setObjectName("btn_ai_toggle")
        self.btn_ai_toggle.clicked.connect(self.toggle_ai_panel)
        tb.add_toolbar_widget(self.btn_ai_toggle)

    # ── Fallback toolbar (when qframelesswindow absent) ───────────────────────
    def _build_fallback_toolbar(self):
        """Called only when frameless lib is unavailable."""
        from PyQt6.QtWidgets import QToolBar
        toolbar = QToolBar(); toolbar.setMovable(False); toolbar.setFixedHeight(TITLEBAR_H)
        self.addToolBar(toolbar)

        def _btn(label, h=28, tip=""):
            b = QPushButton(label); b.setFixedHeight(h)
            if tip: b.setToolTip(tip); return b

        def _lbl(t):
            l = QLabel(t); l.setStyleSheet(f"color:{TEXT_DIM}; font-size:12px;"); return l

        btn_open = _btn("File"); btn_open.clicked.connect(self.open_pdf)
        toolbar.addWidget(btn_open); toolbar.addSeparator()
        toolbar.addWidget(_lbl("Page"))
        self.page_input = QLineEdit(); self.page_input.setFixedSize(38, 26)
        self.page_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_input.returnPressed.connect(self.jump_to_entered_page)
        toolbar.addWidget(self.page_input)
        self.total_page_label = _lbl("/ 0"); toolbar.addWidget(self.total_page_label)
        toolbar.addSeparator()
        btn_zo = _btn("−", tip="Zoom Out"); btn_zo.clicked.connect(self.zoom_out)
        toolbar.addWidget(btn_zo)
        self.zoom_label = _lbl(f"{int(self.current_zoom*100)}%")
        self.zoom_label.setFixedWidth(36); self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.zoom_label)
        btn_zi = _btn("+", tip="Zoom In"); btn_zi.clicked.connect(self.zoom_in)
        toolbar.addWidget(btn_zi); 
        self.tool_selector = QComboBox(); self.tool_selector.setFixedHeight(26)
        self.tool_selector.addItems(["View Mode", "Select Text", "Highlight", "Pen/Write", "Text Note"])
        self.tool_selector.currentIndexChanged.connect(self.change_tool_mode)
        toolbar.addWidget(self.tool_selector)
        self.btn_read = _btn("Read Aloud"); self.btn_read.setObjectName("btn_read")
        self.btn_read.clicked.connect(self.toggle_reading); toolbar.addWidget(self.btn_read)

        btn_quiz = _btn("Quiz Me"); btn_quiz.setObjectName("btn_quiz")
        btn_quiz.clicked.connect(self.quiz_current_page); toolbar.addWidget(btn_quiz)

        self.btn_ai_toggle = _btn("AI"); self.btn_ai_toggle.setObjectName("btn_ai_toggle")
        self.btn_ai_toggle.clicked.connect(self.toggle_ai_panel); toolbar.addWidget(self.btn_ai_toggle)

    # ── Build central UI ──────────────────────────────────────────────────────
    def _build_ui(self):
        if not _HAS_FRAMELESS:
            self._build_fallback_toolbar()

        # ── Main splitter ──
        container = QWidget()
        main_lay  = QVBoxLayout(container)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        self.setCentralWidget(container)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        main_lay.addWidget(self.splitter)

        # ── Left: PDF viewer ──────────────────────────────────────────────
        self.pdf_scroll_area = QScrollArea()
        self.pdf_scroll_area.setWidgetResizable(True)
        self.pdf_container   = QWidget()
        self.pdf_layout      = QVBoxLayout(self.pdf_container)
        self.pdf_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.pdf_scroll_area.setWidget(self.pdf_container)
        self.pdf_scroll_area.verticalScrollBar().valueChanged.connect(self.on_scroll)

        # ── Right: AI Chat ────────────────────────────────────────────────
        self.ai_panel = QWidget()
        self.ai_panel.setObjectName("aiPanel")
        ai_lay = QVBoxLayout(self.ai_panel)
        ai_lay.setContentsMargins(0, 0, 0, 0)
        ai_lay.setSpacing(0)

        # Chat header
        hdr = QWidget(); hdr.setFixedHeight(52); hdr.setObjectName("chatHeader")
        hdr_lay = QHBoxLayout(hdr); hdr_lay.setContentsMargins(14, 0, 14, 0)
        av = QLabel()
        pix = QPixmap("logo/main_white.png")
        if not pix.isNull():
            av.setPixmap(pix.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation))
        av.setFixedSize(34, 34); av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setObjectName("chatAvatar")
        title_blk = QVBoxLayout()
        t_lbl = QLabel("Study with L.U.N.A.R"); t_lbl.setObjectName("chatTitle")
        s_lbl = QLabel("Summaries & answers as you read"); s_lbl.setObjectName("chatSub")
        title_blk.addWidget(t_lbl); title_blk.addWidget(s_lbl); title_blk.setSpacing(1)
        self.status_dot = QLabel(" "); self.status_dot.setObjectName("statusDot")
        self.status_dot.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        self.page_info_lbl = QLabel("")
        self.page_info_lbl.setObjectName("pageInfoLbl")
        self.page_info_lbl.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:10px; background:#1A1A2A;"
            "border-radius:4px; padding:2px 7px;")
        hdr_lay.addWidget(av); hdr_lay.addSpacing(10)
        hdr_lay.addLayout(title_blk); hdr_lay.addStretch()
        hdr_lay.addWidget(self.page_info_lbl)
        hdr_lay.addSpacing(6)
        hdr_lay.addWidget(self.status_dot)

        # Messages scroll area
        self.ai_scroll = QScrollArea()
        self.ai_scroll.setWidgetResizable(True)
        self.ai_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.messages_container = QWidget()
        self.messages_container.setObjectName("msgContainer")
        self.messages_layout = QVBoxLayout(self.messages_container)
        self.messages_layout.setContentsMargins(14, 14, 14, 14)
        self.messages_layout.setSpacing(10)
        self.messages_layout.addStretch()
        self.ai_scroll.setWidget(self.messages_container)
        self._add_system_card("Open a PDF to get started — summaries appear automatically as you scroll.")

        # Typing indicator
        self.typing_widget = QWidget(); self.typing_widget.setObjectName("typingWidget")
        ty_lay = QHBoxLayout(self.typing_widget)
        ty_lay.setContentsMargins(14, 4, 0, 4); ty_lay.setSpacing(8)
        ty_icon = QLabel()
        tpix = QPixmap("logo/main_white.png")
        if not tpix.isNull():
            ty_icon.setPixmap(tpix.scaled(16, 16, Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation))
        self.typing_label = QLabel("Thinking…"); self.typing_label.setObjectName("typingLabel")
        ty_lay.addWidget(ty_icon); ty_lay.addWidget(self.typing_label); ty_lay.addStretch()
        self.typing_widget.hide()

        # Input bar
        input_bar = QWidget(); input_bar.setFixedHeight(68); input_bar.setObjectName("inputBar")
        inp_lay = QHBoxLayout(input_bar)
        inp_lay.setContentsMargins(12, 10, 12, 10); inp_lay.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Ask about this page…")
        self.chat_input.setObjectName("chatInput")
        self.chat_input.returnPressed.connect(self.ask_ai_question)
        btn_send = QPushButton("➤"); btn_send.setObjectName("btnSend")
        btn_send.setFixedSize(38, 38); btn_send.clicked.connect(self.ask_ai_question)
        inp_lay.addWidget(self.chat_input); inp_lay.addWidget(btn_send)

        ai_lay.addWidget(hdr)
        ai_lay.addWidget(self.ai_scroll, 1)
        ai_lay.addWidget(self.typing_widget)
        ai_lay.addWidget(input_bar)

        self.splitter.addWidget(self.pdf_scroll_area)
        self.splitter.addWidget(self.ai_panel)
        self.splitter.setSizes([860, 540])

    # ── Stylesheet ────────────────────────────────────────────────────────────
    def _apply_stylesheet(self):
        self.setStyleSheet(f"""
        QWidget {{
            background: {BG_BASE}; color: {TEXT};
            font-family: 'Segoe UI', 'Arial', sans-serif; font-size: 13px;
        }}
        AppTitleBar {{
            background: {BG_SURFACE}; border-bottom: 1px solid {BORDER};
        }}
        QToolBar {{
            background: {BG_SURFACE}; border-bottom: 1px solid {BORDER};
            spacing: 4px; padding: 0 8px;
        }}
        QSplitter::handle {{ background: {BORDER}; width: 1px; }}

        QPushButton {{
            background: {BG_ITEM}; color: white; font-weight: 700;
            padding: 4px 10px; border-radius: 3px; font-size: 12px;
        }}
        QPushButton:hover {{ background: #383838; border-color: #4B4B4B; }}
        QPushButton:pressed {{ background: {ACCENT}; color: white; border: none; }}
        QPushButton#btn_read {{
            background: transparent; color: white; font-weight: 700;;
        }}
        QPushButton#btn_read:hover {{ background: #1A2E22; }}
        QPushButton#btn_quiz {{
            background: transparent; color: white; font-weight: 700;;
        }}
        QPushButton#btn_quiz:hover {{ background: #2A2210; }}
        QPushButton#btn_quiz:pressed {{ background: #D7BA7D; color: #111; border: none; }}
        QPushButton#btn_ai_toggle {{
            background: transparent; color: white;
            font-weight: 700;
        }}
        QPushButton#btn_ai_toggle:hover {{ background: #0A2030; }}
        QPushButton#btnSend {{
            background: #166534; color: white; border: none;
            border-radius: 19px; font-size: 16px;
        }}
        QPushButton#btnSend:hover {{ background: #1A7A40; }}

        QLineEdit {{
            background: {BG_SURFACE}; border: 1px solid {BORDER}; color: {TEXT};
            padding: 4px 8px; border-radius: 3px; font-size: 12px;
        }}
        QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
        QLineEdit#chatInput {{
            background: #1A1A1A; border: 1px solid #3C3C4E;
            border-radius: 20px; padding: 8px 16px; font-size: 13px;
        }}
        QLineEdit#chatInput:focus {{ border: 1px solid {ACCENT}; }}

        QComboBox {{
            background: {BG_ITEM}; border: 1px solid {BORDER};
            border-radius: 3px; padding: 4px 8px; font-size: 12px;
        }}
        QComboBox:hover {{ background: #383838; }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QComboBox QAbstractItemView {{
            background: {BG_SURFACE}; border: 1px solid {BORDER};
            selection-background-color: {ACCENT}; color: {TEXT};
        }}

        QScrollArea {{ border: none; background: transparent; }}
        QScrollBar:vertical {{
            background: {BG_BASE}; width: 8px; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: #424242; border-radius: 4px; min-height: 28px;
        }}
        QScrollBar::handle:vertical:hover {{ background: #5A5A5A; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ height: 8px; background: {BG_BASE}; }}
        QScrollBar::handle:horizontal {{ background: #424242; border-radius: 4px; }}

        QWidget#aiPanel {{ background: #1A1A1A; }}
        QWidget#chatHeader {{ background: #111111; border-bottom: 1px solid {BORDER}; }}
        QWidget#msgContainer {{ background: transparent; }}
        QLabel#chatTitle {{ color: #E8E8F0; font-size: 13px; font-weight: 700; }}
        QLabel#chatSub   {{ color: {TEXT_DIM}; font-size: 11px; }}
        QLabel#chatAvatar {{ background: #0D1117; border-radius: 17px; padding: 3px; }}
        QLabel#pageInfoLbl {{
            color: {TEXT_DIM}; font-size: 10px;
            background: #1A1A2A; border-radius: 4px; padding: 2px 7px;
        }}
        QWidget#typingWidget {{ background: transparent; }}
        QLabel#typingLabel {{
            color: {ACCENT}; font-size: 12px; font-style: italic; background: transparent;
        }}
        QWidget#inputBar {{ background: #111111; border-top: 1px solid {BORDER}; }}

        QFrame[frameShape="5"] {{
            color: {BORDER}; max-width: 1px; margin: 8px 2px;
        }}
        QLabel {{ background: transparent; }}
        """)

    # ── Shortcuts ─────────────────────────────────────────────────────────────
    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+Z"),       self, self.trigger_undo)
        QShortcut(QKeySequence("Ctrl+Y"),       self, self.trigger_redo)
        QShortcut(QKeySequence("Ctrl+S"),       self, self.save_pdf_overwrite)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self.save_pdf_as)
        QShortcut(QKeySequence("Ctrl+="),       self, self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"),       self, self.zoom_out)
        QShortcut(QKeySequence("Ctrl+R"),       self, self.toggle_reading)
        QShortcut(QKeySequence("Ctrl+Q"),       self, self.quiz_current_page)
        QShortcut(QKeySequence("Ctrl+\\"),      self, self.toggle_ai_panel)

    # ── Zoom ──────────────────────────────────────────────────────────────────
    def zoom_in(self):  self.zoom_ctrl.zoom_by(0.15)
    def zoom_out(self): self.zoom_ctrl.zoom_by(-0.15)

    def _redraw_pages_at_current_zoom(self):
        if not self.doc or not self.page_widgets: return
        self.zoom_label.setText(f"{int(self.current_zoom*100)}%")
        for idx, widget in enumerate(self.page_widgets):
            page = self.doc.load_page(idx)
            mat  = fitz.Matrix(self.current_zoom, self.current_zoom)
            pix  = page.get_pixmap(matrix=mat)
            fmt  = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
            qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
            qpix = QPixmap.fromImage(qimg)
            widget.img_label.setPixmap(qpix)
            widget.setFixedSize(pix.width, pix.height + 20)
            widget.overlay.setGeometry(0, 10, pix.width, pix.height)

    # ── PDF Open ──────────────────────────────────────────────────────────────
    def open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if not file_path: return
        self.current_file_path     = file_path
        self.current_zoom          = 1.4
        self.zoom_label.setText("140%")
        for w in self.page_widgets: w.deleteLater()
        self.page_widgets.clear()
        try:
            self.doc = fitz.open(file_path)
            self.total_page_label.setText(f"/ {len(self.doc)}")
            for pn in range(len(self.doc)):
                page = self.doc.load_page(pn)
                mat  = fitz.Matrix(self.current_zoom, self.current_zoom)
                pix  = page.get_pixmap(matrix=mat)
                fmt  = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                qpix = QPixmap.fromImage(qimg)
                pc   = PDFPageContainer(qpix, pn)
                self.pdf_layout.addWidget(pc); self.page_widgets.append(pc)
            self.scroll_debounce.start(300)
        except Exception as e:
            self._add_system_card(f"Failed to load PDF: {e}")

    # ── Tool Mode ─────────────────────────────────────────────────────────────
    def change_tool_mode(self):
        modes = ["view", "select", "highlight", "write", "text"]
        m = modes[self.tool_selector.currentIndex()]
        for c in self.page_widgets: c.overlay.set_mode(m)

    # ── Scroll / Page tracking ────────────────────────────────────────────────
    def on_scroll(self):
        if self.doc: self.scroll_debounce.start(1500)

    def jump_to_entered_page(self):
        if not self.doc or not self.page_widgets: return
        try:
            t = int(self.page_input.text().strip()) - 1
            if 0 <= t < len(self.page_widgets):
                self.pdf_scroll_area.verticalScrollBar().setValue(
                    self.page_widgets[t].geometry().top())
        except ValueError: pass

    def get_focused_overlay(self):
        if 0 <= self.current_visible_page < len(self.page_widgets):
            return self.page_widgets[self.current_visible_page].overlay
        return None

    def trigger_undo(self):
        ov = self.get_focused_overlay()
        if ov: ov.undo()

    def trigger_redo(self):
        ov = self.get_focused_overlay()
        if ov: ov.redo()

    def analyze_current_viewport(self):
        if not self.doc or not self.page_widgets: return
        vt  = self.pdf_scroll_area.verticalScrollBar().value()
        vh  = self.pdf_scroll_area.viewport().height()
        vc  = vt + vh // 2
        idx = 0
        for i, w in enumerate(self.page_widgets):
            if w.geometry().top() <= vc <= w.geometry().bottom():
                idx = i; break
        self.page_input.setText(str(idx + 1))
        if idx == self.current_visible_page: return
        self.current_visible_page = idx
        
        page = self.doc.load_page(self.current_visible_page)
        text = page.get_text()

        import base64
        pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode('utf-8')

        # ── Reading-time badge ────────────────────────────────────────────
        word_count = len(text.split())
        read_secs  = max(1, word_count // 4)   # ~240 wpm
        if read_secs < 60:
            rt_str = f"{read_secs}s read"
        else:
            rt_str = f"{read_secs//60}m {read_secs%60}s read"
        self.page_info_lbl.setText(f"~{word_count} words · {rt_str}")

        if text.strip() or img_b64:
            self._add_system_card(f"Summarizing page {idx + 1}…")
            self._pending_summary_page = idx + 1
            self.call_cloud_ai("summary", text, image_b64=img_b64)

    # ── AI Chat ───────────────────────────────────────────────────────────────
    def ask_ai_question(self):
        if self.current_visible_page == -1 or not self.doc: return
        query = self.chat_input.text().strip()
        if not query: return
        self.chat_input.clear()
        self._add_user_bubble(query)
        
        page = self.doc.load_page(self.current_visible_page)
        page_text = page.get_text()
        
        import base64
        pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode('utf-8')
        
        self._pending_summary_page = -1
        self.call_cloud_ai("ask", page_text, query, image_b64=img_b64)

    def call_cloud_ai(self, action, text, query="", image_b64=""):
        if self.api_worker and self.api_worker.isRunning(): return
        self.status_dot.setStyleSheet(f"color:{BORDER}; font-size:11px;")
        self.typing_widget.show()
        self._scroll_to_bottom()
        self.api_worker = APIWorker(action, text, query, image_b64)
        self.api_worker.finished.connect(self._on_ai_response)
        self.api_worker.error.connect(self._on_ai_error)
        self.api_worker.start()

    def _on_ai_response(self, text):
        self.typing_widget.hide()
        self.status_dot.setStyleSheet(f"color:{GREEN}; font-size:11px;")
        page_label = self._pending_summary_page
        self._pending_summary_page = -1
        self._add_ai_bubble(text, summary_page=page_label)

    def _on_ai_error(self, err):
        self.typing_widget.hide()
        self.status_dot.setStyleSheet(f"color:{RED_ERR}; font-size:11px;")
        self._add_system_card(f"⚠ {err}")

    # ── Text Extraction ───────────────────────────────────────────────────────
    def extract_text_from_page(self, page_num, rect, w, h):
        if not self.doc: return
        page = self.doc.load_page(page_num)
        sx = page.rect.width / w
        sy = page.rect.height / h
        fitz_rect = fitz.Rect(rect.left() * sx, rect.top() * sy, rect.right() * sx, rect.bottom() * sy)
        text = page.get_textbox(fitz_rect).strip()
        if text:
            QApplication.clipboard().setText(text)
            self._add_system_card(f"📋 Copied text to clipboard.")

    # ── Bubble builders ───────────────────────────────────────────────────────
    def _add_user_bubble(self, text):
        row = QWidget(); row.setStyleSheet("background:transparent;")
        rl  = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0)
        bubble = QLabel(text); bubble.setWordWrap(True); bubble.setMaximumWidth(420)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        bubble.setCursor(Qt.CursorShape.IBeamCursor)
        bubble.setStyleSheet(
            "background:#166534; color:white; border-radius:14px 14px 3px 14px;"
            "padding:9px 13px; font-size:13px;")
        rl.addStretch(); rl.addWidget(bubble)
        self.messages_layout.insertWidget(self.messages_layout.count()-1, row)
        self._scroll_to_bottom()

    def _add_ai_bubble(self, text, summary_page=-1):
        try:
            import markdown; html = markdown.markdown(text)
        except ImportError:
            html = text.replace("\n", "<br>")

        if summary_page > 0:
            html = (
                f"<div style='font-size:10px; font-weight:700; color:{ACCENT}; "
                f"letter-spacing:0.8px; text-transform:uppercase; margin-bottom:7px;'>"
                f"Summary of Page: {summary_page}</div>"
            ) + html

        row = QWidget(); row.setStyleSheet("background:transparent;")
        rl  = QHBoxLayout(row); rl.setContentsMargins(0, 0, 0, 0)
        rl.setAlignment(Qt.AlignmentFlag.AlignLeft)

        av = QLabel()
        pix = QPixmap("logo/main_white.png")
        if not pix.isNull():
            av.setPixmap(pix.scaled(18, 18, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation))
        av.setFixedSize(30, 30); av.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av.setStyleSheet("background:#111111; border-radius:15px; padding:3px;")

        bubble = QLabel(); bubble.setWordWrap(True); bubble.setMaximumWidth(520)
        bubble.setTextFormat(Qt.TextFormat.RichText)
        bubble.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        bubble.setCursor(Qt.CursorShape.IBeamCursor)
        bubble.setText(
            f"<div style='font-family:\"Segoe UI\",sans-serif; font-size:13px;"
            f"line-height:1.6; color:{TEXT};'>{html}</div>")
        bubble.setStyleSheet(
            f"background:{BG_SURFACE}; border:1px solid {BORDER};"
            "border-radius:3px 14px 14px 14px; padding:11px 13px;")

        rl.addWidget(av, alignment=Qt.AlignmentFlag.AlignTop)
        rl.addSpacing(7); rl.addWidget(bubble); rl.addStretch()
        self.messages_layout.insertWidget(self.messages_layout.count()-1, row)

        def _scroll_to_start():
            self.messages_container.adjustSize()
            row_top = row.mapTo(self.messages_container, QPoint(0, 0)).y()
            vp_h    = self.ai_scroll.viewport().height()
            target  = max(0, row_top - int(vp_h * 0.40))
            self.ai_scroll.verticalScrollBar().setValue(target)
        QTimer.singleShot(120, _scroll_to_start)

    def _add_system_card(self, text):
        card = QLabel(text); card.setWordWrap(True)
        card.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-style:italic;"
            "background:transparent; padding:3px 16px;")
        self.messages_layout.insertWidget(self.messages_layout.count()-1, card)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self):
        QTimer.singleShot(70, lambda:
            self.ai_scroll.verticalScrollBar().setValue(
                self.ai_scroll.verticalScrollBar().maximum()))

    # ── TTS ───────────────────────────────────────────────────────────────────
    def toggle_reading(self):
        if self.is_reading: self._stop_reading()
        else:               self._start_reading()

    def _start_reading(self):
        if self.current_visible_page == -1 or not self.doc: return
        text = self.doc.load_page(self.current_visible_page).get_text().strip()
        if not text: self._add_system_card("No readable text on this page."); return
        self.is_reading = True
        self.btn_read.setText("⏹  Stop Reading")
        self.btn_read.setStyleSheet(
            "background:#2A1010; color:#F48771; border:1px solid #4A2020;"
            "border-radius:3px; padding:4px 10px;")
        self._add_system_card(f"Reading page {self.current_visible_page + 1}…")
        if self.tts_worker and self.tts_worker.isRunning():
            self.tts_worker.stop(); self.tts_worker.wait()
        self.tts_worker = TTSWorker(text)
        self.tts_worker.finished.connect(self._on_reading_done)
        self.tts_worker.error.connect(self._on_tts_error)
        self.tts_worker.start()

    def _stop_reading(self):
        self.is_reading = False
        self.btn_read.setText("🔊 Read Aloud")
        self.btn_read.setStyleSheet(
            f"background:transparent; color:{GREEN}; border:1px solid #2A4030;"
            "border-radius:3px; padding:4px 10px;")
        if self.tts_worker and self.tts_worker.isRunning(): self.tts_worker.stop()

    def _on_reading_done(self):
        self.is_reading = False
        self.btn_read.setText("🔊 Read Aloud")
        self.btn_read.setStyleSheet(
            f"background:transparent; color:{GREEN}; border:1px solid #2A4030;"
            "border-radius:3px; padding:4px 10px;")

    def _on_tts_error(self, err):
        self._stop_reading(); self._add_system_card(f"TTS Error: {err}")

    # ── AI Panel toggle ───────────────────────────────────────────────────────
    def toggle_ai_panel(self):
        if self._ai_panel_visible:
            # save current sizes then collapse right panel
            self._splitter_sizes = self.splitter.sizes()
            self.ai_panel.hide()
            self._ai_panel_visible = False
            self.btn_ai_toggle.setText("AI")
            self.btn_ai_toggle.setToolTip("Show AI panel (Ctrl+\\)")
        else:
            self.ai_panel.show()
            self._ai_panel_visible = True
            self.btn_ai_toggle.setText("Hide Ai")
            self.btn_ai_toggle.setToolTip("Hide AI panel (Ctrl+\\)")
            self.splitter.setSizes(self._splitter_sizes)

    # ── Quiz Me ───────────────────────────────────────────────────────────────
    def quiz_current_page(self):
        if self.current_visible_page == -1 or not self.doc:
            self._add_system_card("Open a PDF and scroll to a page first."); return
        
        page = self.doc.load_page(self.current_visible_page)
        text = page.get_text().strip()
        
        import base64
        pix = page.get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
        img_b64 = base64.b64encode(pix.tobytes("jpeg")).decode('utf-8')

        if not text and not img_b64:
            self._add_system_card("No content found on this page to quiz from."); return
            
        self._add_system_card(f"⚡ Generating quiz for page {self.current_visible_page + 1}…")
        self._pending_summary_page = -1
        self.call_cloud_ai("quiz", text, image_b64=img_b64)

    # ── Annotation Save ───────────────────────────────────────────────────────
    def write_annotations_to_vector_doc(self):
        for idx, widget in enumerate(self.page_widgets):
            page = self.doc.load_page(idx); overlay = widget.overlay
            pdf_rect = page.rect; vw, vh = overlay.width(), overlay.height()
            if vw == 0 or vh == 0: continue
            sx, sy = pdf_rect.width/vw, pdf_rect.height/vh
            for q_rect in overlay.highlights:
                r = fitz.Rect(q_rect.left()*sx, q_rect.top()*sy,
                              q_rect.right()*sx, q_rect.bottom()*sy)
                a = page.add_rect_annot(r)
                a.set_colors(stroke=None, fill=(1, 0.92, 0.23))
                a.set_opacity(0.4); a.update()
            for stroke in overlay.drawings:
                pts = [fitz.Point(p.x()*sx, p.y()*sy) for p in stroke]
                if len(pts) > 1:
                    a = page.add_ink_annot([pts])
                    a.set_colors(stroke=(0.9, 0.3, 0.2)); a.set_border(width=2); a.update()
            for note in overlay.text_notes:
                r = fitz.Rect(note["pos"].x()*sx, note["pos"].y()*sy,
                              (note["pos"].x()+150)*sx, (note["pos"].y()+30)*sy)
                a = page.add_freetext_annot(r, note["text"], fontsize=10,
                                            color=(0.1, 0.2, 0.3)); a.update()

    def save_pdf_overwrite(self):
        if not self.doc or not self.current_file_path: return
        try:
            self.write_annotations_to_vector_doc()
            tmp = self.current_file_path + ".tmp"
            self.doc.save(tmp, garbage=3, deflate=True); self.doc.close()
            os.remove(self.current_file_path); os.rename(tmp, self.current_file_path)
            self.doc = fitz.open(self.current_file_path)
            self._add_system_card("✓ Saved.")
        except Exception as e: self._add_system_card(f"Save error: {e}")

    def save_pdf_as(self):
        if not self.doc: return
        fp, _ = QFileDialog.getSaveFileName(self, "Save PDF As", "", "PDF Files (*.pdf)")
        if not fp: return
        try:
            self.write_annotations_to_vector_doc()
            self.doc.save(fp, garbage=3, deflate=True)
            self._add_system_card(f"✓ Exported to {os.path.basename(fp)}")
        except Exception as e: self._add_system_card(f"Export error: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    viewer = StudyCompanionApp()
    viewer.show()
    sys.exit(app.exec())