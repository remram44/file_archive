import sys

try:
    from PyQt4 import QtCore, QtGui
except ImportError:
    sys.stderr.write("PyQt4 is required by 'file_archive view'\n")
    sys.exit(3)


class StoreViewerWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)


def run_viewer(store):
    application = QtGui.QApplication([])

    window = StoreViewerWindow()
    window.show()

    application.exec_()
    sys.exit(0)
