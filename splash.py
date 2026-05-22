from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *

class SplashPage(QWidget):
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel()
        pix = QPixmap("logo/logo.png")
        logo.setPixmap(
            pix.scaled(
                120,120,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        )

        title = QLabel("PDFGo")
        title.setStyleSheet("""
            color:white;
            font-size:34px;
            font-weight:700;
        """)

        subtitle = QLabel("AI Powered Study Companion")
        subtitle.setStyleSheet("color:#999;")

        progress = QProgressBar()
        progress.setRange(0,0)
        progress.setFixedWidth(250)

        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(30)
        layout.addWidget(progress)

        self.setStyleSheet("""
        QWidget{
            background:#111827;
        }

        QProgressBar{
            background:#222;
            border:none;
            height:4px;
        }

        QProgressBar::chunk{
            background:#003FC2;
        }
        """)

        QTimer.singleShot(
            2500,
            self.finished.emit
        )