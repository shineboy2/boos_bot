import sqlite3
from pathlib import Path
from contextlib import contextmanager

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "data" / "market.db"

class DatabaseManager:
    """
    Centralized database connection manager for SQLite.
    Ensures that connections are handled safely and WAL mode is enabled for concurrency.
    """
    
    def __init__(self, db_path=DB_FILE):
        self.db_path = Path(db_path)
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Enable WAL mode for better concurrency."""
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            self._create_schema(conn)

    @contextmanager
    def connect(self):
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _create_schema(self, conn):
        """Create necessary tables if they don't exist."""
        conn.execute("""
            CREATE TABLE IF NOT EXISTS instruments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ins_code TEXT NOT NULL UNIQUE,
                ins_id TEXT NOT NULL UNIQUE,
                isin TEXT,
                symbol TEXT NOT NULL,
                name TEXT,
                market TEXT,
                market_board TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                last REAL,
                volume INTEGER,
                value INTEGER,
                trade_count INTEGER,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id),
                UNIQUE (instrument_id, date)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS divergence_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER NOT NULL,
                signal_date TEXT NOT NULL,
                indicator TEXT NOT NULL,
                divergence_type TEXT NOT NULL,
                
                price_pivot_1_date TEXT NOT NULL,
                price_pivot_2_date TEXT NOT NULL,
                indicator_pivot_1_date TEXT NOT NULL,
                indicator_pivot_2_date TEXT NOT NULL,
                
                price_pivot_1_value REAL NOT NULL,
                price_pivot_2_value REAL NOT NULL,
                indicator_pivot_1_value REAL NOT NULL,
                indicator_pivot_2_value REAL NOT NULL,
                
                bars_between INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS backtest_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                signal_id INTEGER NOT NULL,
                instrument_id INTEGER NOT NULL,
                signal_date TEXT NOT NULL,
                indicator TEXT NOT NULL,
                divergence_type TEXT NOT NULL,
                
                entry_price REAL NOT NULL,
                
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_30d REAL,
                
                mfe_30d REAL,
                mae_30d REAL,
                
                created_at TEXT NOT NULL,
                
                FOREIGN KEY (signal_id) REFERENCES divergence_signals(id),
                FOREIGN KEY (instrument_id) REFERENCES instruments(id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_watchlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                instrument_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (user_id, instrument_id),
                FOREIGN KEY (instrument_id) REFERENCES instruments(id)
            )
        """)

        # Indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_instrument_date ON ohlcv_daily(instrument_id, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON ohlcv_daily(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_instrument ON divergence_signals(instrument_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_date ON divergence_signals(signal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_indicator_type ON divergence_signals(indicator, divergence_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_instrument ON backtest_results(instrument_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_date ON backtest_results(signal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_type ON backtest_results(indicator, divergence_type)")
        
        conn.commit()
