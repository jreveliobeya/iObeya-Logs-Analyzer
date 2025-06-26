#!/usr/bin/env python3
import sys
import re
import os
import shutil
import tempfile
import locale
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtCore import QSettings
import pandas as pd

# Local imports
from timeline_canvas import TimelineCanvas
from log_processing import LogLoaderThread
from ui_widgets import SortableTreeWidgetItem, LoadingDialog, VirtualTreeWidget, SearchWidget
from statistics_dialog import StatsDialog
from app_logic import AppLogic # Added import
from archive_selection_dialog import ArchiveSelectionDialog
from filter_dialog import FilterManagementDialog

class LogAnalyzerApp(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Timeline Log Analyzer v6.0")
        self.resize(1600, 1000)
        self.log_entries_full = pd.DataFrame() # Initialize as DataFrame
        self.message_types_data_for_list = {}
        self.selected_log_levels = {'INFO': False, 'WARN': False, 'ERROR': False, 'DEBUG': False}
        # self.top_loggers_for_selection_buttons = [] # This will be dynamically generated now
        self.stats_dialog = None
        self.timeline_min_num_full_range = 0
        self.timeline_max_num_full_range = 100
        self.slider_scale_factor = 10000
        self._is_batch_updating_ui = False
        self.loading_dialog = None
        self.loader_thread = None
        self.current_loaded_source_name = "No file loaded"
        self.loaded_source_type = None
        self.current_temp_dir = None
        self.filter_dialog = None

        # --- Persistent Settings ---
        self.settings = QSettings("MyCompany", "TimelineLogAnalyzer")
        self.last_log_directory = os.path.expanduser("~")
        self.last_filter_directory = os.path.expanduser("~")
        self.recent_files = []
        self.MAX_RECENT_FILES = 10


        self.app_logic = AppLogic(self) # Initialize AppLogic first

        self.message_type_search_timer = QtCore.QTimer()
        self.message_type_search_timer.setSingleShot(True)
        # NOW self.app_logic exists for the connection
        self.message_type_search_timer.timeout.connect(self.app_logic.apply_message_type_filter) 

        self.setup_ui()
        self.app_logic.reset_all_filters_and_view(initial_load=True)
        self.load_settings() 

    def _enter_batch_update(self):
        self._is_batch_updating_ui = True

    def _exit_batch_update(self):
        self._is_batch_updating_ui = False

    def setup_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QtWidgets.QVBoxLayout(central_widget)

        self.create_menu_bar()
        self.create_toolbar()

        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        timeline_section_widget = self.create_timeline_section_with_sliders()
        main_splitter.addWidget(timeline_section_widget)

        bottom_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        message_types_panel = self.create_message_types_panel()
        bottom_splitter.addWidget(message_types_panel)
        right_panel = self.create_right_panel()
        bottom_splitter.addWidget(right_panel)
        bottom_splitter.setStretchFactor(0, 1);
        bottom_splitter.setStretchFactor(1, 2)

        main_splitter.addWidget(bottom_splitter)
        main_splitter.setStretchFactor(0, 1);
        main_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(main_splitter)

    def create_toolbar(self):
        toolbar = self.addToolBar("File")
        toolbar.setMovable(False);
        toolbar.setFloatable(False)

        toolbar.addSeparator()
        reset_view_action = QtWidgets.QAction("Reset View", self)
        reset_view_action.setToolTip("Reset all filters and timeline zoom")
        reset_view_action.triggered.connect(lambda: self.app_logic.reset_all_filters_and_view(initial_load=False))
        toolbar.addAction(reset_view_action)
        toolbar.addSeparator()

        export_csv_action = QtWidgets.QAction("Export CSV", self)
        export_csv_action.setToolTip("Export aggregated timeline data for selected types to CSV")
        export_csv_action.triggered.connect(self.app_logic.export_timeline_data_to_csv)
        toolbar.addAction(export_csv_action)

        toolbar.addSeparator()

        # --- Filter Menu ---
        self.filter_menu_button = QtWidgets.QToolButton()
        self.filter_menu_button.setText("Filters")
        self.filter_menu_button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        filter_menu = QtWidgets.QMenu(self.filter_menu_button)
        self.filter_menu_button.setMenu(filter_menu)

        manage_filters_action = QtWidgets.QAction("Manage/Apply Filter...", self)
        manage_filters_action.triggered.connect(self.show_filter_dialog)
        filter_menu.addAction(manage_filters_action)

        save_filter_action = QtWidgets.QAction("Save Current Selection as Filter...", self)
        save_filter_action.triggered.connect(self.app_logic.save_current_selection_as_filter)
        filter_menu.addAction(save_filter_action)

        filter_menu.addSeparator()

        clear_filter_action = QtWidgets.QAction("Clear Active Filter", self)
        clear_filter_action.triggered.connect(self.app_logic.clear_active_filter)
        filter_menu.addAction(clear_filter_action)

        toolbar.addWidget(self.filter_menu_button)

        self.active_filter_label = QtWidgets.QLabel("Filter: None")
        self.active_filter_label.setToolTip("The pre-load filter currently in effect.")
        self.active_filter_label.setStyleSheet("padding-left: 5px; padding-right: 5px; border: 1px solid #555;")
        toolbar.addWidget(self.active_filter_label)


        toolbar.addSeparator()

        summary_widget = QtWidgets.QWidget()
        summary_layout = QtWidgets.QHBoxLayout(summary_widget)
        summary_layout.setContentsMargins(8, 4, 8, 4);
        summary_layout.setSpacing(10)

        self.period_label = QtWidgets.QLabel("No log loaded")
        self.period_label.setStyleSheet(
            "QLabel { background-color: #E8F5E8; padding: 4px 8px; border-radius: 4px; font-family: monospace; font-size: 11px; }")
        summary_layout.addWidget(QtWidgets.QLabel("📅"));
        summary_layout.addWidget(self.period_label)

        self.stats_button = QtWidgets.QPushButton("📊")
        self.stats_button.setToolTip("Show Global Statistics");
        self.stats_button.setFixedSize(24, 24)
        self.stats_button.setStyleSheet(
            "QPushButton { font-size: 14px; border: none; padding: 0px; } QPushButton:hover { background-color: #e0e0e0; }")
        self.stats_button.clicked.connect(self.show_stats_panel)
        summary_layout.addWidget(self.stats_button)

        self.total_label = QtWidgets.QLabel("0 entries")
        self.total_label.setStyleSheet(
            "QLabel { background-color: #E3F2FD; padding: 4px 8px; border-radius: 4px; font-weight: bold; }")
        summary_layout.addWidget(self.total_label)

        btn_style = "QPushButton {{ background-color: {bg}; color: {fg}; border: 1px solid {fg}; padding: 2px 6px; border-radius: 3px; font-weight: bold; font-size: 10px; }} QPushButton:hover {{ background-color: {bg_hover}; }}"
        self.error_btn = QtWidgets.QPushButton("ERROR: 0");
        self.error_btn.setStyleSheet(btn_style.format(bg='#FFEBEE', fg='#D32F2F', bg_hover='#FFCDD2'));
        self.error_btn.clicked.connect(lambda: self.app_logic.filter_by_specific_level('ERROR'))
        summary_layout.addWidget(self.error_btn)
        self.warn_btn = QtWidgets.QPushButton("WARN: 0");
        self.warn_btn.setStyleSheet(btn_style.format(bg='#FFF3E0', fg='#F57C00', bg_hover='#FFE0B2'));
        self.warn_btn.clicked.connect(lambda: self.app_logic.filter_by_specific_level('WARN'))
        summary_layout.addWidget(self.warn_btn)
        self.info_btn = QtWidgets.QPushButton("INFO: 0");
        self.info_btn.setStyleSheet(btn_style.format(bg='#E3F2FD', fg='#1976D2', bg_hover='#BBDEFB'));
        self.info_btn.clicked.connect(lambda: self.app_logic.filter_by_specific_level('INFO'))
        summary_layout.addWidget(self.info_btn)
        self.debug_btn = QtWidgets.QPushButton("DEBUG: 0");
        self.debug_btn.setStyleSheet(btn_style.format(bg='#F3E5F5', fg='#7B1FA2', bg_hover='#E1BEE7'));
        self.debug_btn.clicked.connect(lambda: self.app_logic.filter_by_specific_level('DEBUG'))
        summary_layout.addWidget(self.debug_btn)
        summary_layout.addStretch();

        summary_widget.setStyleSheet(
            "QWidget { background-color: #f9f9f9; border: 1px solid #ddd; border-radius: 6px; }")
        summary_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed);
        summary_widget.setMaximumHeight(40);
        toolbar.addWidget(summary_widget)

    def create_timeline_section_with_sliders(self):
        timeline_section_widget = QtWidgets.QWidget()
        section_layout = QtWidgets.QVBoxLayout(timeline_section_widget)
        section_layout.setContentsMargins(0, 0, 0, 0);
        section_layout.setSpacing(2)

        controls_widget = QtWidgets.QWidget()
        controls_layout = QtWidgets.QHBoxLayout(controls_widget)
        controls_layout.setContentsMargins(5, 2, 5, 2)
        controls_layout.addWidget(QtWidgets.QLabel("Time Granularity:"))
        self.granularity_combo = QtWidgets.QComboBox()
        self.granularity_combo.addItems(['minute', 'hour', 'day', 'week'])
        self.granularity_combo.setCurrentText('minute')
        self.granularity_combo.currentTextChanged.connect(self.on_granularity_changed)
        controls_layout.addWidget(self.granularity_combo)
        controls_layout.addStretch()
        section_layout.addWidget(controls_widget)

        self.timeline_canvas = TimelineCanvas()
        self.timeline_canvas.bar_clicked.connect(self.app_logic.on_timeline_bar_clicked)
        self.timeline_canvas.time_range_updated.connect(self.update_timeline_sliders_range)
        section_layout.addWidget(self.timeline_canvas)

        slider_widget = QtWidgets.QWidget()
        slider_layout = QtWidgets.QGridLayout(slider_widget)
        slider_layout.setContentsMargins(5, 0, 5, 5);
        slider_layout.setSpacing(5)

        self.pan_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.pan_slider.setMinimum(0);
        self.pan_slider.setMaximum(self.slider_scale_factor)
        self.pan_slider.setPageStep(int(self.slider_scale_factor * 0.1))
        self.pan_slider.valueChanged.connect(self.on_slider_value_changed)
        self.pan_slider.setToolTip("Pan Timeline")

        self.zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.zoom_slider.setMinimum(10);
        self.zoom_slider.setMaximum(self.slider_scale_factor)
        self.zoom_slider.setValue(self.slider_scale_factor)
        self.zoom_slider.setPageStep(int(self.slider_scale_factor * 0.1))
        self.zoom_slider.valueChanged.connect(self.on_slider_value_changed)
        self.zoom_slider.setToolTip("Zoom Timeline")

        slider_layout.addWidget(QtWidgets.QLabel("Pan:"), 0, 0);
        slider_layout.addWidget(self.pan_slider, 0, 1)
        slider_layout.addWidget(QtWidgets.QLabel("Zoom:"), 1, 0);
        slider_layout.addWidget(self.zoom_slider, 1, 1)
        section_layout.addWidget(slider_widget)
        return timeline_section_widget

    def create_message_types_panel(self):
        panel = QtWidgets.QWidget();
        layout = QtWidgets.QVBoxLayout(panel)

        search_layout = QtWidgets.QHBoxLayout()
        search_layout.addWidget(QtWidgets.QLabel("🔍"))
        self.message_type_search_input = QtWidgets.QLineEdit()
        self.message_type_search_input.setPlaceholderText("Search message types...")
        self.message_type_search_input.textChanged.connect(self.app_logic.on_message_type_search_changed_debounced)
        search_layout.addWidget(self.message_type_search_input)
        self.message_type_search_clear_btn = QtWidgets.QPushButton("✕")
        self.message_type_search_clear_btn.setFixedSize(24,24)
        self.message_type_search_clear_btn.setToolTip("Clear message type search")
        self.message_type_search_clear_btn.clicked.connect(self.message_type_search_input.clear)
        search_layout.addWidget(self.message_type_search_clear_btn)
        layout.addLayout(search_layout)


        title_layout = QtWidgets.QHBoxLayout();
        title_layout.addWidget(QtWidgets.QLabel("<b>Message Types</b>"));
        title_layout.addStretch()
        self.select_top5_btn = QtWidgets.QPushButton("Top 5");
        self.select_top5_btn.clicked.connect(self.app_logic.select_top5_message_types)
        self.select_top10_btn = QtWidgets.QPushButton("Top 10");
        self.select_top10_btn.clicked.connect(self.app_logic.select_top10_message_types)
        self.select_all_visible_types_btn = QtWidgets.QPushButton("Sel. All Vis.");
        self.select_all_visible_types_btn.setToolTip("Select all currently visible (non-hidden) message types")
        self.select_all_visible_types_btn.clicked.connect(
            lambda: self.app_logic.set_check_state_for_visible_types(QtCore.Qt.Checked))
        self.deselect_all_visible_types_btn = QtWidgets.QPushButton("Desel. All"); 
        self.deselect_all_visible_types_btn.setToolTip("Deselect all message types") 
        self.deselect_all_visible_types_btn.clicked.connect(
            lambda: self.app_logic.set_check_state_for_all_types(QtCore.Qt.Unchecked))
        for btn in [self.select_top5_btn, self.select_top10_btn, self.select_all_visible_types_btn,
                    self.deselect_all_visible_types_btn]: title_layout.addWidget(btn)
        layout.addLayout(title_layout)

        self.message_types_tree = QtWidgets.QTreeWidget()
        self.message_types_tree.setHeaderLabels(['Message Type', 'Count']);
        self.message_types_tree.setSortingEnabled(True)
        self.message_types_tree.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        self.message_types_tree.itemChanged.connect(self.app_logic.on_message_type_item_changed)
        header = self.message_types_tree.header();
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch);
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.message_types_tree.sortByColumn(1, QtCore.Qt.DescendingOrder)
        layout.addWidget(self.message_types_tree)
        return panel

    def create_right_panel(self):
        right_widget = QtWidgets.QWidget();
        layout = QtWidgets.QVBoxLayout(right_widget)

        self.search_widget = SearchWidget();
        self.search_widget.search_changed.connect(self.app_logic.on_search_changed)
        layout.addWidget(self.search_widget)

        layout.addWidget(QtWidgets.QLabel("<b>Messages in Selected Time Interval</b>"))
        self.selected_messages_list = VirtualTreeWidget()
        self.selected_messages_list.setHeaderLabels(['Time', 'Level', 'Logger', 'Message'])
        self.selected_messages_list.itemSelectionChanged.connect(self.app_logic.on_message_selected)
        self.selected_messages_list.current_sort_column = 0;
        self.selected_messages_list.current_sort_order = QtCore.Qt.AscendingOrder
        self.selected_messages_list.header().setSortIndicator(0, QtCore.Qt.AscendingOrder)
        layout.addWidget(self.selected_messages_list)

        layout.addWidget(QtWidgets.QLabel("<b>Message Details</b>"))
        self.details_text = QtWidgets.QTextEdit();
        self.details_text.setReadOnly(True)
        self.details_text.setFontFamily("monospace");
        layout.addWidget(self.details_text)
        return right_widget

    def _initiate_loading_process(self, file_path=None, archive_path=None, selected_files=None):
        path_to_add = file_path if file_path else archive_path
        if path_to_add:
            self.add_to_recent_files(path_to_add)

        if self.loader_thread and self.loader_thread.isRunning():
            QtWidgets.QMessageBox.warning(self, "Loading in Progress", "A file or archive is already being loaded.")
            return

        self._cleanup_temp_dir()  # Clean up old temp dir before starting new load
        self.current_temp_dir = tempfile.mkdtemp(prefix='log_analyzer_')

        if archive_path:
            self.current_loaded_source_name = os.path.basename(archive_path)
            self.loaded_source_type = "archive"
        elif file_path:
            self.current_loaded_source_name = os.path.basename(file_path)
            self.loaded_source_type = "single_file"
        else:
            self.current_loaded_source_name = "Unknown Source"
            self.loaded_source_type = None

        self.loading_dialog = LoadingDialog(self)

        # Pass the active filter name to the dialog
        active_filter_name = self.app_logic.get_active_filter_name()
        self.loading_dialog.set_filter_name(active_filter_name)

        self.loader_thread = LogLoaderThread(
            file_path=file_path,
            archive_path=archive_path,
            datetime_format=self.app_logic.datetime_format_for_parsing,
            selected_files_from_archive=selected_files,
            temp_dir=self.current_temp_dir,
            active_filter_loggers=self.app_logic.active_filter_loggers
        )

        # Connect the new signals to the dialog's slots
        self.loader_thread.status_update.connect(self.loading_dialog.update_status)
        self.loader_thread.file_progress_config.connect(self.loading_dialog.set_progress_range)
        self.loader_thread.file_progress_update.connect(self.loading_dialog.set_progress_value)
        self.loader_thread.total_progress_config.connect(self.loading_dialog.set_total_progress_range)
        self.loader_thread.total_progress_update.connect(self.loading_dialog.set_total_progress_value)
        self.loader_thread.message_count_update.connect(self.loading_dialog.update_message_count)
        
        self.loader_thread.finished_loading.connect(self.on_log_data_loaded)
        self.loader_thread.error_occurred.connect(self.on_load_error)
        self.loader_thread.finished.connect(self.on_load_finished)

        self.loading_dialog.show()
        self.loader_thread.start()

    @QtCore.pyqtSlot(float, float)
    def update_timeline_sliders_range(self, min_num, max_num):
        self._enter_batch_update()
        self.timeline_min_num_full_range = min_num;
        self.timeline_max_num_full_range = max_num

        sliders_enabled = (
                    self.timeline_max_num_full_range > self.timeline_min_num_full_range + 1e-9)
        self.pan_slider.setEnabled(sliders_enabled);
        self.zoom_slider.setEnabled(sliders_enabled)

        if sliders_enabled:
            self.pan_slider.setMinimum(0);
            self.pan_slider.setMaximum(self.slider_scale_factor);
            self.pan_slider.setValue(0)
            self.zoom_slider.setMinimum(10);
            self.zoom_slider.setMaximum(self.slider_scale_factor);
            self.zoom_slider.setValue(self.slider_scale_factor)
        else:
            self.pan_slider.setMinimum(0);
            self.pan_slider.setMaximum(0)
            self.zoom_slider.setMinimum(10);
            self.zoom_slider.setMaximum(self.slider_scale_factor);
            self.zoom_slider.setValue(self.slider_scale_factor)
        self._exit_batch_update()
        if not self._is_batch_updating_ui: self._apply_sliders_to_timeline_view()

    def on_slider_value_changed(self):
        if not self._is_batch_updating_ui:
            self._apply_sliders_to_timeline_view()

    def _apply_sliders_to_timeline_view(self):
        if self._is_batch_updating_ui: return
        if self.timeline_min_num_full_range is None or self.timeline_max_num_full_range is None: return

        if self.timeline_max_num_full_range <= self.timeline_min_num_full_range:
            center_point = self.timeline_min_num_full_range;
            tiny_width = 0.0001
            self.timeline_canvas.set_time_window_from_sliders(center_point - tiny_width / 2,
                                                              center_point + tiny_width / 2)
            return

        total_data_span = self.timeline_max_num_full_range - self.timeline_min_num_full_range
        zoom_value = max(self.zoom_slider.value(), 1)
        zoom_ratio = zoom_value / self.slider_scale_factor
        view_width = total_data_span * zoom_ratio
        min_view_width = max(total_data_span * (self.zoom_slider.minimum() / self.slider_scale_factor),
                             1e-5)
        view_width = max(view_width, min_view_width)

        pannable_range_num = total_data_span - view_width
        if pannable_range_num < 0: pannable_range_num = 0

        pan_ratio = self.pan_slider.value() / self.slider_scale_factor
        view_start_offset_from_min = pannable_range_num * pan_ratio
        view_start_num = self.timeline_min_num_full_range + view_start_offset_from_min
        view_end_num = view_start_num + view_width

        view_start_num = max(view_start_num, self.timeline_min_num_full_range)
        view_end_num = min(view_end_num, self.timeline_max_num_full_range)

        if view_start_num + view_width > self.timeline_max_num_full_range:
            view_start_num = self.timeline_max_num_full_range - view_width
            view_start_num = max(view_start_num, self.timeline_min_num_full_range)

        if view_start_num < view_end_num - 1e-9:
            self.timeline_canvas.set_time_window_from_sliders(view_start_num, view_end_num)

    def load_log_file(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Log File", self.last_log_directory, "Log Files (*.log *.txt *.log.gz);;All Files (*)")
        if not file_path: return
        self.last_log_directory = os.path.dirname(file_path)
        self._initiate_loading_process(file_path=file_path)

    def load_log_archive(self):
        archive_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Log Archive", self.last_log_directory, "Archive Files (*.zip)")
        if not archive_path:
            return

        self.last_log_directory = os.path.dirname(archive_path)
        dialog = ArchiveSelectionDialog(archive_path, self)
        if dialog.exec_():
            selected_files = dialog.get_selected_files()
            if selected_files:
                self._initiate_loading_process(archive_path=archive_path, selected_files=selected_files)
            else:
                QtWidgets.QMessageBox.information(self, "No Files Selected", "You did not select any files to load.")

    def on_log_data_loaded(self, log_entries_df, failed_files_summary):
        if self.loading_dialog:
            self.loading_dialog.update_status("Finalizing...", "Displaying results.")
            self.loading_dialog.accept()
        self.log_entries_full = log_entries_df
        self.setWindowTitle(f"Timeline Log Analyzer - {self.current_loaded_source_name}")

        if hasattr(self.selected_messages_list, 'set_all_items_data'):
            self.selected_messages_list.set_all_items_data([])
        self.details_text.clear()

        if self.stats_dialog and self.stats_dialog.isVisible():
            self.stats_dialog.close();
            self.stats_dialog = None

        self.timeline_canvas.set_full_log_data(self.log_entries_full)
        self.app_logic.reset_all_filters_and_view(initial_load=True) # Call on app_logic
        self.app_logic.select_top10_message_types() # Automatically select top 10 message types
        self.loading_dialog.accept() # Close the loading dialog

        if not self.log_entries_full.empty and not self._is_batch_updating_ui:
             self._trigger_timeline_update_from_selection()


        if failed_files_summary:
            error_details = "\n".join(
                [f"- {fname}: {reason}" for fname, reason in failed_files_summary[:15]])
            if len(failed_files_summary) > 15: error_details += f"\n...and {len(failed_files_summary) - 15} more."
            QtWidgets.QMessageBox.warning(self, "Archive Loading Issues",
                                          f"Some files within the archive could not be processed:\n{error_details}")

        if self.log_entries_full.empty: 
            if not self._is_batch_updating_ui:
                self.timeline_canvas.plot_timeline()
                self.update_timeline_sliders_range(0, 0)
            QtWidgets.QMessageBox.information(self, "No Data Loaded",
                                          "No log entries were found or loaded from the source.")

    def on_load_error(self, error_message: str):
        """Handles errors emitted from the LogLoaderThread."""
        self.reset_app_state_after_error(error_message)

    def reset_app_state_after_error(self, error_message: str):
        """Resets the application state and UI after a loading error."""
        if self.loading_dialog and self.loading_dialog.isVisible():
            self.loading_dialog.reject() # Close if still open

        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop() # Request thread to stop
            if not self.loader_thread.wait(1000): # Wait a bit for graceful exit
                self.loader_thread.terminate() # Force terminate if not stopping
        
        QtWidgets.QMessageBox.critical(self, "Loading Error", str(error_message))

        self._cleanup_temp_dir()  # Clean up temp files on error

        self.log_entries_full = pd.DataFrame() # Clear any partial data
        self.current_loaded_source_name = "Error during load"
        self.setWindowTitle("Timeline Log Analyzer - Error")

        # Reset UI elements via AppLogic
        if hasattr(self, 'app_logic') and self.app_logic:
            self.app_logic.reset_all_filters_and_view(initial_load=True)
        else: # Fallback if app_logic somehow not initialized (should not happen)
            if hasattr(self.selected_messages_list, 'set_all_items_data'):
                 self.selected_messages_list.set_all_items_data([])
            if hasattr(self, 'details_text'): self.details_text.clear()
            if hasattr(self, 'timeline_canvas'): self.timeline_canvas.clear_plot()
            if hasattr(self, 'message_types_tree'): self.message_types_tree.clear()
            # Add other direct UI resets if necessary as a fallback

    def on_load_finished(self):
        """Called when the LogLoaderThread finishes, regardless of success or error."""
        if self.loading_dialog and self.loading_dialog.isVisible():
            self.loading_dialog.accept() # Ensure dialog is closed
        # Further cleanup if loader_thread instance needs to be cleared, etc.
        # For now, just ensure dialog is closed.



    def _rebuild_message_types_data_and_list(self, select_all_visible=False):
        if self.log_entries_full.empty: return

        # Filter by selected log levels first
        selected_levels = [level for level, is_selected in self.selected_log_levels.items() if is_selected]
        if not selected_levels: return

        filtered_df = self.log_entries_full[self.log_entries_full['log_level'].isin(selected_levels)]
        if filtered_df.empty: return

        # Get counts of logger_name
        logger_counts = filtered_df['logger_name'].value_counts()

        # Sort by count descending
        sorted_loggers = logger_counts.sort_values(ascending=False).index.tolist()

        current_checked_texts = set()
        if not select_all_visible:
            for i in range(self.message_types_tree.topLevelItemCount()):
                item = self.message_types_tree.topLevelItem(i)
                if item.checkState(0) == QtCore.Qt.Checked:
                    current_checked_texts.add(item.text(0))

        self.message_types_tree.blockSignals(True);
        self.message_types_tree.clear();
        items_to_add = []
        for logger_name, data in self.message_types_data_for_list.items():
            if data['count'] > 0:
                item = SortableTreeWidgetItem([logger_name, str(data['count'])])
                item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                item.setCheckState(0, QtCore.Qt.Checked if (
                            select_all_visible or logger_name in current_checked_texts) else QtCore.Qt.Unchecked)
                items_to_add.append(item)
        if items_to_add: self.message_types_tree.addTopLevelItems(items_to_add)

        current_sort_col = self.message_types_tree.sortColumn()
        current_sort_order = self.message_types_tree.header().sortIndicatorOrder()
        self.message_types_tree.sortItems(current_sort_col if current_sort_col != -1 else 1,
                                          current_sort_order if current_sort_col != -1 else QtCore.Qt.DescendingOrder)
        self.message_types_tree.blockSignals(False)
        self._apply_message_type_filter()

    def on_message_type_item_changed(self, item, column):
        if not self._is_batch_updating_ui:
            self._trigger_timeline_update_from_selection()

    # Changed: New method to set check state for ALL types (hidden or not)
    def set_check_state_for_all_types(self, check_state):
        if self._is_batch_updating_ui: return
        self._enter_batch_update()
        self.message_types_tree.blockSignals(True)
        for i in range(self.message_types_tree.topLevelItemCount()):
            item = self.message_types_tree.topLevelItem(i)
            # Operates on all items, regardless of hidden status
            if item.checkState(0) != check_state:
                item.setCheckState(0, check_state)
        self.message_types_tree.blockSignals(False)
        self._exit_batch_update()
        self._trigger_timeline_update_from_selection()

    # Changed: Renamed and modified to only act on VISIBLE (non-hidden) types
    def set_check_state_for_visible_types(self, check_state):
        if self._is_batch_updating_ui: return
        self._enter_batch_update()
        self.message_types_tree.blockSignals(True)
        for i in range(self.message_types_tree.topLevelItemCount()):
            item = self.message_types_tree.topLevelItem(i)
            if not item.isHidden(): # Only operate on non-hidden items
                if item.checkState(0) != check_state: item.setCheckState(0, check_state)
        self.message_types_tree.blockSignals(False)
        self._exit_batch_update()
        self._trigger_timeline_update_from_selection()

    def _trigger_timeline_update_from_selection(self):
        if self._is_batch_updating_ui: return
        selected_types = set()
        for i in range(self.message_types_tree.topLevelItemCount()):
            item = self.message_types_tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                 selected_types.add(item.text(0))

        self.timeline_canvas.update_display_config(selected_types, self.granularity_combo.currentText())

    def on_granularity_changed(self):
        if self._is_batch_updating_ui: return
        self._enter_batch_update()
        self.pan_slider.setValue(0);
        self.zoom_slider.setValue(self.slider_scale_factor)
        self._exit_batch_update()
        self._trigger_timeline_update_from_selection()

    def reset_all_filters_and_view(self, initial_load=False):
        self._enter_batch_update()
        try:
            self.selected_log_levels = {'INFO': True, 'WARN': True, 'ERROR': True, 'DEBUG': True}
        

            if hasattr(self, 'message_type_search_input'):
                self.message_type_search_input.blockSignals(True)
                self.message_type_search_input.clear()
                self.message_type_search_input.blockSignals(False)

            self._rebuild_message_types_data_and_list(select_all_visible=True)

            if hasattr(self, 'pan_slider') and hasattr(self, 'zoom_slider'):
                self.pan_slider.setValue(0);
                self.zoom_slider.setValue(self.slider_scale_factor)

            if hasattr(self, 'granularity_combo'):
                self.granularity_combo.blockSignals(True)
                default_granularity = 'minute'
                if self.log_entries_full and self.loaded_source_type:
                    if self.loaded_source_type == "archive":
                        default_granularity = 'day'
                    elif self.loaded_source_type == "single_file":
                        default_granularity = 'hour'
                self.granularity_combo.setCurrentText(default_granularity)
                self.granularity_combo.blockSignals(False)

            if hasattr(self, 'search_widget'): self.search_widget.clear_search()
            if hasattr(self.selected_messages_list,
                       'set_all_items_data'): self.selected_messages_list.set_all_items_data([])
            if hasattr(self, 'details_text'): self.details_text.clear()
        finally:
            self._exit_batch_update()

        if initial_load and self.log_entries_full.empty:
            current_granularity = self.granularity_combo.currentText() if hasattr(self, 'granularity_combo') else 'minute'
            self.timeline_canvas.update_display_config(set(), current_granularity)
            self.update_timeline_sliders_range(0, 0)
        elif not self.log_entries_full.empty:
            self._trigger_timeline_update_from_selection()
        else:
            current_granularity = self.granularity_combo.currentText() if hasattr(self, 'granularity_combo') else 'minute'
            self.timeline_canvas.update_display_config(set(), current_granularity)
            self.update_timeline_sliders_range(0, 0)





    def set_current_temp_dir(self, path):
        self.current_temp_dir = path

    def _cleanup_temp_dir(self):
        if self.current_temp_dir and os.path.exists(self.current_temp_dir):
            shutil.rmtree(self.current_temp_dir, ignore_errors=True)
        self.current_temp_dir = None

    def show_filter_dialog(self):
        if self.filter_dialog is None:
            self.filter_dialog = FilterManagementDialog(self)
            self.filter_dialog.filter_selected.connect(self.app_logic.apply_filter_from_dialog)

        self.filter_dialog.set_initial_directory(self.last_filter_directory)
        if self.filter_dialog.exec_():
            # If a directory was selected in the dialog, save it for next time
            new_dir = self.filter_dialog.get_selected_directory()
            if new_dir:
                self.last_filter_directory = new_dir

    def show_stats_panel(self):
        if self.log_entries_full.empty:
            QtWidgets.QMessageBox.information(self, "No Data", "Please load a log file first.")
            return
        if self.stats_dialog is None or not self.stats_dialog.isVisible():
            self.stats_dialog = StatsDialog(self.log_entries_full, self)
            self.stats_dialog.show()
        else:
            self.stats_dialog.activateWindow()

    def set_current_temp_dir(self, path):
        self.current_temp_dir = path

    def _cleanup_temp_dir(self):
        if self.current_temp_dir and os.path.exists(self.current_temp_dir):
            shutil.rmtree(self.current_temp_dir, ignore_errors=True)
        self.current_temp_dir = None

    def closeEvent(self, event):
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.stop()
            if not self.loader_thread.wait(1500):
                self.loader_thread.terminate()
        self._cleanup_temp_dir()  # Clean up on exit
        self.save_settings()
        if self.loading_dialog and self.loading_dialog.isVisible(): self.loading_dialog.reject()
        if self.stats_dialog and self.stats_dialog.isVisible(): self.stats_dialog.close()
        super().closeEvent(event)

    def save_settings(self):
        """Saves application state to QSettings."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.setValue("last_log_directory", self.last_log_directory)
        self.settings.setValue("last_filter_directory", self.last_filter_directory)
        self.settings.setValue("active_filter_name", self.app_logic.active_filter_name)
        # QSettings handles lists better than sets
        self.settings.setValue("active_filter_loggers", list(self.app_logic.active_filter_loggers))
        self.settings.setValue("recent_files", self.recent_files)

    def load_settings(self):
        """Loads application state from QSettings."""
        if self.settings.value("geometry"):
            self.restoreGeometry(self.settings.value("geometry"))
        if self.settings.value("windowState"):
            self.restoreState(self.settings.value("windowState"))

        self.last_log_directory = self.settings.value("last_log_directory", os.path.expanduser("~"))
        self.last_filter_directory = self.settings.value("last_filter_directory", os.path.expanduser("~"))

        filter_name = self.settings.value("active_filter_name", "None")
        filter_loggers = self.settings.value("active_filter_loggers", [])
        if filter_name != "None" and filter_loggers:
            self.app_logic.apply_filter_from_dialog(filter_name, filter_loggers, silent=True)

        self.recent_files = self.settings.value("recent_files", []) or []
        self.update_recent_files_menu()

    def create_menu_bar(self):
        """Creates the main menu bar for the application."""
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        load_file_action = QtWidgets.QAction("Load Log File...", self)
        load_file_action.triggered.connect(self.load_log_file)
        file_menu.addAction(load_file_action)

        load_archive_action = QtWidgets.QAction("Load Log Archive...", self)
        load_archive_action.triggered.connect(self.load_log_archive)
        file_menu.addAction(load_archive_action)

        file_menu.addSeparator()

        self.recent_files_menu = file_menu.addMenu("Recent Files")

        file_menu.addSeparator()

        quit_action = QtWidgets.QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        help_menu = menu_bar.addMenu("&Help")
        about_action = QtWidgets.QAction("About...", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)

    def add_to_recent_files(self, path):
        """Adds a file path to the recent files list."""
        if path in self.recent_files:
            self.recent_files.remove(path)
        self.recent_files.insert(0, path)
        self.recent_files = self.recent_files[:self.MAX_RECENT_FILES]
        self.update_recent_files_menu()

    def update_recent_files_menu(self):
        """Updates the 'Recent Files' menu with the current list of files."""
        if not hasattr(self, 'recent_files_menu'): return
        self.recent_files_menu.clear()
        for path in self.recent_files:
            action = QtWidgets.QAction(os.path.basename(path), self)
            action.setData(path)
            action.setToolTip(path)
            action.triggered.connect(self.open_recent_file)
            self.recent_files_menu.addAction(action)
        self.recent_files_menu.setEnabled(bool(self.recent_files))

    def open_recent_file(self):
        """Opens a file selected from the 'Recent Files' menu."""
        action = self.sender()
        if action:
            path = action.data()
            if not os.path.exists(path):
                QtWidgets.QMessageBox.warning(self, "File Not Found", f"The file {path} could not be found.")
                if path in self.recent_files:
                    self.recent_files.remove(path)
                    self.update_recent_files_menu()
                return

            if path.lower().endswith('.zip'):
                dialog = ArchiveSelectionDialog(path, self)
                if dialog.exec_():
                    selected_files = dialog.get_selected_files()
                    if selected_files:
                        self._initiate_loading_process(archive_path=path, selected_files=selected_files)
            else:
                self._initiate_loading_process(file_path=path)

    def show_about_dialog(self):
        dialog = QtWidgets.QMessageBox(self)
        dialog.setWindowTitle("About Timeline Log Analyzer")
        dialog.setIcon(QtWidgets.QMessageBox.Information)

        title = "<h2 style='text-align:center;'>Timeline Log Analyzer v6.0</h2>"
        copyright_text = "<p style='text-align:center;'>Copyright &copy; 2024 iObeya</p>"
        vibe_text = "<p style='text-align:center;'>100% VibeCoded by JR</p>"
        easter_egg_hint = "<p style='text-align:center; color: #888;'><i>(Psst... try clicking me)</i></p>"

        dialog.setText(f"{title}{copyright_text}{vibe_text}{easter_egg_hint}")
        dialog.setTextFormat(QtCore.Qt.RichText)

        # Easter Egg Logic
        def show_easter_egg():
            dialog.setText(f"{title}{copyright_text}{vibe_text}<hr><p style='text-align:center; font-family: Comic Sans MS, cursive; color: #ff00ff;'><b>\n\n*** VIBE OVERLOAD! ***\n\n</b></p>")
            ok_button = dialog.button(QtWidgets.QMessageBox.Ok)
            if ok_button:
                try:
                    ok_button.clicked.disconnect()
                except TypeError:
                    pass # Already disconnected
                ok_button.clicked.connect(dialog.accept)
                ok_button.setText("Keep Vibing!")

        label = dialog.findChild(QtWidgets.QLabel, "qt_msgbox_label")
        if label:
            class ClickFilter(QtCore.QObject):
                def eventFilter(self, obj, event):
                    if event.type() == QtCore.QEvent.MouseButtonPress:
                        show_easter_egg()
                        return True
                    return False
            
            self.click_filter = ClickFilter(label)
            label.installEventFilter(self.click_filter)

        dialog.setStandardButtons(QtWidgets.QMessageBox.Ok)
        dialog.exec_()


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Timeline Log Analyzer")
    app.setApplicationVersion("6.0")
    app.setOrganizationName("LogAnalyzer")
    try:
        app.setStyle(QtWidgets.QStyleFactory.create('Fusion'))
    except:
        pass
    window = LogAnalyzerApp()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()