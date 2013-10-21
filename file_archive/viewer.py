import platform
import subprocess
import sys

try:
    import sip

    api2_classes = [
            'QData', 'QDateTime', 'QString', 'QTextStream',
            'QTime', 'QUrl', 'QVariant',
            ]
    for cl in api2_classes:
        try:
            sip.setapi(cl, 2)
        except ValueError:
            pass

    from PyQt4 import QtCore, QtGui
except ImportError:
    sys.stderr.write("PyQt4 is required by 'file_archive view'\n")
    sys.exit(3)


try:
    import tdparser
except ImportError:
    sys.stderr.write("tdparser is required by 'file_archive view'\n")
    sys.exit(3)


from .compat import int_types
from .parser import parse_expression
from .trans import _, _n


MAX_RESULTS = 100


system = platform.system().lower()
if system == 'windows':
    def openfile(filename):
        subprocess.call(['cmd', '/c', 'start', filename])
elif system == 'darwin':
    def openfile(filename):
        subprocess.call(['open', filename])
elif system.startswith('linux'):
    def openfile(filename):
        subprocess.call(['xdg-open', filename])
else:
    openfile = None


class SearchError(Exception):
    """Error while querying the file store.
    """


class FileItem(QtGui.QTreeWidgetItem):
    def __init__(self, filehash):
        QtGui.QTreeWidgetItem.__init__(self, [filehash])
        self.hash = filehash


class MetadataItem(FileItem):
    def __init__(self, filehash, key, value):
        if isinstance(value, int_types):
            t = 'int'
            value = '%d' % value
        else: # isinstance(v, string_types):
            t = 'str'
        QtGui.QTreeWidgetItem.__init__(self, [key, value, t])
        self.hash = filehash


class StoreViewerWindow(QtGui.QMainWindow):
    def __init__(self, store):
        QtGui.QMainWindow.__init__(self)
        self.setWindowTitle(_(u"file_archive viewer"))

        self.store = store

        searchbar = QtGui.QHBoxLayout()

        self._needs_refresh = False

        # Input line for the query
        self._input = QtGui.QLineEdit()
        self._input.setPlaceholderText(_(u"Enter query here"))
        self._input.returnPressed.connect(self._search)
        self._input.textEdited.connect(lambda t: self._set_needs_refresh())
        searchbar.addWidget(self._input)

        # Search button
        self._searchbutton = QtGui.QPushButton(_(u"Search"))
        self._searchbutton.clicked.connect(self._search)
        self._set_needs_refresh(True)
        searchbar.addWidget(self._searchbutton)

        results = QtGui.QHBoxLayout()

        # Result view, as a tree with metadata
        self._result_tree = QtGui.QTreeWidget()
        self._result_tree.setColumnCount(3)
        self._result_tree.setHeaderLabels([_(u"Key"), _(u"Value"), _(u"Type")])
        self._result_tree.itemSelectionChanged.connect(self._selection_changed)
        results.addWidget(self._result_tree)

        # Buttons, enabled/disabled when the selection changes
        buttons = QtGui.QVBoxLayout()
        self._buttons = []

        # Open button; uses the system to choose the program to open with
        # (on Windows, might ask you what to use every time because of filename
        # scheme)
        open_button = QtGui.QPushButton(_(u"Open"))
        if openfile is not None:
            open_button.clicked.connect(self._openfile)
            self._buttons.append(('single', open_button))
        else:
            open_button.setEnabled(False)
        buttons.addWidget(open_button)

        # Delete button, removes what's selected (with confirmation)
        remove_button = QtGui.QPushButton(_(u"Delete"))
        remove_button.clicked.connect(self._delete)
        self._buttons.append(('multi', remove_button))
        buttons.addWidget(remove_button)

        self._selection_changed()
        results.addLayout(buttons)

        layout = QtGui.QVBoxLayout()
        layout.addLayout(searchbar)
        layout.addLayout(results)

        widget = QtGui.QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def _set_needs_refresh(self, needs=True):
        if needs == self._needs_refresh:
            return

        if needs:
            self._searchbutton.setStyleSheet('font-weight: bold;')
        else:
            self._searchbutton.setStyleSheet('')
        self._needs_refresh = needs

    def _search(self):
        error = None

        query = self._input.text()

        if len(query.split()) == 1 and all(o not in query.strip()
                                           for o in '=<>'):
            h = query.strip()
            try:
                entries = [self.store.get(h)]
            except KeyError:
                error = _(u"{h} not found", h=h)

        else:
            try:
                conditions = parse_expression(query)
            except ValueError as e:
                error = e.args[0]
            else:
                entries = self.store.query(conditions)

        self._result_tree.clear()

        if error is not None:
            w = QtGui.QTreeWidgetItem([error])
            w.setForeground(0, QtGui.QColor(255, 0, 0))
            self._result_tree.addTopLevelItem(w)
        else:
            for i, entry in enumerate(entries):
                file_item = FileItem(entry['hash'])
                f = file_item.font(0)
                f.setBold(True)
                file_item.setFont(0, f)
                self._result_tree.addTopLevelItem(file_item)
                self._result_tree.setFirstItemColumnSpanned(file_item, True)
                for k, v in entry.metadata.items():
                    if k == 'hash':
                        continue
                    file_item.addChild(MetadataItem(entry['hash'], k, v))

                if i >= MAX_RESULTS:
                    last_item = QtGui.QTreeWidgetItem(
                            [_(u"... stripped after {nb} results...",
                               nb=MAX_RESULTS)])
                    f = last_item.font(0)
                    f.setBold(True)
                    f.setItalic(True)
                    last_item.setFont(0, f)
                    self._result_tree.addTopLevelItem(last_item)
                    self._result_tree.setFirstItemColumnSpanned(last_item,
                                                                True)
                    break
            self._result_tree.expandAll()

        self._set_needs_refresh(False)

    def _selection_changed(self):
        items = self._result_tree.selectedItems()
        for t, button in self._buttons:
            if t == 'single':
                button.setEnabled(
                        len(items) == 1 and
                        isinstance(items[0], FileItem))
            else:
                button.setEnabled(bool(items) and
                                  all(isinstance(i, FileItem) for i in items))

    def _openfile(self):
        item = self._result_tree.currentItem()
        if item is not None:
            openfile(self.store.get_filename(item.hash))

    def _delete(self):
        items = self._result_tree.selectedItems()
        if not items:
            return
        confirm = QtGui.QMessageBox.question(
                self,
                _(u"Are you sure?"),
                _n(u"You are about to delete {num} entry from the store. "
                   u"Please confirm.",
                   u"You are about to delete {num} entries from the store. "
                   u"Please confirm.",
                   len(items),
                   num=len(items)),
                QtGui.QMessageBox.Ok | QtGui.QMessageBox.Cancel,
                QtGui.QMessageBox.Cancel)
        if confirm == QtGui.QMessageBox.Ok:
            hashes = set([i.hash for i in items])
            i = 0
            while i < self._result_tree.topLevelItemCount():
                h = self._result_tree.topLevelItem(i).hash
                if h in hashes:
                    self.store.remove(h)
                    self._result_tree.takeTopLevelItem(i)
                else:
                    i += 1


def run_viewer(store):
    application = QtGui.QApplication([])

    window = StoreViewerWindow(store)
    window.show()

    application.exec_()
    sys.exit(0)
