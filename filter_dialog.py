import os
import json
from PyQt5 import QtWidgets, QtCore

class FilterManagementDialog(QtWidgets.QDialog):
    """
    A dialog for managing, selecting, and applying logger filters from JSON files.
    """
    # Signal to emit the selected filter's name and its list of loggers
    filter_selected = QtCore.pyqtSignal(str, list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Logger Filters")
        self.setMinimumSize(450, 350)
        self.filters_in_dir = {}  # Maps display name to the list of loggers
        self.selected_directory = None
        self.setupUi()
        self.load_filters_from_directory(self.selected_directory)

    def setupUi(self):
        """Create and arrange the UI components for the dialog."""
        layout = QtWidgets.QVBoxLayout(self)

        # Directory selection section
        dir_layout = QtWidgets.QHBoxLayout()
        self.dir_label = QtWidgets.QLabel("No directory selected.")
        self.dir_label.setToolTip("The directory where your filter files are stored.")
        self.dir_button = QtWidgets.QPushButton("Select Directory...")
        dir_layout.addWidget(self.dir_label)
        dir_layout.addStretch()
        dir_layout.addWidget(self.dir_button)
        layout.addLayout(dir_layout)

        # Main horizontal layout for filter/logger lists
        main_split_layout = QtWidgets.QHBoxLayout()

        # Left: Filter List
        filter_layout = QtWidgets.QVBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("Filters:"))
        self.filter_list_widget = QtWidgets.QListWidget()
        self.filter_list_widget.setToolTip("Select a filter to view its loggers.")
        self.filter_list_widget.itemSelectionChanged.connect(self.display_loggers_for_selected_filter)
        filter_layout.addWidget(self.filter_list_widget)
        main_split_layout.addLayout(filter_layout)

        # Right: Logger List
        logger_layout = QtWidgets.QVBoxLayout()
        logger_layout.addWidget(QtWidgets.QLabel("Loggers:"))
        self.logger_list_widget = QtWidgets.QListWidget()
        self.logger_list_widget.setToolTip("Loggers associated with the selected filter.")
        logger_layout.addWidget(self.logger_list_widget)

        # Single Logger Selection Button
        logger_button_layout = QtWidgets.QHBoxLayout()
        self.select_loggers_button = QtWidgets.QPushButton("Select Loggers...")
        logger_button_layout.addWidget(self.select_loggers_button)
        logger_layout.addLayout(logger_button_layout)
        main_split_layout.addLayout(logger_layout)
        layout.addLayout(main_split_layout)

        # CRUD Buttons
        crud_button_layout = QtWidgets.QHBoxLayout()
        self.create_button = QtWidgets.QPushButton("Create")
        self.update_button = QtWidgets.QPushButton("Update")
        self.delete_button = QtWidgets.QPushButton("Delete")
        crud_button_layout.addWidget(self.create_button)
        crud_button_layout.addWidget(self.update_button)
        crud_button_layout.addWidget(self.delete_button)
        layout.addLayout(crud_button_layout)

        # Standard dialog buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        # --- Connections ---
        self.dir_button.clicked.connect(self.select_directory)
        button_box.accepted.connect(self.apply_filter) # OK button triggers accept
        button_box.rejected.connect(self.reject)   # Cancel button triggers reject
        self.filter_list_widget.itemDoubleClicked.connect(self.apply_filter)
        self.create_button.clicked.connect(self.create_filter)
        self.update_button.clicked.connect(self.update_filter)
        self.delete_button.clicked.connect(self.delete_filter)
        self.select_loggers_button.clicked.connect(self.select_loggers_dialog)

        # Global logger set
        self.global_logger_set = set()


    def select_directory(self):
        """Open a dialog to select the directory containing filter files."""
        start_dir = self.selected_directory or os.path.expanduser("~")
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory Containing Filters", start_dir)
        if directory:
            self.selected_directory = directory
            self.dir_label.setText(f"Folder: {os.path.basename(directory)}")
            self.dir_label.setToolTip(directory)
            self.load_filters_from_directory(directory)

    def load_filters_from_directory(self, directory):
        """Scan a directory for .json files and load them as potential filters, and update the global logger set."""
        self.filter_list_widget.clear()
        self.filters_in_dir.clear()
        self.global_logger_set = set()
        if not directory:
            return
        for filename in sorted(os.listdir(directory)):
            if filename.lower().endswith(".json"):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Validate the structure of the JSON file
                        if isinstance(data, dict) and "name" in data and "loggers" in data and isinstance(data["loggers"], list):
                            filter_name = data["name"]
                            loggers = data["loggers"]
                            self.filters_in_dir[filter_name] = loggers
                            self.filter_list_widget.addItem(filter_name)
                            self.global_logger_set.update(loggers)
                except (json.JSONDecodeError, KeyError, TypeError, IOError):
                    # Silently ignore invalid, malformed, or unreadable json files
                    continue


    def apply_filter(self):
        """Emit the selected filter's data and close the dialog."""
        selected_items = self.filter_list_widget.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a filter to apply.")
            return

        selected_filter_name = selected_items[0].text()
        loggers_to_apply = self.filters_in_dir.get(selected_filter_name)

        if loggers_to_apply is not None:
            self.filter_selected.emit(selected_filter_name, loggers_to_apply)
            self.accept()
        else:
            # This case should ideally not be reached with a correct implementation
            QtWidgets.QMessageBox.critical(self, "Error", "An internal error occurred. Could not find the selected filter data.")

    def set_initial_directory(self, directory):
        """Sets the directory to start in when the dialog is opened."""
        if directory and os.path.isdir(directory):
            self.selected_directory = directory
            self.dir_label.setText(f"Folder: {os.path.basename(directory)}")
            self.dir_label.setToolTip(directory)
            self.load_filters_from_directory(directory)
        else:
            self.dir_label.setText("No directory selected.")
            self.dir_label.setToolTip("The directory where your filter files are stored.")

    def get_selected_directory(self):
        """Returns the last successfully selected directory."""
        return self.selected_directory

    def create_filter(self):
        name, ok = QtWidgets.QInputDialog.getText(self, "Create Filter", "Enter filter name:")
        if ok and name:
            loggers, ok = QtWidgets.QInputDialog.getText(self, "Create Filter", "Enter loggers (comma-separated):")
            if ok:
                loggers_list = [logger.strip() for logger in loggers.split(',')]
                file_path = os.path.join(self.selected_directory, f"{name}.json")
                filter_data = {"name": name, "loggers": loggers_list}
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(filter_data, f, indent=4)
                self.load_filters_from_directory(self.selected_directory)

    def update_filter(self):
        selected_items = self.filter_list_widget.selectedItems()
        if selected_items:
            current_name = selected_items[0].text()
            current_loggers = ', '.join(self.filters_in_dir[current_name])
            name, ok = QtWidgets.QInputDialog.getText(self, "Update Filter", "Edit filter name:", text=current_name)
            if ok and name:
                loggers, ok = QtWidgets.QInputDialog.getText(self, "Update Filter", "Edit loggers (comma-separated):", text=current_loggers)
                if ok:
                    loggers_list = [logger.strip() for logger in loggers.split(',')]
                    file_path = os.path.join(self.selected_directory, f"{current_name}.json")
                    filter_data = {"name": name, "loggers": loggers_list}
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(filter_data, f, indent=4)
                    self.load_filters_from_directory(self.selected_directory)

    def delete_filter(self):
        selected_items = self.filter_list_widget.selectedItems()
        if selected_items:
            current_name = selected_items[0].text()
            reply = QtWidgets.QMessageBox.question(self, "Delete Filter", f"Are you sure you want to delete '{current_name}'?", QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                file_path = os.path.join(self.selected_directory, f"{current_name}.json")
                os.remove(file_path)
                self.load_filters_from_directory(self.selected_directory)

    def display_loggers_for_selected_filter(self):
        self.logger_list_widget.clear()
        selected_items = self.filter_list_widget.selectedItems()
        if selected_items:
            filter_name = selected_items[0].text()
            loggers = self.filters_in_dir.get(filter_name, [])
            # Remove empty, sort, and number
            numbered_sorted = [f"{idx}. {logger}" for idx, logger in enumerate(sorted([l for l in loggers if l.strip()]), 1)]
            self.logger_list_widget.addItems(numbered_sorted)

    def select_loggers_dialog(self):
        selected_items = self.filter_list_widget.selectedItems()
        if not selected_items:
            return
        filter_name = selected_items[0].text()
        current_loggers = set(self.filters_in_dir.get(filter_name, []))
        all_loggers = sorted(self.global_logger_set)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Select Loggers")
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel("Select loggers for this filter:")
        layout.addWidget(label)
        search_edit = QtWidgets.QLineEdit()
        search_edit.setPlaceholderText("Search loggers...")
        layout.addWidget(search_edit)

        # Logger count label
        count_label = QtWidgets.QLabel()
        layout.addWidget(count_label)

        # Check/Uncheck All Buttons (affect filtered only)
        check_btn_layout = QtWidgets.QHBoxLayout()
        check_all_btn = QtWidgets.QPushButton("Check All")
        uncheck_all_btn = QtWidgets.QPushButton("Uncheck All")
        check_btn_layout.addWidget(check_all_btn)
        check_btn_layout.addWidget(uncheck_all_btn)
        layout.addLayout(check_btn_layout)

        list_widget = QtWidgets.QListWidget()
        list_widget.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        layout.addWidget(list_widget)

        # Store checked state across filters
        checked_state = {logger: (logger in current_loggers) for logger in all_loggers if logger.strip()}

        def populate_list(filter_text=""):
            list_widget.clear()
            filter_text_l = filter_text.lower()
            filtered_loggers = [logger for logger in all_loggers if logger.strip() and (not filter_text_l or filter_text_l in logger.lower())]
            filtered_loggers.sort()
            # Numbered and sorted
            for idx, logger in enumerate(filtered_loggers, 1):
                display_text = f"{idx}. {logger}"
                item = QtWidgets.QListWidgetItem(display_text)
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                # Remove numbering for check state lookup
                logger_name = logger
                item.setCheckState(QtCore.Qt.Checked if checked_state.get(logger_name, False) else QtCore.Qt.Unchecked)
                list_widget.addItem(item)
            count_label.setText(f"Found: {len(filtered_loggers)}")

        def update_checked_state():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                # Remove numbering prefix for logger name
                logger_name = item.text().split('. ', 1)[-1]
                checked_state[logger_name] = (item.checkState() == QtCore.Qt.Checked)

        # Connect signals
        def on_item_changed(item):
            logger_name = item.text().split('. ', 1)[-1]
            checked_state[logger_name] = (item.checkState() == QtCore.Qt.Checked)

        list_widget.itemChanged.connect(on_item_changed)
        search_edit.textChanged.connect(lambda text: (update_checked_state(), populate_list(text)))

        def check_all_visible():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                item.setCheckState(QtCore.Qt.Checked)
                logger_name = item.text().split('. ', 1)[-1]
                checked_state[logger_name] = True
        def uncheck_all_visible():
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                item.setCheckState(QtCore.Qt.Unchecked)
                logger_name = item.text().split('. ', 1)[-1]
                checked_state[logger_name] = False
        check_all_btn.clicked.connect(check_all_visible)
        uncheck_all_btn.clicked.connect(uncheck_all_visible)

        # Initial population
        populate_list()

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)

        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            update_checked_state()
            checked = [logger for logger, checked in checked_state.items() if checked and logger.strip()]
            updated = sorted(checked)
            self.filters_in_dir[filter_name] = updated
            self.display_loggers_for_selected_filter()
            # Immediately save to JSON file
            if hasattr(self, 'selected_directory') and self.selected_directory:
                file_path = os.path.join(self.selected_directory, f"{filter_name}.json")
                filter_data = {
                    "name": filter_name,
                    "loggers": updated
                }
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        import json
                        json.dump(filter_data, f, indent=4)
                    print(f"[FilterDialog] Saved filter '{filter_name}' with {len(updated)} loggers to {file_path}")
                except Exception as e:
                    print(f"[FilterDialog] Failed to save filter '{filter_name}': {e}")



    def remove_logger(self):
        selected_items = self.filter_list_widget.selectedItems()
        if selected_items:
            filter_name = selected_items[0].text()
            selected_loggers = self.logger_list_widget.selectedItems()
