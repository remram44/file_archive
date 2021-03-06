from __future__ import division, unicode_literals

import imp
import os
import platform
import subprocess
import sys


try:
    import tdparser
except ImportError:
    sys.stderr.write("tdparser is required by 'file_archive view'\n")
    sys.exit(3)


from file_archive import hash_metadata
from file_archive.compat import int_types
from file_archive.parser import parse_expression
from file_archive.trans import _, _n


def get_qt():
    qtapi = os.environ.get('QT_API', 'pyqt')

    # Try PyQt4
    if qtapi == 'pyqt' or qtapi == 'pyqt4':
        try:
            PyQt4 = __import__('PyQt4')
            imp.find_module('QtCore', PyQt4.__path__)
            imp.find_module('QtGui', PyQt4.__path__)
            import sip
        except ImportError:
            pass
        else:
            api2_classes = [
                'QData', 'QDateTime', 'QString', 'QTextStream',
                'QTime', 'QUrl', 'QVariant'
            ]
            for cl in api2_classes:
                try:
                    sip.setapi(cl, 2)
                except ValueError:
                    pass
            import PyQt4.QtCore
            import PyQt4.QtGui
            os.environ['QT_API'] = 'pyqt'
            return PyQt4, qtapi
    # Try PyQt5
    if qtapi == 'pyqt5':
        try:
            PyQt5 = __import__('PyQt5')
            imp.find_module('QtCore', PyQt5.__path__)
            imp.find_module('QtGui', PyQt5.__path__)
        except ImportError:
            pass
        else:
            import PyQt5.QtCore
            import PyQt5.QtGui
            import PyQt5.QtWidgets
            os.environ['QT_API'] = 'pyqt5'
            return PyQt5, qtapi
    # Oh no
    sys.stderr.write("'file_archive view' requires either PyQt4 or PyQt5\n")
    if 'QT_API' in os.environ:
        sys.stderr.write("QT_API is currently set to '%s', which is not "
                         "supported\n" % qtapi)
    sys.exit(3)


PyQt, qtapi = get_qt()
QtCore = PyQt.QtCore
QtGui = PyQt.QtGui
QtWidgets = PyQt.QtWidgets if qtapi == 'pyqt5' else PyQt.QtGui


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


__all__ = ['StoreViewerWindow', 'run_viewer']


class SearchError(Exception):
    """Error while querying the file store.
    """


class FileItem(QtWidgets.QTreeWidgetItem):
    def __init__(self, entry):
        self.entry = entry
        QtWidgets.QTreeWidgetItem.__init__(self, [entry.objectid])


class MetadataItem(FileItem):
    def __init__(self, entry, key, value):
        if isinstance(value, int_types):
            t = 'int'
            value = '%d' % value
        else:  # isinstance(v, string_types):
            t = 'str'
        QtWidgets.QTreeWidgetItem.__init__(self, [key, value, t])
        self.entry = entry


class StoreViewerWindow(QtWidgets.QMainWindow):
    WINDOW_TITLE = _("file_archive viewer")

    MAX_RESULTS = 100

    def __init__(self, store):
        QtWidgets.QMainWindow.__init__(self)
        self.setWindowTitle(self.WINDOW_TITLE)

        self.store = store

        searchbar = QtWidgets.QHBoxLayout()

        self._needs_refresh = False

        # Input line for the query
        self._input = QtWidgets.QLineEdit()
        self._input.setPlaceholderText(_("Enter query here"))
        self._input.returnPressed.connect(self._search)
        self._input.textEdited.connect(lambda t: self._set_needs_refresh())
        searchbar.addWidget(self._input)

        # Search button
        self._searchbutton = QtWidgets.QPushButton(_("Search"))
        self._searchbutton.clicked.connect(self._search)
        searchbar.addWidget(self._searchbutton)

        results = QtWidgets.QHBoxLayout()

        # Result view, as a tree with metadata
        self._result_tree = QtWidgets.QTreeWidget()
        self._result_tree.setColumnCount(3)
        self._result_tree.setHeaderLabels([_("Key"), _("Value"), _("Type")])
        self._result_tree.itemSelectionChanged.connect(self._selection_changed)
        results.addWidget(self._result_tree)

        # Buttons, enabled/disabled when the selection changes
        buttons = QtWidgets.QVBoxLayout()
        self._buttons = self._create_buttons()

        for _name, button in self._buttons:
            buttons.addWidget(button)
        self._selection_changed()
        results.addLayout(buttons)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(searchbar)
        layout.addLayout(results)

        widget = QtWidgets.QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        self._search()

    def _create_buttons(self):
        buttons = []

        # Open button; uses the system to choose the program to open with
        # (on Windows, might ask you what to use every time because of filename
        # scheme)
        open_button = QtWidgets.QPushButton(_("Open"))
        if openfile is not None:
            open_button.clicked.connect(self._openfile)
            buttons.append(('single', open_button))
        else:
            open_button.setEnabled(False)

        # Copy hash button
        copy_button = QtWidgets.QPushButton(_("Copy ID"))
        copy_button.clicked.connect(self._copy_objectid)
        buttons.append(('single', copy_button))

        # Edit metadata button
        edit_button = QtWidgets.QPushButton(_("Edit metadata..."))
        edit_button.clicked.connect(self._edit_metadata)
        buttons.append(('single', edit_button))

        # Delete button, removes what's selected (with confirmation)
        remove_button = QtWidgets.QPushButton(_("Delete"))
        remove_button.clicked.connect(self._delete)
        buttons.append(('multi', remove_button))

        return buttons

    def _set_needs_refresh(self, needs=True):
        if needs == self._needs_refresh:
            return

        if needs:
            self._searchbutton.setStyleSheet('font-weight: bold;')
        else:
            self._searchbutton.setStyleSheet('')
        self._needs_refresh = needs

    def _alter_search_conditions(self, conditions):
        return conditions

    def _search(self):
        error = None

        query = self._input.text()

        if len(query.split()) == 1 and all(o not in query.strip()
                                           for o in '=<>'):
            objectid = query.strip()
            try:
                entries = [self.store.get(objectid)]
            except KeyError:
                error = _("objectid '{oid}' not found", oid=objectid)

        else:
            try:
                conditions = parse_expression(query)
            except tdparser.Error as e:
                error = e.args[0]
            else:
                conditions = self._alter_search_conditions(conditions)
                entries = self.store.query(conditions, limit=self.MAX_RESULTS)

        self._result_tree.clear()

        if error is not None:
            w = QtWidgets.QTreeWidgetItem([error])
            w.setForeground(0, QtGui.QColor(255, 0, 0))
            self._result_tree.addTopLevelItem(w)
            self._result_tree.setFirstItemColumnSpanned(w, True)
        else:
            for i, entry in enumerate(entries):
                file_item = FileItem(entry)
                f = file_item.font(0)
                f.setBold(True)
                file_item.setFont(0, f)
                self._result_tree.addTopLevelItem(file_item)
                self._result_tree.setFirstItemColumnSpanned(file_item, True)
                for k, v in entry.metadata.items():
                    file_item.addChild(MetadataItem(entry, k, v))

                if i + 1 == self.MAX_RESULTS:
                    last_item = QtWidgets.QTreeWidgetItem(
                        [_("... stripped after {nb} results...",
                           nb=self.MAX_RESULTS)])
                    f = last_item.font(0)
                    f.setBold(True)
                    f.setItalic(True)
                    last_item.setFont(0, f)
                    self._result_tree.addTopLevelItem(last_item)
                    self._result_tree.setFirstItemColumnSpanned(last_item,
                                                                True)
                    break
            if self._result_tree.topLevelItemCount() == 0:
                w = QtWidgets.QTreeWidgetItem([_("No matches")])
                self._result_tree.addTopLevelItem(w)
                self._result_tree.setFirstItemColumnSpanned(w, True)
            self._result_tree.expandAll()

        self._set_needs_refresh(False)

    def _selection_changed(self):
        items = self._result_tree.selectedItems()
        for t, button in self._buttons:
            if t == 'single':
                button.setEnabled(len(items) == 1 and
                                  isinstance(items[0], FileItem))
            elif t == 'multi':
                button.setEnabled(bool(items) and
                                  all(isinstance(i, FileItem) for i in items))

    def _openfile(self):
        item = self._result_tree.currentItem()
        if item is not None:
            openfile(item.entry.filename)

    def _copy_objectid(self):
        items = self._result_tree.selectedItems()
        if not items:
            return
        objectid = items[0].entry.objectid

        clipboard = QtWidgets.QApplication.clipboard()
        clipboard.setText(objectid)

    def _edit_metadata(self):
        items = self._result_tree.selectedItems()
        if not items:
            return
        entry = items[0].entry

        editor = MetadataEditor(entry, self)
        editor.show()

    def change_metadata(self, old_objectid, metadata, remove_original=False):
        new_objectid = hash_metadata(metadata)
        if new_objectid == old_objectid:
            return

        self.store.metadata.add(new_objectid, metadata)

        if remove_original:
            self.store.remove(old_objectid)

        self._search()

    def _delete(self):
        items = self._result_tree.selectedItems()
        if not items:
            return
        confirm = QtWidgets.QMessageBox.question(
            self,
            _("Are you sure?"),
            _n("You are about to delete {num} entry from the store. "
               "Please confirm.",
               "You are about to delete {num} entries from the store. "
               "Please confirm.",
               len(items),
               num=len(items)),
            QtWidgets.QMessageBox.Ok | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel)
        if confirm == QtWidgets.QMessageBox.Ok:
            ids = set([i.entry.objectid for i in items])
            i = 0
            while i < self._result_tree.topLevelItemCount():
                oid = self._result_tree.topLevelItem(i).entry.objectid
                if oid in ids:
                    self.store.remove(oid)
                    self._result_tree.takeTopLevelItem(i)
                else:
                    i += 1


class MetadataEditor(QtWidgets.QDialog):
    def __init__(self, entry, parent):
        QtWidgets.QDialog.__init__(self, parent, QtCore.Qt.Dialog)
        self.setWindowModality(QtCore.Qt.ApplicationModal)

        self._entry = entry
        self._parent = parent

        label = QtWidgets.QLabel(_("Editing entry %s") % entry.objectid)

        self._table = QtWidgets.QTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(['key', 'type', 'value'])
        self._table.setSortingEnabled(True)
        self._table.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self._table.resizeColumnsToContents()
        scrollarea = QtWidgets.QScrollArea()
        scrollarea.setWidgetResizable(True)
        scrollarea.setWidget(self._table)

        plus = QtWidgets.QPushButton(_("+"))
        plus.clicked.connect(self._add_row)
        minus = QtWidgets.QPushButton(_("-"))
        minus.clicked.connect(self._remove_row)
        controls = QtWidgets.QVBoxLayout()
        controls.addWidget(plus)
        controls.addWidget(minus)

        table_row = QtWidgets.QHBoxLayout()
        table_row.addWidget(scrollarea)
        table_row.addLayout(controls)

        self._remove_original = QtWidgets.QCheckBox(_("Remove original entry"))
        self._remove_original.setChecked(False)
        self._remove_original.stateChanged.connect(self._mode_changed)

        self._ok_button = QtWidgets.QPushButton(_("Create new entry"))
        self._ok_button.clicked.connect(self._ok_clicked)
        cancel_button = QtWidgets.QPushButton(_("Cancel"))
        cancel_button.clicked.connect(lambda: self.setVisible(False))
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(self._ok_button)
        buttons.addWidget(cancel_button)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(label)
        layout.addLayout(table_row)
        layout.addWidget(self._remove_original)
        layout.addLayout(buttons)
        self.setLayout(layout)

        self._table.setSortingEnabled(False)
        for k, v in self._entry.metadata.items():
            if k == 'hash':
                continue
            self._add_row(k, v, sorting_disabled=True)
        self._table.setSortingEnabled(True)

    def _add_row(self, key=None, value=None, sorting_disabled=False):
        row = self._table.rowCount()
        if not sorting_disabled:
            self._table.setSortingEnabled(False)
        self._table.insertRow(row)

        typeedit = QtWidgets.QComboBox()
        typeedit.addItems(['int', 'str'])
        self._table.setCellWidget(row, 1, typeedit)

        if key is not None:
            keyitem = QtWidgets.QTableWidgetItem(key)
            self._table.setItem(row, 0, keyitem)
        if value is not None:
            if isinstance(value, int_types):
                typeedit.setCurrentIndex(0)
                value = '%s' % value
            else:
                typeedit.setCurrentIndex(1)
            valueitem = QtWidgets.QTableWidgetItem(value)
            self._table.setItem(row, 2, valueitem)

        if not sorting_disabled:
            self._table.setSortingEnabled(True)

    def _remove_row(self):
        row = self._table.currentRow()
        self._table.removeRow(row)

    def _mode_changed(self, remove_original):
        if remove_original:
            self._ok_button.setText(_("Replace entry"))
        else:
            self._ok_button.setText(_("Create new entry"))

    def _ok_clicked(self):
        error = None

        metadata = {}

        for row in range(self._table.rowCount()):
            key = self._table.item(row, 0).text()
            type_ = self._table.cellWidget(row, 1).currentText()
            value = self._table.item(row, 2).text()

            if not key:
                error = _("Empty key")

            if type_ == 'int':
                try:
                    value = int(value)
                except ValueError:
                    error = (_("Invalid int value for %(key)s (row %(row)d)") %
                             {'key': key, 'row': row + 1})
            elif type_ != 'str':
                error = _("Invalid type (row %d)") % (row + 1)

            if key in metadata:
                error = _("Duplicate key %s" % key)

            if error is not None:
                break

            metadata[key] = {'type': type_, 'value': value}

        if error is not None:
            QtWidgets.QMessageBox.critical(self, _("Invalid values"), error)
            return

        metadata['hash'] = self._entry.metadata['hash']

        self._parent.change_metadata(self._entry.objectid, metadata,
                                     self._remove_original.isChecked())
        self.setVisible(False)


def run_viewer(store):
    application = QtWidgets.QApplication([])

    window = StoreViewerWindow(store)
    window.show()

    application.exec_()
    sys.exit(0)
