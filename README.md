# Timeline Log Analyzer

A powerful log analysis tool with a timeline-based visualization for exploring and filtering large log files and archives.

## Features

-   **Timeline Visualization**: View log entry distribution over time and interactively filter by time range.
-   **Advanced Filtering**: Filter logs by level (INFO, WARN, ERROR, DEBUG), message type, and free-text search.
-   **Archive Support**: Load and analyze `.zip` archives containing multiple log files.
-   **Enhanced Archive Loading**: An advanced dialog allows for precise selection of files from an archive:
    -   Filter by log type (`app` or `error`).
    -   Select a custom date range.
    -   Quickly select the last "N" days of logs.
    -   View the total duration of the selected period.
-   **Gzip Decompression**: Automatically handles `.log.gz` files, both standalone and within archives.
-   **Detailed View**: Click on any log entry to see the full, multi-line message, including stack traces.
-   **Robust Statistics**: View detailed statistics, including log level distribution and a Pareto chart for the most frequent message types.

## Installation

### Prerequisites

-   Python 3.6+

### Setup

1.  **Clone the repository (or download the source code):**
    ```bash
    git clone <repository_url>
    cd <repository_directory>
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install the required dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Usage

To run the application, execute the main script from the root directory of the project:

```bash
python3 iobeya_log_analyzer.py
```

### Loading Logs

-   **Load File**: Use the "Load File" button to open a single log file (`.log`, `.txt`) or a compressed log file (`.log.gz`).
-   **Load Archive**: Use the "Load Archive" button to open a `.zip` archive. A dialog will appear with powerful options to filter and select files:
    -   **Log Type**: Choose between `app` or `error` logs. `app` is selected by default.
    -   **Date Range**: Manually set a "From" and "To" date. The total duration of the selection is displayed at the top.
    -   **Last N Days**: Use the spinbox to automatically select the last N days of available logs, which updates the date range for you.

## Configuration

The application is designed to parse log files with the following format:

```
YYYY-MM-DD HH:MM:SS LEVEL [logger_name] Message content...
```

**Example:**
```
2025-04-01 10:30:00 ERROR [com.example.MyClass] An unexpected error occurred.
java.lang.RuntimeException: Something went wrong
    at com.example.MyClass.doSomething(MyClass.java:42)
    ...
```

The log parsing logic is located in `log_processing.py`. If your log format differs, you may need to adjust the regular expression in the `_parse_log_from_iterator` method.

## Recent Updates

-   **Log View Enhancements**:
    -   **Line Colorization**: Log lines in the detailed view are now colored based on their severity level (Red for ERROR, Orange for WARN) for quicker identification.

-   **Timeline Improvements**:
    -   **Weekly Granularity**: The timeline can now be viewed with a "week" granularity, providing a broader overview of log activity.
    -   **Enhanced Tooltips**: 
        -   Hovering over the main date range display now shows a detailed tooltip with weekday names.
        -   Tooltips on individual timeline bars now include the start and end day of the week for that bar.

-   **Archive Selection Dialog Overhaul**:
    -   Improved UI with a clearer layout.
    -   Added a "Last N Days" selector for quick filtering.
    -   Added a dynamic label to show the selected time duration.
    -   Removed the ambiguous "All" log type filter.
-   **Bug Fixes**:
    -   Resolved a `ValueError` crash in the statistics panel when no data was loaded.
    -   Fixed a `NameError` that prevented the Pareto chart from rendering correctly.
