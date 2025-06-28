# Technical Specification: iObeya Log Analyzer Refactoring

**Version:** 1.0

**Date:** 2025-06-28

## 1. Introduction

This document outlines a technical specification for refactoring the iObeya Log Analyzer application. The primary goal is to improve the codebase's modularity, testability, and long-term maintainability by enforcing a stronger separation of concerns. The current architecture is functional but can be enhanced to better scale with future feature development.

The refactoring is divided into three main areas:

1.  **UI and Application Logic Decoupling**: Separating the UI construction from the main application class.
2.  **Decoupling Parsing from Threading**: Isolating the core log parsing logic from the background threading mechanism.
3.  **Introduction of a Formal Data Model**: Encapsulating the log data within a dedicated class to provide a clear and robust API for data access.

## 2. Area 1: UI and Application Logic Decoupling

### 2.1. Goal

To move all UI construction and layout code out of the main `LogAnalyzerApp` class, making it a pure controller responsible for orchestrating application flow and user interactions.

### 2.2. Implementation Details

#### 2.2.1. New File: `main_window_ui.py`

A new file will be created to house a class dedicated to building the main window's UI.

-   **File:** `main_window_ui.py`
-   **Class:** `MainWindowUI`
-   **Responsibilities:** This class will be responsible for instantiating all widgets, menus, toolbars, dialogs, and layouts for the main application window.

-   **Proposed Structure:**

    ```python
    # main_window_ui.py
    from PyQt5 import QtWidgets
    # ... other necessary imports

    class MainWindowUI:
        def setup_ui(self, main_window_instance):
            """Populates the main QMainWindow with all UI elements."""
            main_window_instance.setWindowTitle("iObeya Log Analyzer")
            main_window_instance.setMinimumSize(1200, 800)

            # Create all actions (these will be connected in the main app)
            self.load_file_action = QtWidgets.QAction("Load Log File...", main_window_instance)
            self.load_archive_action = QtWidgets.QAction("Load Log Archive...", main_window_instance)
            # ... all other actions

            # Create Menu Bar
            menu_bar = main_window_instance.menuBar()
            file_menu = menu_bar.addMenu("&File")
            file_menu.addAction(self.load_file_action)
            file_menu.addAction(self.load_archive_action)
            # ... add all other menus and actions

            # Create Widgets
            self.log_table_view = QtWidgets.QTableView()
            self.timeline_canvas = TimelineCanvas()
            # ... instantiate all other widgets

            # Setup Layouts and Central Widget
            central_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            central_splitter.addWidget(self.log_table_view)
            central_splitter.addWidget(self.timeline_canvas)
            main_window_instance.setCentralWidget(central_splitter)

            # Store references to important widgets
            # for the main app to access.
    ```

#### 2.2.2. Modifications to `iobeya_log_analyzer.py`

The `LogAnalyzerApp` class will be refactored to use the new `MainWindowUI` class.

-   **Responsibilities:** It will no longer contain any direct `QtWidgets` instantiation for the main window. It will handle signal/slot connections, application state transitions, and coordination between the `AppLogic` and the UI.

-   **Proposed `__init__` Structure:**

    ```python
    # iobeya_log_analyzer.py
    from main_window_ui import MainWindowUI
    from app_logic import AppLogic

    class LogAnalyzerApp(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()

            self.app_logic = AppLogic()
            self.ui = MainWindowUI()
            self.ui.setup_ui(self)

            self._connect_signals()

        def _connect_signals(self):
            """Connect all UI element signals to controller methods."""
            self.ui.load_archive_action.triggered.connect(self.load_log_archive)
            # ... connect all other signals

    # ... other methods like load_log_archive remain, but they will
    # interact with self.app_logic for state and self.ui for UI elements.
    ```

## 3. Area 2: Decoupling Parsing from Threading

### 3.1. Goal

To isolate the pure logic of parsing log files from the `QThread` implementation. This will make the parsing logic easier to test and modify independently of the threading context.

### 3.2. Implementation Details

#### 3.2.1. New File: `log_parser.py`

A new file will contain a `LogParser` class focused solely on parsing.

-   **File:** `log_parser.py`
-   **Class:** `LogParser`
-   **Responsibilities:** This class will handle file decompression, encoding detection, and line-by-line parsing. It will have no knowledge of PyQt or threading.

-   **Proposed Structure:**

    ```python
    # log_parser.py
    import re
    import gzip
    import shutil
    # ...

    class LogParser:
        def __init__(self, datetime_format, progress_callback=None):
            self.datetime_format = datetime_format
            self.progress_callback = progress_callback # Optional callback for progress
            self.entry_pattern = re.compile(...)

        def parse_file(self, file_path, temp_dir):
            # Contains logic from the current _process_single_file
            # Handles .gz decompression and encoding detection.
            # Returns a list of log entry dictionaries.
            ...

        def _parse_iterator(self, file_iterator, source_name):
            # Contains logic from the current _parse_log_from_iterator
            # This is a pure parsing loop.
            # It can call self.progress_callback if one is provided.
            ...
    ```

#### 3.2.2. Modifications to `log_processing.py`

The `LogLoaderThread` will be simplified to a pure thread manager.

-   **Responsibilities:** It will manage the background thread, handle archive extraction, instantiate and call the `LogParser`, and emit Qt signals for UI updates.

-   **Proposed `run` Method Structure:**

    ```python
    # log_processing.py
    from log_parser import LogParser

    class LogLoaderThread(QtCore.QThread):
        # ... signals remain the same

        def __init__(self, ..., datetime_format, ...):
            # ...
            self.parser = LogParser(datetime_format)

        def run(self):
            if self.archive_path:
                # ... loop through files in archive
                for filename in files_to_process:
                    # ... extract file to temp_path
                    try:
                        entries = self.parser.parse_file(temp_path, self.temp_dir)
                        all_log_entries.extend(entries)
                    except Exception as e:
                        # handle parsing errors
            # ...
            # Finalize and emit finished_loading signal
    ```

## 4. Area 3: Introduction of a Formal Data Model

### 4.1. Goal

To encapsulate the log data (currently a pandas DataFrame) into a dedicated class. This provides a single, authoritative source for data and a clear, controlled API for all data access and manipulation, including on-demand loading of full messages.

### 4.2. Implementation Details

#### 4.2.1. New File: `data_model.py`

-   **File:** `data_model.py`
-   **Class:** `LogDataModel`
-   **Responsibilities:** To hold the log data and provide methods for querying and accessing it.

-   **Proposed Structure:**

    ```python
    # data_model.py
    import pandas as pd

    class LogDataModel:
        def __init__(self, dataframe):
            self._df = dataframe

        @property
        def dataframe(self):
            return self._df

        def __len__(self):
            return len(self._df)

        def get_time_range(self):
            # Returns (min_datetime, max_datetime)
            ...

        def get_full_message_at(self, index):
            """On-demand loading of a full log message."""
            entry = self._df.iloc[index]
            file_path = entry['source_file_path']
            start_line = entry['line_number']
            # Logic to open file_path, read from start_line until the
            # next log entry pattern is found, and return the full message block.
            ...

        def filter(self, level=None, start_time=None, end_time=None, logger_name=None):
            """Applies filters and returns a NEW LogDataModel instance."""
            filtered_df = self._df
            # ... apply filters to filtered_df
            return LogDataModel(filtered_df)
    ```

#### 4.2.2. Modifications to `app_logic.py`

`AppLogic` will be updated to own and use the new `LogDataModel`.

-   **Attribute:** It will have a `self.log_data = None` attribute.
-   **Data Loading:** When log data is successfully loaded (e.g., in `on_log_data_loaded`), it will instantiate the model: `self.log_data = LogDataModel(loaded_dataframe)`.
-   **Data Access:** All other parts of the application will now go through `AppLogic` to get data. For example, to populate the log table, the UI controller will call a method on `app_logic` which in turn returns `self.log_data.dataframe`.

## 5. Conclusion

Executing this refactoring plan will significantly improve the application's architecture. The resulting codebase will be more organized, with clear boundaries between UI, logic, and data. This will make it substantially easier to debug issues, add new features, and write unit tests for individual components (e.g., the `LogParser` can be tested in isolation).
