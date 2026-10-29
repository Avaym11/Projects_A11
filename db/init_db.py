import sqlite3, os
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "ecommerce.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    our_price   REAL NOT NULL,
    cost        REAL NOT NULL,
    currency    TEXT DEFAULT 'USD'
);

CREATE TABLE IF NOT EXISTS mock_prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  TEXT NOT NULL,
    competitor  TEXT NOT NULL,
    price       REAL NOT NULL,
    currency    TEXT DEFAULT 'USD',
    in_stock    INTEGER DEFAULT 1,
    status      TEXT DEFAULT 'In Stock',
    promo       TEXT,
    cached_price REAL,
    UNIQUE(product_id, competitor)
);

CREATE TABLE IF NOT EXISTS price_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  TEXT NOT NULL,
    old_price   REAL,
    new_price   REAL NOT NULL,
    decided_by  TEXT NOT NULL,
    reason      TEXT,
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pending_approvals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT NOT NULL,
    proposed_price  REAL NOT NULL,
    safe_price      REAL,
    reason          TEXT,
    flag            TEXT,
    status          TEXT DEFAULT 'pending',
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT,
    product_id  TEXT NOT NULL,
    old_price   REAL,
    new_price   REAL,
    decided_by  TEXT,
    reason      TEXT,
    status      TEXT,
    intercepted INTEGER DEFAULT 0
);
"""

SEED_PRODUCTS = [
    ("P001", "Sony WH-1000XM5 Headphones", 299.99, 180.00),
    ("P002", "Apple MacBook Air M2",        1199.99, 850.00),
    ("P003", "Samsung Galaxy S24",           799.99, 520.00),
    ("P004", "Logitech MX Master 3 Mouse",   99.99,  55.00),
    ("P005", "iPad Pro 11-inch",             999.99, 680.00),
]

SEED_MOCK_PRICES = [
    ("P001", "Amazon",   279.99, "USD", 1, "In Stock",  None),
    ("P001", "Walmart",  289.00, "USD", 1, "In Stock",  None),
    ("P001", "EU Store", 249.00, "EUR", 1, "In Stock",  None),
    ("P002", "Amazon",   1149.00,"USD", 1, "In Stock",  None),
    ("P002", "BestBuy",  1179.00,"USD", 0, "Out of Stock", None),
    ("P002", "EU Store", 1050.00,"EUR", 1, "Flash Sale","flash_sale"),
    ("P003", "Amazon",   769.99, "USD", 1, "In Stock",  None),
    ("P003", "Walmart",  749.00, "USD", 1, "In Stock",  None),
    ("P003", "EU Store", 699.00, "EUR", 0, "Out of Stock", None),
    ("P004", "Amazon",   94.99,  "USD", 1, "In Stock",  None),
    ("P004", "Walmart",  89.00,  "USD", 1, "In Stock",  None),
    ("P004", "EU Store", 82.00,  "EUR", 1, "In Stock",  None),
    ("P005", "Amazon",   979.00, "USD", 1, "In Stock",  None),
    ("P005", "BestBuy",  999.00, "USD", 0, "Out of Stock", None),
    ("P005", "EU Store", 899.00, "EUR", 1, "Flash Sale","flash_sale"),
]

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.executemany(
        "INSERT OR IGNORE INTO products (id, name, our_price, cost) VALUES (?,?,?,?)",
        SEED_PRODUCTS
    )
    conn.executemany(
        "INSERT OR REPLACE INTO mock_prices (product_id, competitor, price, currency, in_stock, status, promo) VALUES (?,?,?,?,?,?,?)",
        SEED_MOCK_PRICES
    )
    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
