import sqlite3
import datetime

DB_PATH = "bot_data.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            joined_at TEXT,
            last_active TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            approved_at TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS visitors_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()

    defaults = {
        "description": "🔥 *Premium Telegram Channel*\n\n✅ Daily exclusive updates\n✅ Premium content access\n✅ Lifetime membership\n\n💰 Price: ₹299 only!",
        "channel_link": "https://t.me/your_channel",
        "upi_id": "yourname@upi",
        "price": "299",
        "proof_text": "📸 Check our proof channel: https://t.me/your_proof_channel",
        "demo_text": "👁 Demo: https://t.me/demo_channel",
        "qr_file_id": "",
        "product_photo_file_id": "",
    }
    conn = get_conn()
    c = conn.cursor()
    for key, val in defaults.items():
        c.execute("INSERT OR IGNORE INTO config (key, value) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()


def get_config(key):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return row["value"] if row else ""


def set_config(key, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def add_user(user_id, username, first_name):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("""
        INSERT OR IGNORE INTO users (user_id, username, first_name, joined_at, last_active)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, username, first_name, now, now))
    if c.rowcount == 0:
        c.execute("UPDATE users SET last_active=?, username=? WHERE user_id=?",
                  (now, username, user_id))
    conn.commit()
    conn.close()


def get_user_count():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    return c.fetchone()[0]


def get_all_users():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, username, first_name, joined_at, last_active FROM users ORDER BY joined_at DESC")
    return c.fetchall()


def create_order(user_id, username):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO orders (user_id, username, status, created_at) VALUES (?, ?, 'pending', ?)",
              (user_id, username, now))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id


def approve_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("UPDATE orders SET status='approved', approved_at=? WHERE id=?", (now, order_id))
    conn.commit()
    conn.close()


def decline_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE orders SET status='declined' WHERE id=?", (order_id,))
    conn.commit()
    conn.close()


def get_pending_orders():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, created_at FROM orders WHERE status='pending' ORDER BY id DESC")
    return c.fetchall()


def get_order(order_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id=?", (order_id,))
    return c.fetchone()


def get_all_orders():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, user_id, username, status, created_at, approved_at FROM orders ORDER BY id DESC")
    return c.fetchall()


def get_order_stats():
    conn = get_conn()
    c = conn.cursor()
    total = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    pending = c.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
    approved = c.execute("SELECT COUNT(*) FROM orders WHERE status='approved'").fetchone()[0]
    declined = c.execute("SELECT COUNT(*) FROM orders WHERE status='declined'").fetchone()[0]
    conn.close()
    return {"total": total, "pending": pending, "approved": approved, "declined": declined}


def log_action(user_id, action):
    conn = get_conn()
    c = conn.cursor()
    now = datetime.datetime.now().isoformat()
    c.execute("INSERT INTO visitors_log (user_id, action, timestamp) VALUES (?, ?, ?)",
              (user_id, action, now))
    conn.commit()
    conn.close()


def get_recent_logs(limit=20):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, user_id, action, timestamp FROM visitors_log ORDER BY id DESC LIMIT ?", (limit,))
    return c.fetchall()


def get_log_count():
    conn = get_conn()
    c = conn.cursor()
    return c.execute("SELECT COUNT(*) FROM visitors_log").fetchone()[0]