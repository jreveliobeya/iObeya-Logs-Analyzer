import sqlite3
import pandas as pd
from typing import Union, Callable

class SearchEngine:
    """A search engine using SQLite's FTS5 for full-text search on log data."""
    def __init__(self):
        self.conn = None
        self.is_indexed = False

    def index_data(self, messages: list[str], progress_callback: Union[Callable[[int, int], None], None] = None):
        """
        Indexes a list of log messages for full-text search.

        Args:
            messages (list[str]): A list of full log message strings.
            progress_callback (callable, optional): A function to call with progress updates.
        """
        if not messages:
            self.is_indexed = False
            return

        if self.conn:
            self.conn.close()

        self.conn = sqlite3.connect(':memory:')
        cursor = self.conn.cursor()
        cursor.execute('CREATE VIRTUAL TABLE logs USING fts5(log_message)')

        total_rows = len(messages)
        chunk_size = 10000

        for i in range(0, total_rows, chunk_size):
            chunk = messages[i:i + chunk_size]
            # The data needs to be a list of tuples for executemany
            data_to_insert = [(msg,) for msg in chunk]
            cursor.executemany('INSERT INTO logs (log_message) VALUES (?)', data_to_insert)
            if progress_callback:
                progress_callback(min(i + chunk_size, total_rows), total_rows)
        
        self.conn.commit()
        self.is_indexed = True

    def search(self, query: str) -> set:
        """
        Performs a full-text search on the indexed log messages.

        Args:
            query (str): The search query.

        Returns:
            set: A set of 0-based integer indices matching the query. Can be empty.
        """
        if not self.is_indexed or not query:
            return set()

        # Sanitize and build the query to be more robust.
        # This creates an AND query for all terms, with a prefix match on the last term.
        terms = query.split()
        if not terms:
            return set()
            
        terms[-1] += '*'
        fts_query = ' '.join(terms)

        try:
            cursor = self.conn.cursor()
            cursor.execute('SELECT rowid FROM logs WHERE logs MATCH ?', (fts_query,))
            results = cursor.fetchall()
            # FTS rowid is 1-based, DataFrame index is 0-based.
            return {row[0] - 1 for row in results}
        except sqlite3.OperationalError:
            # This can happen with invalid FTS queries (e.g., just '*')
            return set()

    def close(self):
        """Closes the database connection and clears the index."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.is_indexed = False
