# Log Archive Loading and Parsing Process

This document details the step-by-step process of how the iObeya Log Analyzer loads, parses, and processes log files from a `.zip` archive. The entire workflow is designed to be efficient, robust, and non-blocking, ensuring the user interface remains responsive even when handling large files.

## 1. User Action: Initiating the Load

The process begins when the user clicks on the **"Load Log Archive..."** option from the "File" menu in the main application window.

-   **File**: `iobeya_log_analyzer.py`
-   **Method**: `create_menu_bar()`
-   **Action**: The `triggered` signal of the "Load Log Archive" menu action is connected to the `load_log_archive()` method.

## 2. Archive and File Selection

The `load_log_archive()` method orchestrates the initial user interaction.

-   **File**: `iobeya_log_analyzer.py`
-   **Method**: `load_log_archive()`

1.  A standard **File Dialog** prompts the user to select a `.zip` archive.
2.  Upon selection, a custom **`ArchiveSelectionDialog`** is launched. This dialog inspects the contents of the zip file and presents a list of the log files found within it.
3.  The user can then select the specific log files they wish to analyze from this list.

## 3. The `ArchiveSelectionDialog`: Inspecting the Zip

This dialog is responsible for reading the archive and displaying its contents.

-   **File**: `archive_selection_dialog.py`
-   **Method**: `populate_file_list()`

1.  **Open Archive**: It opens the selected `.zip` file using Python's `zipfile` library.
2.  **Scan and Parse**: It iterates through each file in the archive, using regular expressions to parse filenames and extract key information like the log type (`app` or `error`) and the date.
3.  **Populate UI**: It populates the dialog's list widget with the discovered files and automatically configures date range filters based on the oldest and newest logs found.

## 4. Initiating Background Processing

Once the user confirms their selection, the main application hands off the heavy lifting to a background thread.

-   **File**: `iobeya_log_analyzer.py`
-   **Method**: `_initiate_loading_process()`

1.  **Prevent Overlap**: It checks if another loading process is already running.
2.  **Create `LogLoaderThread`**: It instantiates a `LogLoaderThread` (a `QThread` subclass). This is the key to preventing the UI from freezing.
3.  **Pass Information**: It passes the archive path and the list of selected files to the new thread.
4.  **Connect Signals**: It connects signals from the thread (e.g., for progress updates, completion) to methods (slots) in the main UI.
5.  **Start Thread**: It calls `.start()` on the thread to begin the background processing.

## 5. The `LogLoaderThread`: Background Execution

All subsequent steps occur within the `LogLoaderThread` to ensure the main application remains responsive.

-   **File**: `log_processing.py`
-   **Class**: `LogLoaderThread`

### 5.1. Extracting Files from the Archive

-   **Method**: `_process_archive()`

1.  **Extraction Loop**: The thread iterates through the list of files selected by the user.
2.  **Save to Temp**: Each file is extracted from the `.zip` archive and saved to a temporary directory on the disk.
3.  **Process Individually**: For each extracted file, it calls the `_process_single_file()` method.

### 5.2. Preparing Each File for Parsing

-   **Method**: `_process_single_file()`

This method handles the "physical" characteristics of each log file.

1.  **Decompression**: It checks if the filename ends with `.gz`. If so, it decompresses the file into another temporary file.
2.  **Encoding Handling**: It attempts to open the file with `UTF-8` encoding. If this fails (due to a `UnicodeDecodeError`), it intelligently retries with a list of other common encodings until it succeeds. This makes the parsing process very robust against different file formats.

### 5.3. Parsing the Log Content

-   **Method**: `_parse_log_from_iterator()`

This is the core of the parsing logic, where raw text is converted into structured data.

1.  **Regex Matching**: It uses a compiled regular expression to match and capture the components of each log line (timestamp, level, logger name, and message).
2.  **Memory-Efficient Reading**: It reads the file line-by-line, which is highly efficient and avoids loading large files into memory.
3.  **Live Filtering**: If a filter is active in the UI, it is applied here. Lines that do not match the filter are skipped immediately, reducing processing overhead.

## 6. Data Storage: The "Metadata-Only" Strategy

A key aspect of the application's performance is how it stores the parsed data. Instead of storing the full, potentially multi-line, log message for every entry, it adopts a **metadata-only** approach.

For each log entry found, it creates a lightweight Python dictionary containing only the essential metadata:

```python
{
    'datetime': '2023-01-01 12:00:00', # The raw timestamp string
    'datetime_obj': datetime_object,   # The parsed datetime object for sorting
    'log_level': 'INFO',               # The log level
    'logger_name': 'com.iobeya....',    # The logger name
    'source_file_path': '/tmp/log_analyzer_xyz/app-2023-01-01.log', # Path to the source file
    'line_number': 123,                # The starting line number of the entry
    'message_preview': 'User logged in...' # A short preview (the first line of the message)
}
```

This strategy keeps the initial memory usage low. The full log message is only loaded from the original file on-demand when a user explicitly clicks on an entry in the UI's log table.

## 7. Finalization and Display

1.  **Aggregation**: The lists of metadata dictionaries from all processed files are combined.
2.  **Sorting**: The entire collection of log entries is sorted chronologically using the `datetime_obj`.
3.  **Data Hand-off**: The final, sorted list is converted into a pandas DataFrame and sent back to the main application thread via a `finished_loading` signal.
4.  **UI Update**: The main application receives the DataFrame and updates the log table, timeline, and other UI elements to display the data.

This concludes the journey from a user's click to the logs being displayed in the application.
