# archive_selection_dialog.py

from PyQt5 import QtWidgets, QtCore, QtGui
from datetime import datetime, timedelta
import re
import os
import zipfile
from filter_dialog import FilterManagementDialog

class ArchiveSelectionDialog(QtWidgets.QDialog):
    def __init__(self, archive_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files from Archive")
        self.archive_path = archive_path
        self.file_items = []
        self.min_date_in_files = None
        self.max_date_in_files = None

        # Store the filter that was active when the dialog was opened
        self.initial_filter = self.parent().app_logic.get_active_filter_name()

        self.setup_ui()
        self.populate_file_list()

    def setup_ui(self):
        self.setMinimumSize(800, 600)
        layout = QtWidgets.QVBoxLayout(self)

        # Duration label
        self.duration_label = QtWidgets.QLabel("Selected duration: N/A")
        font = self.duration_label.font()
        font.setBold(True)
        self.duration_label.setFont(font)
        self.duration_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.duration_label)

        # Filters
        filter_group = QtWidgets.QGroupBox("Filters")
        filter_layout = QtWidgets.QGridLayout()

        # Type filter
        type_label = QtWidgets.QLabel("Log Type:")
        self.type_app_radio = QtWidgets.QRadioButton("App")
        self.type_app_radio.setChecked(True)
        self.type_error_radio = QtWidgets.QRadioButton("Error")
        
        type_hbox = QtWidgets.QHBoxLayout()
        type_hbox.addWidget(self.type_app_radio)
        type_hbox.addWidget(self.type_error_radio)
        type_hbox.addStretch()

        filter_layout.addWidget(type_label, 0, 0)
        filter_layout.addLayout(type_hbox, 0, 1)

        # Date range filter
        filter_layout.addWidget(QtWidgets.QLabel("From:"), 1, 0)
        self.start_date_edit = QtWidgets.QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        filter_layout.addWidget(self.start_date_edit, 1, 1)

        filter_layout.addWidget(QtWidgets.QLabel("To:"), 2, 0)
        self.end_date_edit = QtWidgets.QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        filter_layout.addWidget(self.end_date_edit, 2, 1)

        # Last N days filter
        last_n_days_label = QtWidgets.QLabel("Select Last N Days:")
        self.last_n_days_spinbox = QtWidgets.QSpinBox()
        self.last_n_days_spinbox.setMinimum(1)
        self.last_n_days_spinbox.setEnabled(False) # Disabled until files are loaded
        
        filter_layout.addWidget(last_n_days_label, 3, 0)
        filter_layout.addWidget(self.last_n_days_spinbox, 3, 1)

        # Full-text indexing checkbox
        self.full_text_indexing_checkbox = QtWidgets.QCheckBox("Enable Full-Text Indexing")
        self.full_text_indexing_checkbox.setChecked(True)
        filter_layout.addWidget(self.full_text_indexing_checkbox, 4, 0, 1, 2)  # Span two columns

        # Filter selection combo box
        filter_selection_label = QtWidgets.QLabel("Select Filter:")
        self.filter_combo_box = QtWidgets.QComboBox()
        self.populate_filter_combo_box()
        filter_layout.addWidget(filter_selection_label, 5, 0)
        filter_layout.addWidget(self.filter_combo_box, 5, 1)

        # Add button to open filter management dialog
        self.manage_filters_button = QtWidgets.QPushButton("Manage Filters")
        self.manage_filters_button.clicked.connect(self.open_filter_management_dialog)
        filter_layout.addWidget(self.manage_filters_button, 5, 2)

        filter_group.setLayout(filter_layout)
        layout.addWidget(filter_group)

        # File list
        self.file_list_widget = QtWidgets.QListWidget()
        self.file_list_widget.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        layout.addWidget(self.file_list_widget)
        
        # Selection buttons
        selection_layout = QtWidgets.QHBoxLayout()
        self.select_all_button = QtWidgets.QPushButton("Select All Visible")
        self.deselect_all_button = QtWidgets.QPushButton("Deselect All Visible")
        selection_layout.addWidget(self.select_all_button)
        selection_layout.addWidget(self.deselect_all_button)
        selection_layout.addStretch()
        layout.addLayout(selection_layout)

        # Buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Connections
        self.type_app_radio.toggled.connect(self.apply_filters)
        self.type_error_radio.toggled.connect(self.apply_filters)
        self.start_date_edit.dateChanged.connect(self._update_days_spinbox)
        self.end_date_edit.dateChanged.connect(self._update_days_spinbox)
        self.last_n_days_spinbox.valueChanged.connect(self._on_last_n_days_changed)
        
        self.select_all_button.clicked.connect(lambda: self.set_visible_items_check_state(QtCore.Qt.Checked))
        self.deselect_all_button.clicked.connect(lambda: self.set_visible_items_check_state(QtCore.Qt.Unchecked))

    def populate_filter_combo_box(self):
        import json
        # Load filters from last_filter_directory
        filter_directory = self.parent().last_filter_directory
        self.filter_combo_box.clear()
        self.filter_combo_box.addItem('No Filter')
        filter_names = []
        if os.path.exists(filter_directory):
            for f in os.listdir(filter_directory):
                file_path = os.path.join(filter_directory, f)
                if os.path.isfile(file_path) and f.lower().endswith('.json'):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as jf:
                            data = json.load(jf)
                            if isinstance(data, dict) and "name" in data:
                                filter_names.append(data["name"])
                    except Exception:
                        continue
            self.filter_combo_box.addItems(filter_names)

        # Set initial filter selection based on active_filter_name
        active_filter_name = self.initial_filter
        if active_filter_name:
            index = self.filter_combo_box.findText(active_filter_name)
            if index != -1:
                self.filter_combo_box.setCurrentIndex(index)
            else:
                self.filter_combo_box.setCurrentIndex(0)
        else:
            self.filter_combo_box.setCurrentIndex(0)

    def _on_last_n_days_changed(self, days):
        if not self.max_date_in_files:
            return

        # Block signals to prevent feedback loop
        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)

        new_start_date = self.max_date_in_files - timedelta(days=days - 1)
        self.start_date_edit.setDate(new_start_date)
        self.end_date_edit.setDate(self.max_date_in_files)

        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)

        # Manually trigger filter update
        self.apply_filters()

    def _update_days_spinbox(self):
        if not self.max_date_in_files:
            return
            
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()
        
        if start_date > end_date:
            return

        days = (end_date - start_date).days + 1
        
        # Block signals to prevent feedback loop
        self.last_n_days_spinbox.blockSignals(True)
        self.last_n_days_spinbox.setValue(days)
        self.last_n_days_spinbox.blockSignals(False)
        
        self.apply_filters()


    def populate_file_list(self):
        dated_file_pattern = re.compile(r'(app|error)-(\d{4}-\d{2}-\d{2})(?:-\d+)?\.log(\.gz)?')
        undated_files = {}
        max_date = None

        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zf:
                for member_info in zf.infolist():
                    if member_info.is_dir() or member_info.filename.startswith('__MACOSX/'):
                        continue
                    
                    filename = os.path.basename(member_info.filename)
                    match = dated_file_pattern.match(filename)

                    if match:
                        log_type, date_str, _ = match.groups()
                        log_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                        self.file_items.append({'name': member_info.filename, 'type': log_type, 'date': log_date})
                        if max_date is None or log_date > max_date:
                            max_date = log_date
                    elif filename in ['app.log', 'error.log', 'app.log.gz', 'error.log.gz']:
                        log_type = 'app' if 'app' in filename else 'error'
                        undated_files[filename] = {'name': member_info.filename, 'type': log_type, 'date': None}

        except (zipfile.BadZipFile, FileNotFoundError) as e:
            QtWidgets.QMessageBox.critical(self, "Error", f"Could not open or read archive: {e}")
            QtCore.QTimer.singleShot(0, self.reject)
            return

        if max_date and undated_files:
            next_day = max_date + timedelta(days=1)
            for f in undated_files.values():
                f['date'] = next_day
            self.file_items.extend(undated_files.values())

        if not self.file_items:
            self.duration_label.setText("No log files found in archive.")
            return

        self.file_items.sort(key=lambda x: x['date'])

        self.min_date_in_files = self.file_items[0]['date']
        self.max_date_in_files = self.file_items[-1]['date']

        self.start_date_edit.setDateRange(self.min_date_in_files, self.max_date_in_files)
        self.end_date_edit.setDateRange(self.min_date_in_files, self.max_date_in_files)
        
        self.start_date_edit.setDate(self.min_date_in_files)
        self.end_date_edit.setDate(self.max_date_in_files)
        
        total_days = (self.max_date_in_files - self.min_date_in_files).days + 1
        self.last_n_days_spinbox.setRange(1, total_days)
        self.last_n_days_spinbox.setValue(total_days)
        self.last_n_days_spinbox.setEnabled(True)

        self.apply_filters()

    def apply_filters(self):
        self.file_list_widget.clear()
        
        start_date = self.start_date_edit.date().toPyDate()
        end_date = self.end_date_edit.date().toPyDate()

        if start_date > end_date:
            self.duration_label.setText("Invalid date range")
            return
            
        duration = (end_date - start_date).days + 1
        self.duration_label.setText(f"Selected duration: {duration} day(s)")
        
        if self.type_app_radio.isChecked():
            log_type_filter = 'app'
        else:
            log_type_filter = 'error'

        for file_info in self.file_items:
            # Date check
            if not (start_date <= file_info['date'] <= end_date):
                continue
            
            # Type check
            if file_info['type'] != log_type_filter:
                continue

            item = QtWidgets.QListWidgetItem()
            item.setText(f"{file_info['name']} ({file_info['date'].strftime('%Y-%m-%d')})")
            item.setData(QtCore.Qt.UserRole, file_info)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked) # Default to checked
            self.file_list_widget.addItem(item)
            
    def set_visible_items_check_state(self, check_state):
        for i in range(self.file_list_widget.count()):
            self.file_list_widget.item(i).setCheckState(check_state)

    def get_selected_files(self):
        selected_files = []
        for i in range(self.file_list_widget.count()):
            item = self.file_list_widget.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                # We need to return the filename as it is inside the zip, which is stored in the data
                file_info = item.data(QtCore.Qt.UserRole)
                selected_files.append(file_info['name'])
        return selected_files

    def is_full_text_indexing_enabled(self):
        """
        Returns True if full-text indexing is enabled, False otherwise
        """
        return self.full_text_indexing_checkbox.isChecked()

    def accept(self):
        selected_filter = self.filter_combo_box.currentText()

        # Only update the app's filter if it has been changed in the dialog
        if selected_filter != self.initial_filter:
            if selected_filter == 'No Filter':
                self.parent().app_logic.clear_active_filter()
            else:
                self.parent().app_logic.apply_filter_by_name(selected_filter)

        super().accept()

    def open_filter_management_dialog(self):
        print("Opening filter management dialog...")
        filter_mgmt_dialog = FilterManagementDialog(self)
        # Set the initial directory for filters
        filter_dir = getattr(self.parent(), 'last_filter_directory', None)
        if filter_dir:
            filter_mgmt_dialog.set_initial_directory(filter_dir)
        filter_mgmt_dialog.setWindowModality(QtCore.Qt.NonModal)
        filter_mgmt_dialog.setWindowFlags(filter_mgmt_dialog.windowFlags() | QtCore.Qt.WindowStaysOnTopHint)
        filter_mgmt_dialog.setFocusPolicy(QtCore.Qt.StrongFocus)
        filter_mgmt_dialog.filter_selected.connect(self._on_filter_selected_from_mgmt)
        filter_mgmt_dialog.finished.connect(self.populate_filter_combo_box)
        filter_mgmt_dialog.show()
        filter_mgmt_dialog.raise_()
        filter_mgmt_dialog.activateWindow()
        print("Filter management dialog opened.")

    def _on_filter_selected_from_mgmt(self, filter_name, loggers):
        # Only set the combo box selection, do NOT apply the filter yet
        idx = self.filter_combo_box.findText(filter_name)
        if idx >= 0:
            self.filter_combo_box.setCurrentIndex(idx)

if __name__ == '__main__':
    import sys
    # Create a dummy zip for testing
    if not os.path.exists("dummy.zip"):
        with zipfile.ZipFile("dummy.zip", "w") as zf:
            zf.writestr("app-2023-01-01.log.gz", "log data")
            zf.writestr("error-2023-01-01.log.gz", "log data")
            zf.writestr("app-2023-01-02.log.gz", "log data")
            zf.writestr("app.log", "log data")

    app = QtWidgets.QApplication(sys.argv)
    dialog = ArchiveSelectionDialog("dummy.zip")
    if dialog.exec_():
        print("Selected files:", dialog.get_selected_files())
    
    if os.path.exists("dummy.zip"):
        os.remove("dummy.zip")
        
    sys.exit(0)
