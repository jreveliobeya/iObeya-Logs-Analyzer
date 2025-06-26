#!/usr/bin/env python3
from PyQt5 import QtWidgets, QtGui, QtCore
from collections import Counter
import pandas as pd
from datetime import datetime # For summary text
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np
from matplotlib.ticker import PercentFormatter

class StatsDialog(QtWidgets.QDialog):
    def __init__(self, all_log_entries, parent=None):
        super().__init__(parent)
        self.all_log_entries = all_log_entries
        self.setWindowTitle("Global Log Statistics")
        self.setMinimumSize(900, 700) # Increased size for new chart
        layout = QtWidgets.QVBoxLayout(self)
        self.tab_widget = QtWidgets.QTabWidget()
        layout.addWidget(self.tab_widget)

        # Create tabs
        self.create_summary_tab()
        self.create_pareto_tab()
        self.create_level_dist_tab()
        self.create_top_messages_breakdown_tab()

        # Populate with data
        self.populate_tabs()

    def create_summary_tab(self):
        summary_tab = QtWidgets.QWidget()
        summary_layout = QtWidgets.QVBoxLayout(summary_tab)
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        summary_layout.addWidget(scroll_area)
        summary_container = QtWidgets.QWidget()
        self.summary_form_layout = QtWidgets.QFormLayout(summary_container)
        self.summary_form_layout.setRowWrapPolicy(QtWidgets.QFormLayout.WrapAllRows)
        self.summary_form_layout.setLabelAlignment(QtCore.Qt.AlignLeft)
        self.summary_form_layout.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        scroll_area.setWidget(summary_container)
        self.tab_widget.addTab(summary_tab, "Overall Summary")

    def create_pareto_tab(self):
        pareto_tab = QtWidgets.QWidget()
        pareto_layout = QtWidgets.QVBoxLayout(pareto_tab)
        self.pareto_canvas = FigureCanvas(Figure(figsize=(7, 5)))
        pareto_layout.addWidget(self.pareto_canvas)
        self.tab_widget.addTab(pareto_tab, "Message Type Pareto")

    def create_level_dist_tab(self):
        level_dist_tab = QtWidgets.QWidget()
        level_dist_layout = QtWidgets.QVBoxLayout(level_dist_tab)
        self.level_dist_canvas = FigureCanvas(Figure(figsize=(5, 4)))
        level_dist_layout.addWidget(self.level_dist_canvas)
        self.tab_widget.addTab(level_dist_tab, "Log Level Distribution")

    def create_top_messages_breakdown_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        self.top_messages_canvas = FigureCanvas(Figure(figsize=(7, 6)))
        layout.addWidget(self.top_messages_canvas)
        self.tab_widget.addTab(tab, "Top 10 Breakdown")

    def populate_tabs(self):
        self.populate_summary_tab()
        self.plot_pareto_chart()
        self.plot_level_distribution()
        self.plot_top_messages_breakdown()

    def populate_summary_tab(self):
        # Clear previous widgets
        while self.summary_form_layout.count():
            item = self.summary_form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.all_log_entries.empty:
            self.summary_form_layout.addRow(QtWidgets.QLabel("No log entries loaded."))
            return

        total_entries = len(self.all_log_entries)
        first_dt = self.all_log_entries['datetime_obj'].min()
        last_dt = self.all_log_entries['datetime_obj'].max()
        logger_counts = self.all_log_entries['logger_name'].value_counts()
        level_counts = self.all_log_entries['log_level'].value_counts()

        # Helper to add a section
        def add_section(title):
            lbl = QtWidgets.QLabel(title)
            lbl.setStyleSheet("font-size: 14px; font-weight: bold; margin-top: 10px; margin-bottom: 5px;")
            self.summary_form_layout.addRow(lbl)

        # General Stats
        add_section("Global Statistics")
        period = "N/A"
        if pd.notna(first_dt) and pd.notna(last_dt):
            period = f"{first_dt:%Y-%m-%d %H:%M:%S} to {last_dt:%Y-%m-%d %H:%M:%S} (Duration: {str(last_dt - first_dt).split('.')[0]})"
        self.summary_form_layout.addRow("Time Period:", QtWidgets.QLabel(period))
        self.summary_form_layout.addRow("Total Entries:", QtWidgets.QLabel(f"{total_entries:,}"))
        self.summary_form_layout.addRow("Unique Message Types:", QtWidgets.QLabel(f"{len(logger_counts):,}"))

        # Log Levels
        add_section("Entries by Log Level")
        for level in ['ERROR', 'WARN', 'INFO', 'DEBUG']:
            count = level_counts.get(level, 0)
            percent = (count / total_entries * 100) if total_entries > 0 else 0
            self.summary_form_layout.addRow(f"{level}:", QtWidgets.QLabel(f"{count:>10,} ({percent:.2f}%)"))

        # Top 10 Messages
        add_section("Top 10 Most Frequent Message Types")
        for logger, count in logger_counts.nlargest(10).items():
            self.summary_form_layout.addRow(f"{logger}:", QtWidgets.QLabel(f"{count:,}"))

    def plot_pareto_chart(self):
        if self.all_log_entries.empty: return
        logger_counts = self.all_log_entries['logger_name'].value_counts()
        if logger_counts.empty: return

        top_20_counts = logger_counts.nlargest(20)
        loggers = top_20_counts.index.tolist()
        counts = top_20_counts.values
        
        cum_percent = np.cumsum(counts) / len(self.all_log_entries) * 100

        fig = self.pareto_canvas.figure
        fig.clear()
        ax1 = fig.add_subplot(111)
        x = np.arange(len(loggers))
        ax1.bar(x, counts, color='C0', alpha=0.7)
        ax1.set_xticks(x)
        ax1.set_xticklabels(loggers, rotation=45, ha="right", fontsize=8)
        ax1.set_xlabel("Message Type (Logger)")
        ax1.set_ylabel("Frequency (Count)", color='C0')
        ax1.tick_params(axis='y', labelcolor='C0')

        ax2 = ax1.twinx()
        ax2.plot(x, cum_percent, color='C1', marker='o', ms=5)
        ax2.yaxis.set_major_formatter(PercentFormatter())
        ax2.set_ylabel("Cumulative Percentage", color='C1')
        ax2.tick_params(axis='y', labelcolor='C1')
        ax2.set_ylim(0, 105)

        fig.suptitle(f"Pareto Chart of Message Types (Top {len(top_20_counts)})", fontsize=12)
        fig.tight_layout(rect=[0, 0.05, 1, 0.95])
        self.pareto_canvas.draw()

    def plot_level_distribution(self):
        if self.all_log_entries.empty: return
        level_counts = self.all_log_entries['log_level'].value_counts()
        if level_counts.empty: return

        ordered_labels = ['ERROR', 'WARN', 'INFO', 'DEBUG']
        plot_data = level_counts.reindex(ordered_labels).dropna()

        fig = self.level_dist_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        colors_map = {'ERROR': '#D32F2F', 'WARN': '#F57C00', 'INFO': '#1976D2', 'DEBUG': '#7B1FA2'}
        pie_colors = [colors_map.get(label, '#AAAAAA') for label in plot_data.index]

        ax.pie(plot_data.values, labels=plot_data.index, autopct='%1.1f%%', startangle=90, colors=pie_colors, wedgeprops={'edgecolor': 'white'})
        ax.axis('equal')
        fig.suptitle("Log Level Distribution", fontsize=12)
        fig.tight_layout()
        self.level_dist_canvas.draw()

    def plot_top_messages_breakdown(self):
        if self.all_log_entries.empty: return
        logger_counts = self.all_log_entries['logger_name'].value_counts()
        if logger_counts.empty: return

        top_10_loggers = logger_counts.nlargest(10).index
        df_top_10 = self.all_log_entries[self.all_log_entries['logger_name'].isin(top_10_loggers)]

        # Pivot table to get counts of each level for each top logger
        pivot = pd.crosstab(df_top_10['logger_name'], df_top_10['log_level'])
        
        # Order columns and logger names
        ordered_levels = ['ERROR', 'WARN', 'INFO', 'DEBUG']
        pivot = pivot.reindex(columns=ordered_levels, fill_value=0)
        pivot = pivot.reindex(index=top_10_loggers)

        fig = self.top_messages_canvas.figure
        fig.clear()
        ax = fig.add_subplot(111)
        
        colors_map = {'ERROR': '#D32F2F', 'WARN': '#F57C00', 'INFO': '#1976D2', 'DEBUG': '#7B1FA2'}
        
        # Plot stacked bar chart
        pivot.plot(kind='bar', stacked=True, ax=ax, color=[colors_map.get(c) for c in pivot.columns])

        ax.set_title('Log Level Breakdown for Top 10 Message Types', fontsize=12)
        ax.set_xlabel('Message Type (Logger)')
        ax.set_ylabel('Number of Log Entries')
        plt.setp(ax.get_xticklabels(), rotation=45, ha='right', rotation_mode='anchor', fontsize=8)
        ax.legend(title='Log Level')
        
        fig.tight_layout(rect=[0, 0.05, 1, 0.95])
        self.top_messages_canvas.draw()