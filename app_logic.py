# app_logic.py
import pandas as pd
from PyQt5 import QtCore, QtWidgets
from collections import Counter
from datetime import datetime
from ui_widgets import SortableTreeWidgetItem
import os
import re
import json
import locale
from search_engine import SearchEngine

class AppLogic(QtCore.QObject):
    def __init__(self, main_window, status_bar):
        super().__init__()
        self.mw = main_window
        self.status_bar = status_bar
        self.datetime_format_for_parsing = '%Y-%m-%d %H:%M:%S'
        self.selected_log_levels = {'INFO': True, 'WARN': True, 'ERROR': True, 'DEBUG': True}
        self.message_types_data_for_list = pd.DataFrame(columns=['logger_name', 'count'])
        self.timeline_filter_active = False
        self.timeline_filter_start_time = None
        self.timeline_filter_end_time = None
        self.current_search_text = ""
        self.active_filter_name = "None"
        self.active_filter_loggers = set()

        # --- Full-Text Search Engine ---
        self.search_engine = SearchEngine()
        self.global_search_query = ""
        self.global_search_timer = QtCore.QTimer()
        self.global_search_timer.setSingleShot(True)
        self.global_search_timer.timeout.connect(self._apply_search_filter_and_update_views)

    def update_indexing_progress(self, current, total):
        """Update the status bar with indexing progress."""
        if self.status_bar:
            progress = (current / total) * 100
            self.status_bar.showMessage(f"Indexing for search... {progress:.0f}%")
            QtCore.QCoreApplication.processEvents() # Force UI update

    def set_full_log_data(self, df, enable_full_text_indexing):
        """Passes the full DataFrame to the timeline canvas and indexes it for search if enabled."""
        if self.mw.timeline_canvas:
            self.mw.timeline_canvas.set_full_log_data(df)

        # Conditionally index data for FTS
        if enable_full_text_indexing and df is not None and not df.empty:
            try:
                self.status_bar.showMessage("Preparing data for search indexing...", 0)
                QtCore.QCoreApplication.processEvents()

                # This pattern must match the one in log_processing.py
                entry_pattern = re.compile(
                    r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+'
                    r'(INFO|WARN|ERROR|DEBUG)\s+'
                    r'\[(.*?)\]\s+' # Logger name in brackets
                    r'(.*)' # The rest of the line is the message
                )

                grouped_by_file = df.groupby('source_file_path')
                messages_to_index = []

                for file_path, group in grouped_by_file:
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                        
                        for index, row in group.iterrows():
                            line_num = row['line_number']
                            if 1 <= line_num <= len(lines):
                                line_content = lines[line_num - 1]
                                match = entry_pattern.match(line_content)
                                if match:
                                    # The full message is the 4th capture group
                                    messages_to_index.append(match.group(4).strip())
                                else:
                                    # Fallback to preview if line format is unexpected
                                    messages_to_index.append(row['message_preview'])
                            else:
                                # Fallback for out-of-bounds line number
                                messages_to_index.append(row['message_preview'])

                    except Exception as e:
                        print(f"[AppLogic] Warning: Could not process file {file_path} for indexing: {e}")
                        # Fallback for all entries in the failed file
                        for index, row in group.iterrows():
                            messages_to_index.append(row['message_preview'])

                self.status_bar.showMessage("Indexing log data for full-text search...", 0)
                QtCore.QCoreApplication.processEvents()
                self.search_engine.index_data(messages_to_index, self.update_indexing_progress)
                self.status_bar.showMessage("Indexing complete.", 3000)

            except Exception as e:
                import traceback
                print(f"Error during FTS indexing preparation: {e}")
                print(traceback.format_exc())
                self.status_bar.showMessage("Error during search indexing.", 5000)
        else:
            self.search_engine.close() # Clear any old index

    def update_status_bar_message(self, message, timeout=0):
        if self.status_bar:
            self.status_bar.showMessage(message, timeout)
            QtWidgets.QApplication.processEvents() # Force UI update

    # ... (reset_all_filters_and_view, _rebuild_message_types_data_and_list)
    # ... (trigger_timeline_update_from_selection, on_granularity_changed, on_slider_value_changed)

    @QtCore.pyqtSlot(float, float)  # <--- DÉCORER COMME SLOT
    def update_timeline_sliders_range(self, min_num, max_num):
        self.mw._enter_batch_update()
        self.mw.timeline_min_num_full_range = min_num
        self.mw.timeline_max_num_full_range = max_num

        sliders_enabled = (self.mw.timeline_max_num_full_range > self.mw.timeline_min_num_full_range + 1e-9)
        if self.mw.pan_slider: self.mw.pan_slider.setEnabled(sliders_enabled)
        if self.mw.zoom_slider: self.mw.zoom_slider.setEnabled(sliders_enabled)

        if sliders_enabled:
            if self.mw.pan_slider:
                self.mw.pan_slider.setMinimum(0)
                self.mw.pan_slider.setMaximum(self.mw.slider_scale_factor)
                self.mw.pan_slider.setValue(0)
            if self.mw.zoom_slider:
                self.mw.zoom_slider.setMinimum(10)
                self.mw.zoom_slider.setMaximum(self.mw.slider_scale_factor)
                self.mw.zoom_slider.setValue(self.mw.slider_scale_factor)
        else:
            if self.mw.pan_slider:
                self.mw.pan_slider.setMinimum(0)
                self.mw.pan_slider.setMaximum(0)
            if self.mw.zoom_slider:
                self.mw.zoom_slider.setMinimum(10)
                self.mw.zoom_slider.setMaximum(self.mw.slider_scale_factor)
                self.mw.zoom_slider.setValue(self.mw.slider_scale_factor)
        self.mw._exit_batch_update()
        if not self.mw._is_batch_updating_ui: self.apply_sliders_to_timeline_view()

    # ... (le reste des méthodes de AppLogic)
    def reset_all_filters_and_view(self, initial_load=False):
        self.mw._enter_batch_update()
        try:
            # Reset filter states
            self.selected_log_levels = {'INFO': True, 'WARN': True, 'ERROR': True, 'DEBUG': True}
            self.timeline_filter_active = False
            self.timeline_filter_start_time = None
            self.timeline_filter_end_time = None
            self.current_search_text = ""

            # Update UI elements that reflect these states
            self.update_log_summary_display() # Reflects log level counts

            search_input = self.mw.message_type_search_input
            if search_input:
                search_input.blockSignals(True)
                search_input.clear()
                search_input.blockSignals(False)

            # This rebuilds the message type tree and selects all by default
            self._rebuild_message_types_data_and_list(select_all_visible=True)

            if self.mw.pan_slider and self.mw.zoom_slider:
                self.mw.pan_slider.setValue(0)
                self.mw.zoom_slider.setValue(self.mw.slider_scale_factor)

            if self.mw.granularity_combo:
                self.mw.granularity_combo.blockSignals(True)
                default_granularity = 'minute'
                if hasattr(self.mw, 'log_entries_full') and not self.mw.log_entries_full.empty and self.mw.loaded_source_type:
                    if self.mw.loaded_source_type == "archive":
                        default_granularity = 'day'
                    elif self.mw.loaded_source_type == "single_file":
                        default_granularity = 'hour'
                self.mw.granularity_combo.setCurrentText(default_granularity)
                self.mw.granularity_combo.blockSignals(False)

            if self.mw.search_widget: self.mw.search_widget.clear_search() # Clears UI
            # selected_messages_list will be updated by _apply_filters_and_update_views
            if self.mw.details_text: self.mw.details_text.clear()

        finally:
            self.mw._exit_batch_update()

        # Apply all (now reset) filters to update the main list and timeline.
        self._apply_filters_and_update_views(refresh_filter_categories=True)
        
        # On initial load, programmatically click the "Top 10" button to select the most frequent message types.
        # Using .click() simulates a user action, ensuring all connected signals are properly emitted via the event loop.
        if initial_load:
            if hasattr(self.mw, 'select_top10_btn'):
                self.mw.select_top10_btn.click()

        if not initial_load and self.mw.statusBar():
            self.mw.statusBar().showMessage("Vue et filtres réinitialisés", 3000)

    def update_log_summary_display(self):
        if not self.mw.period_label or not self.mw.total_label or not self.mw.error_btn:
            return

        if self.mw.log_entries_full.empty:
            self.mw.period_label.setText("Pas de log chargé")
            self.mw.period_label.setToolTip("") # Clear tooltip
            self.mw.total_label.setText("0 entrées")
            for level in ['INFO', 'WARN', 'ERROR', 'DEBUG']:
                btn = getattr(self.mw, f"{level.lower()}_btn", None)
                if btn:
                    btn.setText(f"{level}: 0")
        else:
            total_entries = len(self.mw.log_entries_full)
            first_dt_obj = self.mw.log_entries_full['datetime_obj'].min()
            last_dt_obj = self.mw.log_entries_full['datetime_obj'].max()

            period_str = "N/A"
            tooltip_text = ""
            if pd.notna(first_dt_obj) and pd.notna(last_dt_obj):
                try:
                    locale.setlocale(locale.LC_TIME, 'fr_FR.UTF-8')
                except locale.Error:
                    locale.setlocale(locale.LC_TIME, '') # Fallback

                start_str = first_dt_obj.strftime('%a %Y-%m-%d %H:%M:%S')
                end_str = last_dt_obj.strftime('%a %Y-%m-%d %H:%M:%S')
                period_str = f"{start_str} to {end_str}"

                duration = last_dt_obj - first_dt_obj
                days, rem = divmod(duration.total_seconds(), 86400)
                hours, rem = divmod(rem, 3600)
                minutes, seconds = divmod(rem, 60)
                duration_str = f"{int(days)}j {int(hours)}h {int(minutes)}m {int(seconds)}s"
                
                tooltip_text = (
                    f"Période totale des logs chargés :\n"
                    f"Début : {first_dt_obj.strftime('%A %d %B %Y, %H:%M:%S')}\n"
                    f"Fin   : {last_dt_obj.strftime('%A %d %B %Y, %H:%M:%S')}\n"
                    f"Durée : {duration_str}"
                )

            self.mw.period_label.setText(period_str)
            self.mw.period_label.setToolTip(tooltip_text)
            self.mw.total_label.setText(f"{total_entries:,} entrées")
            
            level_counts = self.mw.log_entries_full['log_level'].value_counts()
            for level in ['INFO', 'WARN', 'ERROR', 'DEBUG']:
                btn = getattr(self.mw, f"{level.lower()}_btn", None)
                if btn:
                    count = level_counts.get(level, 0)
                    btn.setText(f"{level}: {count:,}")
                    btn.setChecked(self.selected_log_levels.get(level, False))

    def _rebuild_message_types_data_and_list(self, source_df=None, select_all_visible=False):
        if source_df is None:
            if not hasattr(self.mw, 'log_entries_full') or self.mw.log_entries_full.empty:
                df_to_process = pd.DataFrame(columns=['logger_name', 'log_level'])
            else:
                selected_levels = {level for level, is_selected in self.selected_log_levels.items() if is_selected}
                df_to_process = self.mw.log_entries_full[self.mw.log_entries_full['log_level'].isin(selected_levels)]
        else:
            df_to_process = source_df

        if df_to_process.empty:
            self.message_types_data_for_list = pd.DataFrame(columns=['logger_name', 'count'])
        else:
            logger_counts_series = df_to_process['logger_name'].value_counts()
            search_text = self.mw.message_type_search_input.text().lower() if self.mw.message_type_search_input else ""
            if search_text:
                if not logger_counts_series.empty and pd.api.types.is_string_dtype(logger_counts_series.index.dtype):
                    logger_counts_series = logger_counts_series[logger_counts_series.index.str.lower().str.contains(search_text, regex=False)]
                elif not logger_counts_series.empty:
                    logger_counts_series = logger_counts_series[[str(idx).lower().find(search_text) != -1 for idx in logger_counts_series.index]]

            if logger_counts_series.empty:
                self.message_types_data_for_list = pd.DataFrame(columns=['logger_name', 'count'])
            else:
                self.message_types_data_for_list = logger_counts_series.reset_index()
                self.message_types_data_for_list.columns = ['logger_name', 'count']
                self.message_types_data_for_list['count'] = self.message_types_data_for_list['count'].astype(int)

        if self.mw.message_types_tree:
            tree = self.mw.message_types_tree
            tree.clear()
            tree.setSortingEnabled(False)
            items = []
            for _, row in self.message_types_data_for_list.iterrows():
                item = SortableTreeWidgetItem([str(row['logger_name']), str(int(row['count']))])
                item.setCheckState(0, QtCore.Qt.Unchecked)
                items.append(item)
            tree.addTopLevelItems(items)
            tree.setSortingEnabled(True)
            if select_all_visible:
                self.set_check_state_for_visible_types(QtCore.Qt.Checked)

    def trigger_timeline_update_from_selection(self):
        if self.mw._is_batch_updating_ui or not self.mw.timeline_canvas: return
        selected_types = set()
        if self.mw.message_types_tree:
            for i in range(self.mw.message_types_tree.topLevelItemCount()):
                item = self.mw.message_types_tree.topLevelItem(i)
                if item.checkState(0) == QtCore.Qt.Checked:
                    selected_types.add(item.text(0))

        granularity = self.mw.granularity_combo.currentText() if self.mw.granularity_combo else 'minute'
        self.mw.timeline_canvas.update_display_config(selected_types, granularity)

    def on_granularity_changed(self):
        if self.mw._is_batch_updating_ui: return
        self.mw._enter_batch_update()
        if self.mw.pan_slider: self.mw.pan_slider.setValue(0)
        if self.mw.zoom_slider: self.mw.zoom_slider.setValue(self.mw.slider_scale_factor)
        self.mw._exit_batch_update()
        self.trigger_timeline_update_from_selection()
        if self.mw.statusBar(): self.mw.statusBar().showMessage(f"Granularité: {self.mw.granularity_combo.currentText()}", 2000)

    def on_slider_value_changed(self):
        if not self.mw._is_batch_updating_ui:
            self.apply_sliders_to_timeline_view()

    def apply_sliders_to_timeline_view(self):
        if self.mw._is_batch_updating_ui: return
        if self.mw.timeline_min_num_full_range is None or self.mw.timeline_max_num_full_range is None: return
        if not self.mw.timeline_canvas or not self.mw.pan_slider or not self.mw.zoom_slider: return

        if self.mw.timeline_max_num_full_range <= self.mw.timeline_min_num_full_range:
            center_point = self.mw.timeline_min_num_full_range
            tiny_width = 0.0001
            self.mw.timeline_canvas.set_time_window_from_sliders(center_point - tiny_width / 2, center_point + tiny_width / 2)
            return

        total_data_span = self.mw.timeline_max_num_full_range - self.mw.timeline_min_num_full_range
        zoom_value = max(self.mw.zoom_slider.value(), 1)
        zoom_ratio = zoom_value / self.mw.slider_scale_factor
        view_width = total_data_span * zoom_ratio
        min_view_width = max(total_data_span * (self.mw.zoom_slider.minimum() / self.mw.slider_scale_factor), 1e-5)
        view_width = max(view_width, min_view_width)

        pannable_range_num = total_data_span - view_width
        if pannable_range_num < 0: pannable_range_num = 0

        pan_ratio = self.mw.pan_slider.value() / self.mw.slider_scale_factor
        view_start_offset_from_min = pannable_range_num * pan_ratio
        view_start_num = self.mw.timeline_min_num_full_range + view_start_offset_from_min
        view_end_num = view_start_num + view_width

        view_start_num = max(view_start_num, self.mw.timeline_min_num_full_range)
        view_end_num = min(view_end_num, self.mw.timeline_max_num_full_range)

        if view_start_num + view_width > self.mw.timeline_max_num_full_range:
            view_start_num = self.mw.timeline_max_num_full_range - view_width
            view_start_num = max(view_start_num, self.mw.timeline_min_num_full_range)

        if view_start_num < view_end_num - 1e-9:
            self.mw.timeline_canvas.set_time_window_from_sliders(view_start_num, view_end_num)
        elif total_data_span > 1e-9:
            self.mw.timeline_canvas.set_time_window_from_sliders(self.mw.timeline_min_num_full_range, self.mw.timeline_max_num_full_range)

    def on_message_type_search_changed_debounced(self, text):
        if self.mw.message_type_search_timer:
            self.mw.message_type_search_timer.stop()
            self.mw.message_type_search_timer.start(300)
        if self.mw.statusBar():
            self.mw.statusBar().showMessage(f"Filtrage types: '{text}'" if text else "Filtre types effacé", 2000)

    def apply_message_type_filter(self):
        if not self.mw.message_types_tree or not self.mw.message_type_search_input: return
        search_text = self.mw.message_type_search_input.text().lower()
        for i in range(self.mw.message_types_tree.topLevelItemCount()):
            item = self.mw.message_types_tree.topLevelItem(i)
            item.setHidden(bool(search_text and search_text not in item.text(0).lower()))
        # The visibility of items in the tree has changed, which affects what _apply_filters_and_update_views considers.
        self._apply_filters_and_update_views(refresh_filter_categories=False)

    def on_message_type_item_changed(self, item, column):
        if not self.mw._is_batch_updating_ui:
            # A change in the message type tree selection is a filter change.
            self._apply_filters_and_update_views(refresh_filter_categories=False)
            
            # Also, the timeline needs to be updated based on the new selection of message types.
            selected_types_for_timeline = set()
            if self.mw.message_types_tree:
                for i in range(self.mw.message_types_tree.topLevelItemCount()):
                    tree_item = self.mw.message_types_tree.topLevelItem(i)
                    # Consider only items that are checked AND not hidden by the message type search filter
                    if tree_item.checkState(0) == QtCore.Qt.Checked and not tree_item.isHidden():
                        selected_types_for_timeline.add(tree_item.text(0))
            
            current_granularity = self.mw.granularity_combo.currentText() if self.mw.granularity_combo else 'minute'
            if self.mw.timeline_canvas:
                self.mw.timeline_canvas.update_display_config(selected_types_for_timeline, current_granularity)

    def on_global_search_changed(self, text):
        """Handle changes from the global search box with debouncing."""
        self.global_search_query = text.strip()
        self.global_search_timer.start(300) # Debounce for 300ms

    def on_search_changed(self, search_text):
        self.current_search_text = search_text.strip()
        # _apply_filters_and_update_views will handle empty log_entries_full or empty search_text
        self._apply_filters_and_update_views(refresh_filter_categories=True)
        
        # Status bar message is now handled by _apply_filters_and_update_views, 
        # but we can add a specific search status message here if desired, or let the generic one suffice.
        if self.mw.statusBar():
            if self.current_search_text:
                self.mw.statusBar().showMessage(f"Filtre de recherche appliqué: '{self.current_search_text}'", 2000)
            else:
                self.mw.statusBar().showMessage("Filtre de recherche effacé", 2000)

    def _apply_search_filter_and_update_views(self):
        """Apply search filter and update views."""
        self._apply_filters_and_update_views(refresh_filter_categories=True)

    def _apply_filters_and_update_views(self, refresh_filter_categories=False):
        """Central method to apply all active filters and update all views.
        The filtering order is:
        1. Global Full-Text Search
        2. Log Level
        3. Timeline Time Range
        4. Message Type List Selection
        5. Main Search box (over the log list)
        """
        if self.mw.log_entries_full is None or self.mw.log_entries_full.empty:
            self.update_status_bar_message("No log data to filter.")
            if self.mw.selected_messages_list: self.mw.selected_messages_list.set_all_items_data([])
            self._rebuild_message_types_data_and_list(source_df=pd.DataFrame())
            return

        # --- Start Filtering ---
        current_df = self.mw.log_entries_full

        # 1. Global Full-Text Search
        if self.global_search_query and self.search_engine.is_indexed:
            matching_indices = self.search_engine.search(self.global_search_query)
            current_df = current_df[current_df.index.isin(matching_indices)]

        # 2. Filter by Log Level
        active_levels = {level for level, is_selected in self.selected_log_levels.items() if is_selected}
        if len(active_levels) < len(self.selected_log_levels):
            current_df = current_df[current_df['log_level'].isin(active_levels)]

        # 3. Filter by Time (from timeline slider)
        if self.timeline_filter_active and self.timeline_filter_start_time and self.timeline_filter_end_time:
            current_df = current_df[
                (current_df['datetime_obj'] >= self.timeline_filter_start_time) &
                (current_df['datetime_obj'] < self.timeline_filter_end_time)
            ]

        # This dataframe has the global, level, and time filters applied.
        # It's the source for rebuilding the message type list.
        if refresh_filter_categories:
            self._rebuild_message_types_data_and_list(source_df=current_df.copy())

        # 4. Filter by selected message types in the list
        selected_types = set()
        is_any_type_checked = False
        if self.mw.message_types_tree:
            for i in range(self.mw.message_types_tree.topLevelItemCount()):
                item = self.mw.message_types_tree.topLevelItem(i)
                if item.checkState(0) == QtCore.Qt.Checked:
                    is_any_type_checked = True
                    selected_types.add(item.text(0))
        
        if is_any_type_checked:
             current_df = current_df[current_df['logger_name'].isin(selected_types)]

        # 5. Filter by main search widget text (self.current_search_text)
        if self.current_search_text:
            if 'message_preview' in current_df.columns:
                current_df = current_df[current_df['message_preview'].str.contains(self.current_search_text, case=False, na=False, regex=False)]

        # Now current_df is fully filtered. Update the main message view.
        filtered_entries_list = current_df.to_dict('records')
        if self.mw.selected_messages_list:
            self.mw.details_text.clear()
            self.mw.prev_message_button.setEnabled(False)
            self.mw.next_message_button.setEnabled(False)
            self.mw.selected_messages_list.set_all_items_data(filtered_entries_list)

        if self.status_bar:
            status_message = f"{len(filtered_entries_list):,} messages displayed."
            self.status_bar.showMessage(status_message, 3000)

        # Finally, update the timeline view with the currently selected types
        if self.mw.timeline_canvas:
            granularity = self.mw.granularity_combo.currentText() if self.mw.granularity_combo else 'minute'
            self.mw.timeline_canvas.update_display_config(selected_types, granularity)

    def _fetch_full_log_entry(self, metadata_entry):
        source_file_path = metadata_entry.get('source_file_path')
        start_line = metadata_entry.get('line_number')

        if not source_file_path or not start_line or not os.path.exists(source_file_path):
            return f"Source file not found or invalid metadata: {source_file_path}"

        full_entry = []
        line_number = 0

        try:
            # Since log_processing now guarantees uncompressed files, we only need to handle plain text.
            # We still need to handle encoding, however.
            detected_encoding = None
            encodings_to_try = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
            opener = lambda enc: open(source_file_path, 'r', encoding=enc)

            for enc in encodings_to_try:
                try:
                    with opener(enc) as f_test:
                        f_test.readline()
                    detected_encoding = enc
                    break
                except (UnicodeDecodeError, IOError):
                    continue
            
            if not detected_encoding:
                return f"Could not decode file {os.path.basename(source_file_path)} to fetch full entry."

            with opener(detected_encoding) as f:
                # This is not the most efficient way to get to a line, but it's simple.
                for i, line in enumerate(f):
                    line_number = i + 1
                    if line_number == start_line:
                        full_entry.append(line)
                        # Now read subsequent lines that don't match the log entry pattern (for stack traces)
                        for next_line in f:
                            if re.match(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', next_line):
                                break # Start of a new log entry
                            full_entry.append(next_line)
                        break
            return "".join(full_entry)
        except Exception as e:
            return f"Error reading full log entry from {os.path.basename(source_file_path)}: {e}"
    def on_timeline_bar_clicked(self, time_start, time_end):
        if self.mw._is_batch_updating_ui: return
        
        self.timeline_filter_active = True
        self.timeline_filter_start_time = time_start
        self.timeline_filter_end_time = time_end
        
        self._apply_filters_and_update_views(refresh_filter_categories=False)

    def navigate_to_previous_message(self):
        self._navigate_message(-1)

    def navigate_to_next_message(self):
        self._navigate_message(1)

    def _navigate_message(self, direction):
        selected_items = self.mw.selected_messages_list.selectedItems()
        if not selected_items:
            return

        current_item = selected_items[0]
        current_logger = current_item.text(2)  # Logger is in column 2
        current_index = self.mw.selected_messages_list.indexOfTopLevelItem(current_item)

        start_index = current_index + direction
        if direction == -1:
            search_range = range(start_index, -1, -1)
        else:
            search_range = range(start_index, self.mw.selected_messages_list.topLevelItemCount())

        for i in search_range:
            item = self.mw.selected_messages_list.topLevelItem(i)
            if item and item.text(2) == current_logger:
                self.mw.selected_messages_list.setCurrentItem(item)
                self.mw.selected_messages_list.scrollToItem(item, QtWidgets.QAbstractItemView.PositionAtCenter)
                return

    def on_message_selected(self):
        if not self.mw.selected_messages_list or not self.mw.details_text: return
        selected_items = self.mw.selected_messages_list.selectedItems()
        if not selected_items:
            self.mw.details_text.clear()
            self.mw.prev_message_button.setEnabled(False)
            self.mw.next_message_button.setEnabled(False)
            return
        
        metadata_entry = selected_items[0].data(0, QtCore.Qt.UserRole)
        if not metadata_entry or not isinstance(metadata_entry, dict):
            self.mw.details_text.setPlainText("Error: Invalid or no metadata associated with selected item.")
            return

        full_message_content = self._fetch_full_log_entry(metadata_entry)
        self.mw.details_text.setPlainText(full_message_content)

        # Update navigation button states
        selected_item = selected_items[0]
        current_logger = selected_item.text(2)
        current_index = self.mw.selected_messages_list.indexOfTopLevelItem(selected_item)

        # Check for previous
        has_prev = False
        for i in range(current_index - 1, -1, -1):
            item = self.mw.selected_messages_list.topLevelItem(i)
            if item and item.text(2) == current_logger:
                has_prev = True
                break
        self.mw.prev_message_button.setEnabled(has_prev)

        # Check for next
        has_next = False
        for i in range(current_index + 1, self.mw.selected_messages_list.topLevelItemCount()):
            item = self.mw.selected_messages_list.topLevelItem(i)
            if item and item.text(2) == current_logger:
                has_next = True
                break
        self.mw.next_message_button.setEnabled(has_next)

    def _get_currently_visible_message_types_sorted_by_count(self):
        if not self.mw.message_types_tree: return []
        visible_types_with_counts = []
        for i in range(self.mw.message_types_tree.topLevelItemCount()):
            item = self.mw.message_types_tree.topLevelItem(i)
            if not item.isHidden():
                try:
                    count = int(item.text(1))
                    visible_types_with_counts.append((item.text(0), count))
                except (ValueError, TypeError):
                    continue
        visible_types_with_counts.sort(key=lambda x: (-x[1], x[0]))
        return [name for name, count in visible_types_with_counts]

    def _select_top_n_types_logic(self, top_n):
        if not self.mw.message_types_tree or self.mw.log_entries_full.empty:
            return

        # Get currently selected levels
        selected_levels = {level for level, is_selected in self.selected_log_levels.items() if is_selected}
        df = self.mw.log_entries_full[self.mw.log_entries_full['log_level'].isin(selected_levels)]

        if df.empty:
            return

        # Get top N logger names by frequency
        top_types = df['logger_name'].value_counts().nlargest(top_n).index.to_list()
        top_types_set = set(top_types)

        self.mw._enter_batch_update()
        try:
            tree = self.mw.message_types_tree
            for i in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(i)
                logger_name = item.text(0)
                if logger_name in top_types_set:
                    item.setCheckState(0, QtCore.Qt.Checked)
                else:
                    item.setCheckState(0, QtCore.Qt.Unchecked)
        finally:
            self.mw._exit_batch_update()
        self.trigger_timeline_update_from_selection()

    def select_top5_message_types(self):
        self._select_top_n_types_logic(5)

    def select_top10_message_types(self):
        self._select_top_n_types_logic(10)

    def set_check_state_for_all_types(self, check_state):
        if self.mw._is_batch_updating_ui or not self.mw.message_types_tree: return
        self.mw._enter_batch_update()
        self.mw.message_types_tree.blockSignals(True)
        for i in range(self.mw.message_types_tree.topLevelItemCount()):
            item = self.mw.message_types_tree.topLevelItem(i)
            if item.checkState(0) != check_state:
                item.setCheckState(0, check_state)
        self.mw.message_types_tree.blockSignals(False)
        self.mw._exit_batch_update()
        self.trigger_timeline_update_from_selection()

    def set_check_state_for_visible_types(self, check_state):
        if self.mw._is_batch_updating_ui or not self.mw.message_types_tree: return
        self.mw._enter_batch_update()
        self.mw.message_types_tree.blockSignals(True)
        for i in range(self.mw.message_types_tree.topLevelItemCount()):
            item = self.mw.message_types_tree.topLevelItem(i)
            if not item.isHidden():
                if item.checkState(0) != check_state: item.setCheckState(0, check_state)
        self.mw.message_types_tree.blockSignals(False)
        self.mw._exit_batch_update()
        self.trigger_timeline_update_from_selection()

    def filter_by_specific_level(self, level_to_show):
        if self.mw._is_batch_updating_ui: return
        self.mw._enter_batch_update()
        try:
            # Set current filter to only this level
            self.selected_log_levels = {lvl: (lvl == level_to_show) for lvl in ['INFO', 'WARN', 'ERROR', 'DEBUG']}
            
            # Update UI elements that depend on log level counts or selections
            self.update_log_summary_display() # Updates counts on buttons
            
            # Rebuild message type list based on the new log level filter, selecting all visible types
            # This ensures the message type tree reflects types present in the new level-filtered subset
            self._rebuild_message_types_data_and_list(select_all_visible=True)

        finally:
            self.mw._exit_batch_update()
        
        # Apply all current filters (including the new level filter) to update the main list
        self._apply_filters_and_update_views(refresh_filter_categories=False)
        
        # Update the timeline display based on the new selection of message types (which were rebuilt)
        # and current granularity.
        selected_types_for_timeline = set()
        if self.mw.message_types_tree:
            for i in range(self.mw.message_types_tree.topLevelItemCount()):
                item = self.mw.message_types_tree.topLevelItem(i)
                if item.checkState(0) == QtCore.Qt.Checked: # Should be all visible types after rebuild
                    selected_types_for_timeline.add(item.text(0))
        
        current_granularity = self.mw.granularity_combo.currentText() if self.mw.granularity_combo else 'minute'
        if self.mw.timeline_canvas:
            self.mw.timeline_canvas.update_display_config(selected_types_for_timeline, current_granularity)

    def apply_date_filter_to_timeline(self):
        date_range = getattr(self.mw, 'date_filter_range', None)
        
        if not date_range or self.mw.log_entries_full.empty:
            filtered_df = self.mw.log_entries_full
        else:
            start_qdate, end_qdate = date_range
            start_dt = datetime(start_qdate.year(), start_qdate.month(), start_qdate.day())
            end_dt = datetime(end_qdate.year(), end_qdate.month(), end_qdate.day(), 23, 59, 59, 999999)
            
            mask = (
                (self.mw.log_entries_full['datetime_obj'] >= start_dt) &
                (self.mw.log_entries_full['datetime_obj'] <= end_dt)
            )
            filtered_df = self.mw.log_entries_full[mask]

        if self.mw.timeline_canvas:
            self.mw.timeline_canvas.set_full_log_data(filtered_df)

    def set_granularity(self, granularity):
        # Update the timeline granularity and refresh the view
        if hasattr(self.mw, 'timeline_canvas') and self.mw.timeline_canvas:
            self.mw.timeline_canvas.current_time_granularity = granularity
            # Refresh the plot with selected types
            selected_types = set()
            if self.mw.message_types_tree:
                for i in range(self.mw.message_types_tree.topLevelItemCount()):
                    item = self.mw.message_types_tree.topLevelItem(i)
                    if item.checkState(0) == QtCore.Qt.Checked:
                        selected_types.add(item.text(0))
            self.mw.timeline_canvas.update_display_config(selected_types, granularity)

    def pan_timeline_left(self):
        self._pan_timeline(direction=-1)

    def pan_timeline_right(self):
        self._pan_timeline(direction=1)

    def export_timeline_data_to_csv(self):
        if self.mw.log_entries_full.empty:
            QtWidgets.QMessageBox.information(self.mw, "No Data", "Please load a log file first.")
            return

        selected_types = {item.text(0) for item in self.mw.message_types_tree.findItems("*", QtCore.Qt.MatchWildcard | QtCore.Qt.MatchRecursive) if item.checkState(0) == QtCore.Qt.Checked}

        if not selected_types:
            QtWidgets.QMessageBox.information(self.mw, "No Selection", "Please select at least one message type to export.")
            return

        granularity = self.mw.granularity_combo.currentText()

        # This logic mirrors _get_or_prepare_time_groups in TimelineCanvas
        df_filtered = self.mw.log_entries_full[self.mw.log_entries_full['logger_name'].isin(selected_types)].copy()
        if df_filtered.empty:
            QtWidgets.QMessageBox.information(self.mw, "No Data", "No log entries found for the selected message types.")
            return

        df_filtered.dropna(subset=['datetime_obj'], inplace=True)
        dts = df_filtered['datetime_obj']

        if granularity == 'day':
            df_filtered['period_date'] = dts.dt.floor('D')
        elif granularity == 'hour':
            df_filtered['period_date'] = dts.dt.floor('h')
        else:  # 'minute'
            df_filtered['period_date'] = dts.dt.floor('T')

        # Group by the new period and logger name, then count
        export_data = df_filtered.groupby(['period_date', 'logger_name']).size().reset_index(name='total_count')

        # Sort for readability
        export_data.sort_values(by=['period_date', 'logger_name'], inplace=True)

        # Get file path from user
        default_filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self.mw, "Save CSV Export", default_filename, "CSV Files (*.csv);;All Files (*)")

        if file_path:
            try:
                export_data.to_csv(file_path, index=False, date_format='%Y-%m-%d %H:%M:%S')
                QtWidgets.QMessageBox.information(self.mw, "Export Successful", f"Data successfully exported to {os.path.basename(file_path)}.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self.mw, "Export Failed", f"An error occurred while saving the file:\n{e}")

    def save_current_selection_as_filter(self):
        """Saves the currently checked message types to a JSON filter file."""
        selected_types = {item.text(0) for item in self.mw.message_types_tree.findItems("*", QtCore.Qt.MatchWildcard | QtCore.Qt.MatchRecursive) if item.checkState(0) == QtCore.Qt.Checked}

        if not selected_types:
            QtWidgets.QMessageBox.warning(self.mw, "No Selection", "Please select at least one message type to save as a filter.")
            return

        filter_name, ok = QtWidgets.QInputDialog.getText(self.mw, "Save Filter", "Enter a name for this filter:")

        if ok and filter_name:
            default_filename = f"{filter_name.replace(' ', '_').lower()}.json"
            file_path, _ = QtWidgets.QFileDialog.getSaveFileName(self.mw, "Save Filter File", default_filename, "JSON Files (*.json);;All Files (*)")

            if file_path:
                filter_data = {
                    "name": filter_name,
                    "loggers": sorted(list(selected_types))
                }
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(filter_data, f, indent=4)
                    QtWidgets.QMessageBox.information(self.mw, "Success", f"Filter '{filter_name}' saved successfully.")
                except IOError as e:
                    QtWidgets.QMessageBox.critical(self.mw, "Error", f"Could not save filter file: {e}")

    def apply_filter_from_dialog(self, filter_name, loggers, silent=False):
        """Receives the filter data from the dialog and applies it."""
        self.active_filter_name = filter_name
        self.active_filter_loggers = set(loggers)
        self.mw.active_filter_label.setText(f"Filter: {self.active_filter_name}")
        self.mw.active_filter_label.setToolTip(f"Active loggers: {', '.join(loggers)}")
        if not silent:
            QtWidgets.QMessageBox.information(self.mw, "Filter Applied", f"The filter '{filter_name}' is now active. It will be applied the next time you load a log file or archive.")

    def clear_active_filter(self):
        """Clears the currently active filter."""
        self.active_filter_name = "None"
        self.active_filter_loggers = set()
        self.mw.active_filter_label.setText("Filter: None")
        self.mw.active_filter_label.setToolTip("No pre-load filter is active.")

    def get_active_filter_name(self):
        """Returns the name of the currently active filter."""
        return self.active_filter_name

    def apply_filter_by_name(self, filter_name):
        """Apply the filter by its name."""
        filter_path = os.path.join(self.mw.last_filter_directory, filter_name)
        if os.path.exists(filter_path):
            with open(filter_path, 'r', encoding='utf-8') as f:
                filter_data = json.load(f)
                loggers = filter_data.get('loggers', [])
                self.apply_filter_from_dialog(filter_name, loggers)
                print(f"Filter '{filter_name}' applied with loggers: {loggers}")
        else:
            print(f"Filter '{filter_name}' not found.")