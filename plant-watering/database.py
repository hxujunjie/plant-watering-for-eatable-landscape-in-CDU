import sqlite3
import os
from datetime import datetime, timezone, timedelta

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'watering.db'))

# 项目所在地区为中国大陆，统一使用北京时间（UTC+8）。
# Hugging Face Spaces 容器默认 UTC，sqlite 的 datetime('now', 'localtime') 在该环境下仍取 UTC，
# 因此改为应用层显式生成北京时间字符串。
BEIJING_TZ = timezone(timedelta(hours=8))


def current_time_str():
    """返回北京时间字符串（YYYY-MM-DD HH:MM:SS），与 SQLite 默认格式兼容。"""
    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')


def get_db():
    """获取数据库连接，启用行工厂以返回字典。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """初始化数据库，创建表（如果不存在）。"""
    conn = get_db()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS watering_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT (datetime('now', '+8 hours'))
        );

        CREATE TABLE IF NOT EXISTS photo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watering_log_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT (datetime('now', '+8 hours')),
            FOREIGN KEY (watering_log_id) REFERENCES watering_log(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()
    conn.close()


def add_watering_log(name):
    """新增一条签到记录，返回记录ID。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO watering_log (name, created_at) VALUES (?, ?)",
        (name, current_time_str())
    )
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def add_photo(watering_log_id, file_path):
    """为签到记录添加照片。"""
    conn = get_db()
    columns = {row['name'] for row in conn.execute("PRAGMA table_info(photo)").fetchall()}
    if 'caption' in columns:
        conn.execute(
            "INSERT INTO photo (watering_log_id, file_path, caption, created_at) VALUES (?, ?, ?, ?)",
            (watering_log_id, file_path, '', current_time_str())
        )
    else:
        conn.execute(
            "INSERT INTO photo (watering_log_id, file_path, created_at) VALUES (?, ?, ?)",
            (watering_log_id, file_path, current_time_str())
        )
    conn.commit()
    conn.close()


def get_recent_logs(limit=20, offset=0):
    """获取最近的签到记录（倒序），包含关联照片。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT w.id, w.name, w.created_at
        FROM watering_log w
        ORDER BY w.created_at DESC
        LIMIT ? OFFSET ?
    ''', (limit, offset)).fetchall()
    conn.close()

    logs = []
    for row in rows:
        photos = get_photos_by_log_id(row['id'])
        logs.append({
            'id': row['id'],
            'name': row['name'],
            'created_at': row['created_at'],
            'photos': photos
        })
    return logs


def get_photos_by_log_id(log_id):
    """获取某条签到记录的所有照片。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, file_path FROM photo WHERE watering_log_id = ? ORDER BY created_at",
        (log_id,)
    ).fetchall()
    conn.close()
    return [{'id': r['id'], 'file_path': r['file_path']} for r in rows]


def delete_watering_log(log_id):
    """删除签到记录及其关联照片文件。"""
    conn = get_db()
    photos = conn.execute(
        "SELECT file_path FROM photo WHERE watering_log_id = ?", (log_id,)
    ).fetchall()
    for p in photos:
        filepath = os.path.join(os.path.dirname(__file__), p['file_path'].lstrip('/'))
        if os.path.exists(filepath):
            os.remove(filepath)
    conn.execute("DELETE FROM watering_log WHERE id = ?", (log_id,))
    conn.commit()
    conn.close()


def get_last_watering():
    """获取最近一次浇水记录。"""
    conn = get_db()
    row = conn.execute(
        "SELECT name, created_at FROM watering_log ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        return {'name': row['name'], 'created_at': row['created_at']}
    return None


def get_all_names():
    """获取所有签到过的姓名（按最近使用排序）。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT DISTINCT name FROM watering_log ORDER BY created_at DESC
    ''').fetchall()
    conn.close()
    return [r['name'] for r in rows]


def get_logs_by_date(year, month, day):
    """获取指定日期的所有签到记录。"""
    date_str = f"{year:04d}-{month:02d}-{day:02d}"
    conn = get_db()
    rows = conn.execute('''
        SELECT w.id, w.name, w.created_at
        FROM watering_log w
        WHERE date(w.created_at) = ?
        ORDER BY w.created_at DESC
    ''', (date_str,)).fetchall()
    conn.close()

    logs = []
    for row in rows:
        photos = get_photos_by_log_id(row['id'])
        logs.append({
            'id': row['id'],
            'name': row['name'],
            'created_at': row['created_at'],
            'photos': photos
        })
    return logs


def get_marked_dates(year, month):
    """获取指定月份中有签到记录的日期集合。"""
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"
    conn = get_db()
    rows = conn.execute('''
        SELECT DISTINCT date(created_at) as d FROM watering_log
        WHERE date(created_at) >= ? AND date(created_at) < ?
    ''', (start, end)).fetchall()
    conn.close()
    return [r['d'] for r in rows]


def get_all_photos_grouped_by_date():
    """获取所有照片，按日期分组（倒序）。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT p.id, p.file_path, p.watering_log_id, w.created_at
        FROM photo p
        JOIN watering_log w ON p.watering_log_id = w.id
        ORDER BY w.created_at DESC, p.created_at DESC
    ''').fetchall()
    conn.close()

    groups = {}
    for r in rows:
        date_key = r['created_at'][:10]
        if date_key not in groups:
            groups[date_key] = []
        groups[date_key].append({
            'id': r['id'],
            'file_path': r['file_path'],
            'watering_log_id': r['watering_log_id']
        })
    return groups


def get_all_logs_for_export():
    """获取所有签到记录用于导出。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT w.id, w.name, w.created_at,
               (SELECT COUNT(*) FROM photo WHERE watering_log_id = w.id) as photo_count
        FROM watering_log w
        ORDER BY w.created_at DESC
    ''').fetchall()
    conn.close()
    return [dict(r) for r in rows]
