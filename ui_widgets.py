#!/usr/bin/env python3
from PyQt5 import QtWidgets, QtGui, QtCore
from datetime import datetime # For VirtualTreeWidget sorting

class SortableTreeWidgetItem(QtWidgets.QTreeWidgetItem):
    def __lt__(self, other):
        tree_widget = self.treeWidget()
        if not tree_widget:
            return self.text(0).lower() < other.text(0).lower()
        column = tree_widget.sortColumn()
        try:
            if column == 1:  # Count column
                return int(self.text(column)) < int(other.text(column))
            val1_str = self.text(column)
            val2_str = other.text(column)
            try:
                val1_num = float(val1_str)
                val2_num = float(val2_str)
                return val1_num < val2_num
            except ValueError:
                return val1_str.lower() < val2_str.lower()
        except (ValueError, AttributeError):
            return self.text(column).lower() < other.text(column).lower()


class LoadingDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Loading Logs")
        self.setMinimumSize(450, 200)
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.CustomizeWindowHint | QtCore.Qt.WindowTitleHint)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(6)

        # --- Filter Info --- 
        self.filter_label = QtWidgets.QLabel("Filter: None")
        self.filter_label.setStyleSheet("font-style: italic; color: #888;")
        layout.addWidget(self.filter_label)

        # --- Main Status --- 
        self.status_label = QtWidgets.QLabel("Initializing...")
        self.status_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.status_label)

        # --- File-specific Progress --- 
        self.detail_label = QtWidgets.QLabel("")
        self.detail_label.setStyleSheet("font-size: 11px; color: #777;")
        layout.addWidget(self.detail_label)
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        layout.addWidget(self.progress_bar)

        # --- Total Progress --- 
        layout.addSpacing(10)
        self.total_status_label = QtWidgets.QLabel("Total Progress")
        layout.addWidget(self.total_status_label)
        self.total_progress_bar = QtWidgets.QProgressBar()
        self.total_progress_bar.setRange(0, 100)
        self.total_progress_bar.setValue(0)
        self.total_progress_bar.setTextVisible(True)
        layout.addWidget(self.total_progress_bar)

        # --- Message Counter --- 
        self.message_counter_label = QtWidgets.QLabel("Messages: 0 | Total: 0")
        self.message_counter_label.setAlignment(QtCore.Qt.AlignRight)
        self.message_counter_label.setStyleSheet("font-size: 11px; color: #777; margin-top: 5px;")
        layout.addWidget(self.message_counter_label)

    def set_filter_name(self, filter_name):
        self.filter_label.setText(f"Filter: {filter_name if filter_name else 'None'}")

    @QtCore.pyqtSlot(int, int)
    def update_message_count(self, current_count, total_count):
        self.message_counter_label.setText(f"Messages: {current_count:,} | Total: {total_count:,}")

    def set_status(self, status_text):
        self.status_label.setText(status_text)

    def set_detail(self, detail_text):
        self.detail_label.setText(detail_text)

    def set_progress_range(self, min_val, max_val):
        self.progress_bar.setRange(min_val, max_val)
        self.progress_bar.setValue(min_val)

    def set_progress_value(self, value):
        self.progress_bar.setValue(value)

    def set_total_progress_range(self, min_val, max_val):
        self.total_progress_bar.setRange(min_val, max_val)
        self.total_progress_bar.setValue(min_val)

    def set_total_progress_value(self, value):
        self.total_progress_bar.setValue(value)

    def update_status(self, status_text, detail_text=""):
        self.set_status(status_text)
        if detail_text:
            self.set_detail(detail_text)


class VirtualTreeWidget(QtWidgets.QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.all_items_data = []  # List of dicts
        self.filtered_items_data = []  # List of dicts (subset of all_items_data)
        self.visible_items = []  # List of QTreeWidgetItem currently in the tree
        self.items_per_page = 1000  # How many items to load at once
        self.current_page = 0
        self.search_filter = ""
        self.current_sort_column = -1  # No sort initially
        self.current_sort_order = QtCore.Qt.AscendingOrder

        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.header().sortIndicatorChanged.connect(self.on_sort_indicator_changed)

    def set_all_items_data(self, items_data):
        self.all_items_data = items_data
        self.apply_search_filter(self.search_filter, force_refresh=True)  # Re-apply current filter or show all

    def _sort_filtered_data(self):
        if not self.filtered_items_data or self.current_sort_column == -1:
            return

        col_idx = self.current_sort_column
        reverse_sort = (self.current_sort_order == QtCore.Qt.DescendingOrder)

        # Define how to get a sortable value from the item data dictionary
        def get_value_for_sort(item_data_dict):
            if col_idx == 0:  # Time column
                # Prefer datetime_obj for sorting if available and valid
                dt_obj = item_data_dict.get('datetime_obj')
                if isinstance(dt_obj, datetime) and dt_obj != datetime.min:
                    return dt_obj
                return item_data_dict.get('datetime', "")  # Fallback to string
            elif col_idx == 1:  # Level column
                return item_data_dict.get('log_level', "").lower()
            elif col_idx == 2:  # Logger column
                return item_data_dict.get('logger_name', "").lower()
            elif col_idx == 3:  # Message column (sort by preview)
                # The message_preview is already a single line.
                return item_data_dict.get('message_preview', "").lower()
            # Fallback for any other unexpected column index, though unlikely with fixed headers
            try:
                return item_data_dict.get(self.headerItem().text(col_idx), "").lower()
            except AttributeError:  # headerItem might not be set
                return ""

        try:
            self.filtered_items_data.sort(key=get_value_for_sort, reverse=reverse_sort)
        except TypeError:  # Fallback for mixed types (e.g. datetime vs string if obj is bad)
            self.filtered_items_data.sort(key=lambda x: str(get_value_for_sort(x)).lower(), reverse=reverse_sort)

    def on_sort_indicator_changed(self, logical_index, order):
        self.current_sort_column = logical_index
        self.current_sort_order = order
        self._sort_filtered_data()
        self.current_page = 0  # Reset to first page
        self._refresh_visible_items()

    def apply_search_filter(self, search_text, force_refresh=False):
        new_search_filter = search_text.lower()
        # Avoid re-filtering if text hasn't changed and data isn't forced,
        # unless previous filter resulted in self.filtered_items_data being a new list (not a slice)
        if not force_refresh and self.search_filter == new_search_filter and \
                self.filtered_items_data is not self.all_items_data:  # Check if it was actually filtered
            return

        self.search_filter = new_search_filter
        if not self.search_filter:
            self.filtered_items_data = self.all_items_data[:]  # Use a slice to ensure it's a mutable copy if needed
        else:
            self.filtered_items_data = [
                item for item in self.all_items_data
                if self.search_filter in item.get('message_preview', '').lower() or \
                   self.search_filter in item.get('logger_name', '').lower()
            ]
        self._sort_filtered_data()  # Re-sort after filtering
        self.current_page = 0  # Reset to first page
        self._refresh_visible_items()

    def _refresh_visible_items(self):
        self.clear()  # Remove all existing QTreeWidgetItems
        self.visible_items = []
        self.current_page = 0  # Reset pagination
        self._load_more_items()

    def _load_more_items(self):
        start_idx = self.current_page * self.items_per_page
        if start_idx >= len(self.filtered_items_data):
            return  # No more items to load

        end_idx = min(start_idx + self.items_per_page, len(self.filtered_items_data))
        new_q_items = []
        for i in range(start_idx, end_idx):
            entry = self.filtered_items_data[i]
            # Create QTreeWidgetItem with display data
            item = QtWidgets.QTreeWidgetItem([ # Using standard QTreeWidgetItem here, Sortable is for the other tree
                entry['datetime'],
                entry['log_level'],
                entry['logger_name'],
                entry['message_preview']  # Use the pre-generated preview
            ])

            # --- Colorization based on log level ---
            log_level = entry.get('log_level', '').upper()
            color = None
            if log_level == 'ERROR':
                color = QtGui.QColor("red")
            elif log_level == 'WARN':
                color = QtGui.QColor("orange")

            if color:
                brush = QtGui.QBrush(color)
                for col in range(item.columnCount()):
                    item.setForeground(col, brush)
            # --- End Colorization ---

            item.setData(0, QtCore.Qt.UserRole, entry)  # Store full entry data
            new_q_items.append(item)

        if new_q_items:
            self.addTopLevelItems(new_q_items)
            self.visible_items.extend(new_q_items)
            self.current_page += 1

    def _on_scroll(self, value):
        scrollbar = self.verticalScrollBar()
        # Load more if near the bottom and more data is available
        if (scrollbar.maximum() > 0 and value >= scrollbar.maximum() * 0.8 and
                len(self.visible_items) < len(self.filtered_items_data)):
            self._load_more_items()


class SearchWidget(QtWidgets.QWidget):
    search_changed = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self);
        layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(QtWidgets.QLabel("🔍"))  # Search icon
        self.search_input = QtWidgets.QLineEdit();
        self.search_input.setPlaceholderText("Search messages and logger names...")
        self.search_input.textChanged.connect(self._on_text_changed_debounced)
        layout.addWidget(self.search_input)
        self.clear_button = QtWidgets.QPushButton("✕");
        self.clear_button.setFixedSize(24, 24)  # Small, square button
        self.clear_button.setToolTip("Clear search");
        self.clear_button.clicked.connect(self.clear_search)
        layout.addWidget(self.clear_button)

        self.search_timer = QtCore.QTimer();
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._emit_search_changed)

    def _on_text_changed_debounced(self, text): self.search_timer.stop(); self.search_timer.start(300)  # 300ms debounce

    def _emit_search_changed(self): self.search_changed.emit(self.search_input.text())

    def clear_search(self): self.search_input.clear()  # This will trigger textChanged -> search_changed