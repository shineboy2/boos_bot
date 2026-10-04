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
    
    SCHEMA_VERSION = 2  # Increment when schema changes
    
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
            self._migrate_schema(conn)

    @contextmanager
    def connect(self):
        """Context manager for SQLite connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
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
                instrument_type TEXT,
                instrument_status TEXT DEFAULT 'active',
                active INTEGER DEFAULT 1,
                last_seen_at TEXT,
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
                yesterday REAL,
                volume INTEGER,
                value INTEGER,
                trade_count INTEGER,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                is_valid INTEGER DEFAULT 1,
                price_type TEXT DEFAULT 'raw',
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
                
                pivot_occurrence_date TEXT,
                confirmation_date TEXT,
                
                created_at TEXT NOT NULL,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id),
                UNIQUE (instrument_id, signal_date, indicator, divergence_type, 
                        price_pivot_1_date, price_pivot_2_date)
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
                
                entry_date TEXT,
                entry_price REAL NOT NULL,
                entry_type TEXT DEFAULT 'next_open',
                
                return_5d REAL,
                return_10d REAL,
                return_20d REAL,
                return_30d REAL,
                
                mfe_30d REAL,
                mae_30d REAL,
                
                horizon_5d_complete INTEGER DEFAULT 0,
                horizon_10d_complete INTEGER DEFAULT 0,
                horizon_20d_complete INTEGER DEFAULT 0,
                horizon_30d_complete INTEGER DEFAULT 0,
                
                transaction_cost REAL DEFAULT 0.0,
                
                created_at TEXT NOT NULL,
                
                FOREIGN KEY (signal_id) REFERENCES divergence_signals(id),
                FOREIGN KEY (instrument_id) REFERENCES instruments(id),
                UNIQUE (signal_id)
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS client_type_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                real_buy_count INTEGER,
                real_buy_volume REAL,
                real_buy_value REAL,
                real_sell_count INTEGER,
                real_sell_volume REAL,
                real_sell_value REAL,
                legal_buy_count INTEGER,
                legal_buy_volume REAL,
                legal_buy_value REAL,
                legal_sell_count INTEGER,
                legal_sell_volume REAL,
                legal_sell_value REAL,
                UNIQUE(instrument_id, date),
                FOREIGN KEY(instrument_id) REFERENCES instruments(id)
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
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL UNIQUE,
                stage TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                market_date TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                total_instruments INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                skipped_count INTEGER DEFAULT 0,
                records_created INTEGER DEFAULT 0,
                records_updated INTEGER DEFAULT 0,
                error_message TEXT,
                metadata TEXT
            )
        """)
        
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                instrument_id INTEGER,
                date TEXT,
                issue_type TEXT NOT NULL,
                severity TEXT NOT NULL DEFAULT 'warning',
                description TEXT,
                field_name TEXT,
                field_value TEXT,
                action_taken TEXT DEFAULT 'flagged',
                detected_at TEXT NOT NULL,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS paper_trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                instrument_id INTEGER NOT NULL,
                buy_date TEXT NOT NULL,
                buy_price REAL NOT NULL,
                volume INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                sell_date TEXT,
                sell_price REAL,
                pnl_percent REAL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (instrument_id) REFERENCES instruments(id)
            )
        """)

        conn.commit()
    
    def _migrate_schema(self, conn):
        """
        Non-destructive schema migration.
        Add new columns to existing tables without data loss.
        """
        # Check and add columns that may not exist in older databases
        migrations = [
            ("instruments", "instrument_type", "TEXT"),
            ("instruments", "instrument_status", "TEXT DEFAULT 'active'"),
            ("instruments", "last_seen_at", "TEXT"),
            ("ohlcv_daily", "yesterday", "REAL"),
            ("ohlcv_daily", "is_valid", "INTEGER DEFAULT 1"),
            ("ohlcv_daily", "price_type", "TEXT DEFAULT 'raw'"),
            ("divergence_signals", "pivot_occurrence_date", "TEXT"),
            ("divergence_signals", "confirmation_date", "TEXT"),
            ("backtest_results", "entry_date", "TEXT"),
            ("backtest_results", "entry_type", "TEXT DEFAULT 'next_open'"),
            ("backtest_results", "horizon_5d_complete", "INTEGER DEFAULT 0"),
            ("backtest_results", "horizon_10d_complete", "INTEGER DEFAULT 0"),
            ("backtest_results", "horizon_20d_complete", "INTEGER DEFAULT 0"),
            ("backtest_results", "horizon_30d_complete", "INTEGER DEFAULT 0"),
            ("backtest_results", "transaction_cost", "REAL DEFAULT 0.0"),
        ]
        
        for table, column, col_type in migrations:
            try:
                conn.execute(f"SELECT {column} FROM {table} LIMIT 1")
            except sqlite3.OperationalError:
                try:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                except sqlite3.OperationalError:
                    pass  # Column may already exist with different case
        
        # Try to create UNIQUE index on divergence_signals if not exists
        # This is safe because we use IF NOT EXISTS
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_signals_unique 
                ON divergence_signals(instrument_id, signal_date, indicator, divergence_type, 
                                     price_pivot_1_date, price_pivot_2_date)
            """)
        except sqlite3.OperationalError:
            pass  # May fail if duplicates exist; we'll clean them up separately
        
        # Try to create UNIQUE index on backtest_results.signal_id
        try:
            conn.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_bt_signal_unique
                ON backtest_results(signal_id)
            """)
        except sqlite3.OperationalError:
            pass
        
        # Create Indexes after columns are guaranteed to exist
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_instrument_date ON ohlcv_daily(instrument_id, date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_date ON ohlcv_daily(date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_instrument ON divergence_signals(instrument_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_date ON divergence_signals(signal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_indicator_type ON divergence_signals(indicator, divergence_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_instrument ON backtest_results(instrument_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_date ON backtest_results(signal_date)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_type ON backtest_results(indicator, divergence_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_bt_signal_id ON backtest_results(signal_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_runs_stage ON pipeline_runs(stage, status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dq_instrument ON data_quality_issues(instrument_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_instruments_active ON instruments(active)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_instruments_type ON instruments(instrument_type)")
        
        conn.commit()
