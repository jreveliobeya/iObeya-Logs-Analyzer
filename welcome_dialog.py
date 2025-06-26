from PyQt5 import QtWidgets, QtCore, QtGui

class WelcomeDialog(QtWidgets.QDialog):
    def __init__(self, recent_files, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.recent_files = recent_files
        self.result = {'action': None, 'path': None}

        self.setWindowTitle("Welcome to iObeya Log Analyzer")
        self.setMinimumSize(500, 300)

        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        # Title
        title_label = QtWidgets.QLabel("iObeya Log Analyzer")
        font = title_label.font()
        font.setPointSize(20)
        font.setBold(True)
        title_label.setFont(font)
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(title_label)

        subtitle_label = QtWidgets.QLabel("Get started by opening a log file or archive.")
        subtitle_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(subtitle_label)
        
        layout.addSpacing(20)

        # Main content area
        content_layout = QtWidgets.QHBoxLayout()
        
        # Left side: Quick Actions
        actions_group = QtWidgets.QGroupBox("Start New Analysis")
        actions_layout = QtWidgets.QVBoxLayout()
        
        self.open_file_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("document-open"), "Open Log File...")
        self.open_archive_button = QtWidgets.QPushButton(QtGui.QIcon.fromTheme("document-open-archive"), "Open Log Archive...")

        actions_layout.addWidget(self.open_file_button)
        actions_layout.addWidget(self.open_archive_button)
        actions_layout.addStretch()
        actions_group.setLayout(actions_layout)
        content_layout.addWidget(actions_group)

        # Right side: Recent Files
        recent_files_group = QtWidgets.QGroupBox("Open Recent")
        recent_files_layout = QtWidgets.QVBoxLayout()
        
        self.recent_files_list = QtWidgets.QListWidget()
        if self.recent_files:
            self.recent_files_list.addItems(self.recent_files)
        else:
            no_recent_label = QtWidgets.QLabel("No recent files")
            no_recent_label.setAlignment(QtCore.Qt.AlignCenter)
            recent_files_layout.addWidget(no_recent_label)

        recent_files_layout.addWidget(self.recent_files_list)
        recent_files_group.setLayout(recent_files_layout)
        content_layout.addWidget(recent_files_group)
        
        content_layout.setStretch(0, 1)
        content_layout.setStretch(1, 2)
        layout.addLayout(content_layout)

        # Connect signals
        self.open_file_button.clicked.connect(self.on_open_file)
        self.open_archive_button.clicked.connect(self.on_open_archive)
        self.recent_files_list.itemDoubleClicked.connect(self.on_recent_file_selected)

    def on_open_file(self):
        self.result['action'] = 'open_file'
        self.accept()

    def on_open_archive(self):
        self.result['action'] = 'open_archive'
        self.accept()

    def on_recent_file_selected(self, item):
        path = item.text()
        if path != "No recent files":
            self.result['action'] = 'open_recent'
            self.result['path'] = path
            self.accept()
