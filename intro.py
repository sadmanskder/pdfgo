from PyQt6.QtWidgets import *
from PyQt6.QtCore import *

class IntroPage(QWidget):

    startClicked = pyqtSignal()

    def __init__(self):
        super().__init__()

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Welcome to PDFGo")
        title.setStyleSheet("""
        font-size:40px;
        color:white;
        font-weight:700;
        """)

        desc = QLabel(
            "Read PDFs.\nAsk AI.\nUnderstand faster."
        )

        desc.setStyleSheet("""
        color:#aaa;
        font-size:18px;
        """)

        btn = QPushButton("Get Started")

        btn.setFixedSize(200,50)

        btn.setStyleSheet("""
        QPushButton{
            background:red;
            color:white;
            border:none;
            border-radius:12px;
            font-size:16px;
        }

        QPushButton:hover{
            background:#6e6eff;
        }
        """)

        btn.clicked.connect(
            self.startClicked.emit
        )

        layout.addWidget(title)
        layout.addWidget(desc)
        layout.addSpacing(40)
        layout.addWidget(btn)

        self.setStyleSheet("""
        background:#0f172a;
        """)