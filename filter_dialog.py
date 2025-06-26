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

        # List to display found filters
        layout.addWidget(QtWidgets.QLabel("Available Filters:"))
        self.filter_list_widget = QtWidgets.QListWidget()
        self.filter_list_widget.setToolTip("Double-click a filter to apply it.")
        layout.addWidget(self.filter_list_widget)

        # Standard dialog buttons
        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        layout.addWidget(button_box)

        # --- Connections ---
        self.dir_button.clicked.connect(self.select_directory)
        button_box.accepted.connect(self.apply_filter) # OK button triggers accept
        button_box.rejected.connect(self.reject)   # Cancel button triggers reject
        self.filter_list_widget.itemDoubleClicked.connect(self.apply_filter)

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
        """Scan a directory for .json files and load them as potential filters."""
        self.filter_list_widget.clear()
        self.filters_in_dir.clear()
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
