import sqlite3
import hashlib
import os

DB_FILE = "qrack.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member'
        );
        CREATE TABLE IF NOT EXISTS scan_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            qr_id TEXT NOT NULL,
            scanned_by TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            remark TEXT,
            verification_status TEXT
        );
    ''')
    # Create default team head if not exists
    head = c.execute("SELECT * FROM users WHERE role='head'").fetchone()
    if not head:
        pwd = hashlib.sha256("admin123".encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                  ("teamhead", pwd, "head"))
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_user(username):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    return user

def create_user(username, password, role='member'):
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                     (username, hash_password(password), role))
        conn.commit()
        conn.close()
        return True
    except:
        conn.close()
        return False

def log_scan(qr_id, scanned_by, remark, verification_status):
    conn = get_db()
    # Check if already scanned — update latest
    existing = conn.execute("SELECT id FROM scan_logs WHERE qr_id=?", (qr_id,)).fetchone()
    if existing:
        conn.execute('''UPDATE scan_logs SET scanned_by=?, timestamp=CURRENT_TIMESTAMP,
                     remark=?, verification_status=? WHERE qr_id=?''',
                     (scanned_by, remark, verification_status, qr_id))
    else:
        conn.execute('''INSERT INTO scan_logs (qr_id, scanned_by, remark, verification_status)
                     VALUES (?, ?, ?, ?)''', (qr_id, scanned_by, remark, verification_status))
    conn.commit()
    conn.close()

def get_scan_logs():
    conn = get_db()
    logs = conn.execute("SELECT * FROM scan_logs ORDER BY timestamp DESC").fetchall()
    conn.close()
    return [dict(l) for l in logs]

def get_all_users():
    conn = get_db()
    users = conn.execute("SELECT id, username, role FROM users").fetchall()
    conn.close()
    return [dict(u) for u in users]

def delete_user(user_id):
    conn = get_db()
    conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()