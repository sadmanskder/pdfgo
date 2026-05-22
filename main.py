import sys

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import *
from splash import SplashPage
from intro import IntroPage
from appwindow import StudyCompanionApp   # your current app


class Root(QStackedWidget):

    def __init__(self):
        super().__init__()
        # Remove the default OS top window bar for the splash/intro screens
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)

        self.splash = SplashPage()
        self.intro = IntroPage()

        self.addWidget(self.splash)
        self.addWidget(self.intro)

        self.splash.finished.connect(
            lambda:self.setCurrentIndex(1)
        )

        self.intro.startClicked.connect(self.launch_main)

        # Center the startup window and prevent right cut-out
        self._center_window(self)

    def _center_window(self, win):
        screen = QApplication.primaryScreen()
        if screen:
            avail_geom = screen.availableGeometry()
            new_width = min(700, avail_geom.width())
            new_height = min(600, avail_geom.height())
            win.resize(new_width, new_height)
            
            geo = win.frameGeometry()
            geo.moveCenter(avail_geom.center())
            win.move(geo.topLeft())

    def launch_main(self):
        # Create the main app as a true top-level window. 
        # This prevents the severe rendering duplication and layout bugs caused 
        # by embedding a FramelessMainWindow inside another widget.
        self.main_app = StudyCompanionApp()
        
        # Center the main app properly before showing it
        self._center_window(self.main_app)
        
        self.main_app.show()
        
        # Automatically trigger the PDF open dialog shortly after showing the window
        QTimer.singleShot(150, self.main_app.open_pdf)
        
        # Close the splash/intro window completely.
        # Since main_app is now visible, the application stays open.
        self.close()


app = QApplication(sys.argv)

window = Root()
window.show()

sys.exit(app.exec())
