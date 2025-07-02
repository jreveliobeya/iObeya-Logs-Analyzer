from PyQt5 import QtWidgets, QtCore
import os
import json

class FilterCRUDDialog(QtWidgets.QDialog):
    def __init__(self, filter_directory, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Filters")
        self.filter_directory = filter_directory
        self.setup_ui()
        self.load_filters()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)

        # Filter list
        self.filter_list = QtWidgets.QListWidget()
        self.filter_list.itemSelectionChanged.connect(self.display_filter_details)
        layout.addWidget(self.filter_list)

        # Filter details
        self.name_edit = QtWidgets.QLineEdit()
        self.loggers_edit = QtWidgets.QTextEdit()
        layout.addWidget(QtWidgets.QLabel("Filter Name:"))
        layout.addWidget(self.name_edit)
        layout.addWidget(QtWidgets.QLabel("Loggers (comma-separated):"))
        layout.addWidget(self.loggers_edit)

        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        self.create_button = QtWidgets.QPushButton("Create")
        self.update_button = QtWidgets.QPushButton("Update")
        self.delete_button = QtWidgets.QPushButton("Delete")
        button_layout.addWidget(self.create_button)
        button_layout.addWidget(self.update_button)
        button_layout.addWidget(self.delete_button)
        layout.addLayout(button_layout)

        # Connect buttons
        self.create_button.clicked.connect(self.create_filter)
        self.update_button.clicked.connect(self.update_filter)
        self.delete_button.clicked.connect(self.delete_filter)

    def load_filters(self):
        self.filter_list.clear()
        if os.path.exists(self.filter_directory):
            for file_name in os.listdir(self.filter_directory):
                if file_name.endswith('.json'):
                    self.filter_list.addItem(file_name)

    def display_filter_details(self):
        current_item = self.filter_list.currentItem()
        if current_item:
            file_path = os.path.join(self.filter_directory, current_item.text())
            with open(file_path, 'r', encoding='utf-8') as f:
                filter_data = json.load(f)
                self.name_edit.setText(filter_data.get('name', ''))
                self.loggers_edit.setPlainText(', '.join(filter_data.get('loggers', [])))

    def create_filter(self):
        name = self.name_edit.text().strip()
        loggers = [logger.strip() for logger in self.loggers_edit.toPlainText().split(',')]
        if name:
            file_path = os.path.join(self.filter_directory, f"{name}.json")
            filter_data = {"name": name, "loggers": loggers}
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(filter_data, f, indent=4)
            self.load_filters()

    def update_filter(self):
        current_item = self.filter_list.currentItem()
        if current_item:
            name = self.name_edit.text().strip()
            loggers = [logger.strip() for logger in self.loggers_edit.toPlainText().split(',')]
            file_path = os.path.join(self.filter_directory, current_item.text())
            filter_data = {"name": name, "loggers": loggers}
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(filter_data, f, indent=4)
            self.load_filters()

    def delete_filter(self):
        current_item = self.filter_list.currentItem()
        if current_item:
            file_path = os.path.join(self.filter_directory, current_item.text())
            os.remove(file_path)
            self.load_filters()
