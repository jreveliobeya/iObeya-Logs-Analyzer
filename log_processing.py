#!/usr/bin/env python3
import gzip
import io
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime
from collections import defaultdict, Counter
from PyQt5.QtCore import QObject, QThread, pyqtSignal
from PyQt5 import QtCore # Only QtCore needed for QThread and signals
import zipfile
import gzip
import io
import os # For path basename
import pandas as pd
import tempfile
import shutil

class LogLoaderThread(QThread):
    finished_loading = pyqtSignal(object, object) # df, failed_files_summary
    error_occurred = pyqtSignal(str)

    # Signals for the loading dialog
    status_update = pyqtSignal(str, str) # Main status, detail status
    file_progress_config = pyqtSignal(int, int) # Min, max for the current file progress bar
    file_progress_update = pyqtSignal(int) # Value for the current file progress bar
    total_progress_config = pyqtSignal(int, int) # Min, max for the total progress bar
    total_progress_update = pyqtSignal(int) # Value for the total progress bar
    message_count_update = pyqtSignal(int, int) # Number of messages loaded so far

    def __init__(self, file_path=None, archive_path=None, datetime_format=None, 
                 selected_files_from_archive=None, temp_dir=None, active_filter_loggers=None, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.archive_path = archive_path
        self.datetime_format_for_parsing = datetime_format
        self.selected_files_from_archive = selected_files_from_archive or []
        self.temp_dir = temp_dir
        self.active_filter_loggers = active_filter_loggers or set()
        self.total_messages_loaded = 0
        self.should_stop = False
        self.encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']

    def run(self):
        try:
            if not self.temp_dir or not os.path.exists(self.temp_dir):
                raise Exception("Temporary directory not provided or does not exist.")

            all_log_entries = []
            failed_files_summary = []
            if self.archive_path:
                self.status_update.emit("Processing archive...", os.path.basename(self.archive_path))
                all_log_entries, failed_files_summary = self._process_archive()
            elif self.file_path:
                self.status_update.emit("Processing file...", os.path.basename(self.file_path))
                all_log_entries = self._process_single_file(self.file_path)
            else:
                self.error_occurred.emit("No file or archive path specified.")
                return

            if self.should_stop:
                self.status_update.emit("Loading cancelled.", "")
                return

            if all_log_entries:
                self.status_update.emit("Finalizing...", f"Sorting {len(all_log_entries):,} entries")

                # Sort by datetime_obj primarily, then by original datetime string for stability
                def sort_key(entry):
                    dt_obj = entry.get('datetime_obj')
                    # Handle cases where datetime_obj might be min (parse error) or None
                    if isinstance(dt_obj, datetime) and dt_obj != datetime.min: return dt_obj
                    try:  # Fallback to parsing the string again if obj is bad
                        return datetime.strptime(entry.get('datetime', ''), self.datetime_format_for_parsing)
                    except:  # If truly unparseable, sort to the end
                        return datetime.max  # Sort unparseable/invalid dates to the end

                all_log_entries.sort(key=sort_key)

            if not self.should_stop:
                df_log_entries = pd.DataFrame(all_log_entries)
                self.finished_loading.emit(df_log_entries, failed_files_summary)
        except Exception as e:
            self.error_occurred.emit(f"Unexpected error during loading: {str(e)}")

    def _process_archive(self):
        all_entries = []
        failed_files = []
        try:
            with zipfile.ZipFile(self.archive_path, 'r') as zf:
                files_to_process = self.selected_files_from_archive or [info.filename for info in zf.infolist() if not info.is_dir() and not info.filename.startswith('__MACOSX/')]
                
                total_files = len(files_to_process)
                self.total_progress_config.emit(0, total_files)
                self.total_progress_update.emit(0)

                for i, filename in enumerate(files_to_process):
                    if self.should_stop: break
                    self.total_progress_update.emit(i)
                    self.status_update.emit(f"File {i+1} of {total_files}", filename)

                    try:
                        member_info = zf.getinfo(filename)
                        temp_file_path = os.path.join(self.temp_dir, os.path.basename(filename))
                        with zf.open(member_info) as source, open(temp_file_path, 'wb') as target:
                            shutil.copyfileobj(source, target)

                        entries = self._process_single_file(temp_file_path, is_in_archive=True)
                        all_entries.extend(entries)
                        self.total_messages_loaded += len(entries)

                    except KeyError:
                        failed_files.append((filename, "File not found in archive."))
                    except Exception as e:
                        failed_files.append((filename, str(e)))
                    
                    if self.should_stop: break

                self.total_progress_update.emit(total_files)

        except (zipfile.BadZipFile, FileNotFoundError) as e:
            self.error_occurred.emit(f"Error opening archive: {e}")
            return [], []
        return all_entries, failed_files

    def _process_single_file(self, file_path_to_process, is_in_archive=False):
        if not is_in_archive:
            self.total_progress_config.emit(0, 1)
            self.total_progress_update.emit(0)

        path_to_parse = file_path_to_process
        try:
            if file_path_to_process.endswith('.gz'):
                self.file_progress_config.emit(0, 0) # Indeterminate for decompression
                uncompressed_filename = os.path.basename(file_path_to_process)[:-3]
                path_to_parse = os.path.join(self.temp_dir, uncompressed_filename)
                with gzip.open(file_path_to_process, 'rb') as f_in, open(path_to_parse, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)

            file_size = os.path.getsize(path_to_parse)
            self.file_progress_config.emit(0, file_size)

            detected_encoding = 'utf-8' # Default
            try:
                with open(path_to_parse, 'r', encoding='utf-8') as f:
                    return self._parse_log_from_iterator(f, path_to_parse, file_size)
            except UnicodeDecodeError:
                self.status_update.emit("Decoding error, trying fallback...", os.path.basename(path_to_parse))
                for enc in self.encodings_to_try[1:]:
                    if self.should_stop: return []
                    try:
                        with open(path_to_parse, 'r', encoding=enc) as f:
                            detected_encoding = enc
                            return self._parse_log_from_iterator(f, path_to_parse, file_size)
                    except UnicodeDecodeError:
                        continue
                raise IOError(f"Could not decode {os.path.basename(path_to_parse)}.")

        except Exception as e:
            raise Exception(f"Error processing {os.path.basename(file_path_to_process)}: {e}")
        finally:
            if not is_in_archive:
                self.total_progress_update.emit(1)

    def _parse_log_from_iterator(self, file_iterator, source_name, file_size):
        entry_pattern = re.compile(
            r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+'
            r'(INFO|WARN|ERROR|DEBUG)\s+'
            r'\[(.*?)\]\s+'
            r'(.*)'
        )
        log_entries = []
        line_number = 0
        bytes_read = 0
        is_filtering_active = bool(self.active_filter_loggers)
        total_messages = 0

        for line_text in file_iterator:
            if self.should_stop: break
            line_number += 1
            bytes_read += len(line_text.encode('utf-8', errors='ignore'))

            if line_number % 500 == 0:
                self.file_progress_update.emit(bytes_read)

            match = entry_pattern.match(line_text)
            if match:
                # If filtering is active, check if the logger name starts with any of the filter prefixes
                if is_filtering_active:
                    logger_name_from_log = match.group(3)
                    if not any(logger_name_from_log.startswith(prefix) for prefix in self.active_filter_loggers):
                        continue  # Skip this line as it doesn't match the filter
                dt_str, lvl, lgr, msg_content = match.groups()
                parsed_dt = datetime.min
                try:
                    parsed_dt = datetime.strptime(dt_str, self.datetime_format_for_parsing)
                except ValueError:
                    pass

                # Create a metadata-only entry
                entry = {
                    'datetime': dt_str,
                    'datetime_obj': parsed_dt,
                    'log_level': lvl,
                    'logger_name': lgr,
                    'source_file_path': source_name, # Full path for on-demand loading
                    'line_number': line_number, # Start line of the entry
                    'message_preview': msg_content.strip() # A small preview
                }
                log_entries.append(entry)
                total_messages += 1
                if total_messages % 1000 == 0:
                    self.message_count_update.emit(total_messages, self.total_messages_loaded + total_messages)

        self.file_progress_update.emit(file_size) # Final update for this file
        self.message_count_update.emit(total_messages, self.total_messages_loaded + total_messages) # Final count for this file
        return log_entries

    def stop(self):
        self.should_stop = True
