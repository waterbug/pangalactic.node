"""
Help document browser widget
"""
import os

from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtGui import QIcon, QKeySequence
from PyQt5.QtWidgets import (QAction, QApplication, QDialog,
    QLabel, QTextBrowser, QToolBar, QVBoxLayout)

# pangalactic
from pangalactic.core         import state
from pangalactic.core.uberorb import orb


class HelpWidget(QDialog):

    def __init__(self, page, parent=None):
        super(HelpWidget, self).__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setAttribute(Qt.WA_GroupLeader)
        self.create_widgets()
        self.layout_widgets()
        self.create_connections()
        self.text_browser.setSearchPaths([":/help"])
        self.text_browser.setSource(QUrl(page))
        self.resize(1200, 900)
        self.setWindowTitle("{0} Help".format(
                QApplication.applicationName()))

    def create_widgets(self):
        self.text_browser = QTextBrowser()
        self.back_action = self.create_action(
                                    "Go Back",
                                    slot=self.text_browser.backward,
                                    icon="left_arrow",
                                    tip="Back to previous page")
        self.back_action.setShortcut(QKeySequence.Back)
        self.home_action = self.create_action(
                                    "Home",
                                    slot=self.text_browser.home,
                                    icon="tardis",
                                    tip="Go to Help Home")
        self.home_action.setShortcut("Home")
        self.page_label = QLabel()

        self.tool_bar = QToolBar()
        self.tool_bar.addAction(self.back_action)
        self.tool_bar.addAction(self.home_action)
        self.tool_bar.addWidget(self.page_label)

    def create_action(self, text, slot=None, icon=None, tip=None,
                      checkable=False):
        action = QAction(text, self)
        if icon is not None:
            icon_file = icon + state.get('icon_type', '.ico')
            icon_dir = getattr(orb, 'icon_dir', 'icons')
            icon_path = os.path.join(icon_dir, icon_file)
            action.setIcon(QIcon(icon_path))
        if tip is not None:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            action.triggered.connect(slot)
        if checkable:
            action.setCheckable(True)
        return action

    def layout_widgets(self):
        layout = QVBoxLayout()
        layout.addWidget(self.tool_bar)
        layout.addWidget(self.text_browser, 1)
        self.setLayout(layout)

    def create_connections(self):
        self.text_browser.sourceChanged.connect(self.updatePageTitle)

    def updatePageTitle(self):
        self.page_label.setText(self.text_browser.documentTitle())


if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    widget = HelpWidget("file:///home/waterbug/gitlab/cattens/doc/user_guide.html")
    widget.show()
    app.exec_()

