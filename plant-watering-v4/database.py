import sqlite3
import os
from datetime import datetime, timezone, timedelta

# 数据库路径，支持环境变量覆盖
DB_PATH = os.path.join(os.path.dirname(__file__), 'watering.db')

# 北京时区（UTC+8）
BEIJING_TZ = timezone(timedelta(hours=8))


def current_time_str():
    """返回当前北京时间字符串，格式：YYYY-MM-DD HH:MM:SS"""
    return datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')


def get_db():
    """获取数据库连接，启用行工厂以返回字典。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate_db(conn):
    """数据库迁移：为已有表添加新列。"""
    # 检查 photo 表是否有 caption 列，没有则添加
    cursor = conn.execute("PRAGMA table_info(photo)")
    columns = [row['name'] for row in cursor.fetchall()]
    if 'caption' not in columns:
        conn.execute("ALTER TABLE photo ADD COLUMN caption TEXT NOT NULL DEFAULT ''")


def init_db():
    """初始化数据库，创建表（如果不存在）。"""
    conn = get_db()

    conn.executescript('''
        CREATE TABLE IF NOT EXISTS watering_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS photo (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watering_log_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT '',
            caption TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (watering_log_id) REFERENCES watering_log(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS tag (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at DATETIME NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS photo_tag (
            photo_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (photo_id, tag_id),
            FOREIGN KEY (photo_id) REFERENCES photo(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tag(id) ON DELETE CASCADE
        );

        -- 黑板留言
        CREATE TABLE IF NOT EXISTS board_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL DEFAULT '匿名',
            content TEXT NOT NULL,
            color TEXT DEFAULT '#2c2416',
            created_at DATETIME NOT NULL DEFAULT ''
        );

        -- 照片留言
        CREATE TABLE IF NOT EXISTS photo_comment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            photo_id INTEGER NOT NULL,
            author TEXT NOT NULL DEFAULT '匿名',
            content TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT '',
            FOREIGN KEY (photo_id) REFERENCES photo(id) ON DELETE CASCADE
        );

        -- 签到点赞
        CREATE TABLE IF NOT EXISTS log_like (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watering_log_id INTEGER NOT NULL,
            author TEXT NOT NULL DEFAULT '匿名',
            created_at DATETIME NOT NULL DEFAULT '',
            UNIQUE(watering_log_id, author),
            FOREIGN KEY (watering_log_id) REFERENCES watering_log(id) ON DELETE CASCADE
        );
    ''')
    conn.commit()

    # 迁移：为已有表添加新列
    _migrate_db(conn)

    # 预设 tag 种子数据：当 tag 表为空时插入
    count = conn.execute("SELECT COUNT(*) as cnt FROM tag").fetchone()['cnt']
    if count == 0:
        seed_tags = ['开花', '发芽', '浇水', '施肥', '虫害', '修剪', '换盆', '新叶', '枯萎', '结果']
        for tag_name in seed_tags:
            conn.execute(
                "INSERT INTO tag (name, created_at) VALUES (?, ?)",
                (tag_name, current_time_str())
            )
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


def add_photo(watering_log_id, file_path, caption=''):
    """为签到记录添加照片，可附带注释。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO photo (watering_log_id, file_path, created_at, caption) VALUES (?, ?, ?, ?)",
        (watering_log_id, file_path, current_time_str(), caption)
    )
    photo_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return photo_id


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


# ========== Tag 标签相关函数 ==========

def set_photo_tags(photo_id, tag_ids):
    """设置照片的标签（先删后增）。"""
    conn = get_db()
    conn.execute("DELETE FROM photo_tag WHERE photo_id = ?", (photo_id,))
    for tag_id in tag_ids:
        conn.execute(
            "INSERT INTO photo_tag (photo_id, tag_id) VALUES (?, ?)",
            (photo_id, tag_id)
        )
    conn.commit()
    conn.close()


def get_photo_tags(photo_id):
    """获取照片的所有标签，返回 [{id, name}, ...]。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT t.id, t.name
        FROM tag t
        JOIN photo_tag pt ON t.id = pt.tag_id
        WHERE pt.photo_id = ?
        ORDER BY t.name
    ''', (photo_id,)).fetchall()
    conn.close()
    return [{'id': r['id'], 'name': r['name']} for r in rows]


def get_all_tags():
    """获取所有标签。"""
    conn = get_db()
    rows = conn.execute("SELECT id, name, created_at FROM tag ORDER BY name").fetchall()
    conn.close()
    return [{'id': r['id'], 'name': r['name'], 'created_at': r['created_at']} for r in rows]


def create_tag(name):
    """创建新标签，返回新标签的 id。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO tag (name, created_at) VALUES (?, ?)",
        (name, current_time_str())
    )
    tag_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return tag_id


def delete_tag(tag_id):
    """删除标签（关联的 photo_tag 会级联删除）。"""
    conn = get_db()
    conn.execute("DELETE FROM tag WHERE id = ?", (tag_id,))
    conn.commit()
    conn.close()


def get_photos_by_tag(tag_id, order='desc'):
    """按标签筛选照片，返回 [{id, file_path, caption, watering_log_id, created_at}, ...]。"""
    conn = get_db()
    order_clause = 'DESC' if order == 'desc' else 'ASC'
    rows = conn.execute(
        'SELECT p.id, p.file_path, p.caption, p.watering_log_id, w.created_at '
        'FROM photo p '
        'JOIN photo_tag pt ON p.id = pt.photo_id '
        'JOIN watering_log w ON p.watering_log_id = w.id '
        'WHERE pt.tag_id = ? '
        'ORDER BY w.created_at ' + order_clause + ', p.created_at ' + order_clause,
        (tag_id,)
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        photo = {
            'id': r['id'],
            'file_path': r['file_path'],
            'caption': r['caption'],
            'watering_log_id': r['watering_log_id'],
            'created_at': r['created_at']
        }
        photo['tags'] = get_photo_tags(r['id'])
        result.append(photo)
    return result


def get_photos_by_tags_intersection(tag_ids, order='desc'):
    """按多个标签交集筛选照片（AND逻辑），返回同时拥有所有指定标签的照片。"""
    if not tag_ids:
        return []
    conn = get_db()
    order_clause = 'DESC' if order == 'desc' else 'ASC'
    # 构建动态SQL：每个标签一个条件，要求照片同时拥有所有标签
    placeholders = ','.join(['?' for _ in tag_ids])
    rows = conn.execute(
        'SELECT p.id, p.file_path, p.caption, p.watering_log_id, w.created_at '
        'FROM photo p '
        'JOIN watering_log w ON p.watering_log_id = w.id '
        'WHERE p.id IN ('
        '    SELECT photo_id FROM photo_tag WHERE tag_id IN (' + placeholders + ') '
        '    GROUP BY photo_id '
        '    HAVING COUNT(DISTINCT tag_id) = ?'
        ') '
        'ORDER BY w.created_at ' + order_clause + ', p.created_at ' + order_clause,
        tag_ids + [len(tag_ids)]
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        photo = {
            'id': r['id'],
            'file_path': r['file_path'],
            'caption': r['caption'],
            'watering_log_id': r['watering_log_id'],
            'created_at': r['created_at']
        }
        photo['tags'] = get_photo_tags(r['id'])
        result.append(photo)
    return result


def get_photos_with_tags_by_log_id(log_id):
    """获取签到记录的照片及标签。"""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, file_path, caption FROM photo WHERE watering_log_id = ? ORDER BY created_at",
        (log_id,)
    ).fetchall()
    conn.close()

    result = []
    for r in rows:
        photo = {
            'id': r['id'],
            'file_path': r['file_path'],
            'caption': r['caption']
        }
        photo['tags'] = get_photo_tags(r['id'])
        result.append(photo)
    return result


def get_recent_logs_with_details(limit=20, offset=0, order='desc'):
    """获取签到记录，支持排序（desc=从新到旧，asc=从旧到新），包含照片的 caption、tags 和 like_count。"""
    conn = get_db()
    order_clause = 'DESC' if order == 'desc' else 'ASC'
    rows = conn.execute(
        'SELECT w.id, w.name, w.created_at '
        'FROM watering_log w '
        'ORDER BY w.created_at ' + order_clause + ' '
        'LIMIT ? OFFSET ?',
        (limit, offset)
    ).fetchall()
    conn.close()

    logs = []
    for row in rows:
        photos = get_photos_with_tags_by_log_id(row['id'])
        logs.append({
            'id': row['id'],
            'name': row['name'],
            'created_at': row['created_at'],
            'photos': photos,
            'like_count': get_log_like_count(row['id'])
        })
    return logs


def get_logs_by_date_with_details(year, month, day):
    """获取指定日期的签到记录，包含照片的 caption、tags 和 like_count。"""
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
        photos = get_photos_with_tags_by_log_id(row['id'])
        logs.append({
            'id': row['id'],
            'name': row['name'],
            'created_at': row['created_at'],
            'photos': photos,
            'like_count': get_log_like_count(row['id'])
        })
    return logs


def get_all_photos_with_tags_grouped_by_date():
    """获取所有照片（含 caption、tags 和 comment_count），按日期分组（倒序）。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT p.id, p.file_path, p.caption, p.watering_log_id, w.created_at
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
        photo = {
            'id': r['id'],
            'file_path': r['file_path'],
            'caption': r['caption'],
            'watering_log_id': r['watering_log_id']
        }
        photo['tags'] = get_photo_tags(r['id'])
        photo['comment_count'] = _get_photo_comment_count(r['id'])
        groups[date_key].append(photo)
    return groups


def _get_photo_comment_count(photo_id):
    """获取照片的留言数量（内部辅助函数）。"""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM photo_comment WHERE photo_id = ?",
        (photo_id,)
    ).fetchone()
    conn.close()
    return row['cnt']


# ========== 黑板留言相关函数 ==========

def add_board_message(author, content, color='#2c2416'):
    """发布黑板留言，返回留言ID。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO board_message (author, content, color, created_at) VALUES (?, ?, ?, ?)",
        (author, content, color, current_time_str())
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return msg_id


def get_board_messages(limit=50, offset=0, keyword=''):
    """获取黑板留言（倒序），支持分页和关键词搜索。"""
    conn = get_db()
    if keyword:
        rows = conn.execute('''
            SELECT id, author, content, color, created_at
            FROM board_message
            WHERE content LIKE ? OR author LIKE ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', ('%' + keyword + '%', '%' + keyword + '%', limit, offset)).fetchall()
        total = conn.execute('''
            SELECT COUNT(*) as cnt FROM board_message
            WHERE content LIKE ? OR author LIKE ?
        ''', ('%' + keyword + '%', '%' + keyword + '%')).fetchone()['cnt']
    else:
        rows = conn.execute('''
            SELECT id, author, content, color, created_at
            FROM board_message
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset)).fetchall()
        total = conn.execute('SELECT COUNT(*) as cnt FROM board_message').fetchone()['cnt']
    conn.close()
    return [dict(r) for r in rows], total


def delete_board_message(msg_id):
    """删除黑板留言。"""
    conn = get_db()
    conn.execute("DELETE FROM board_message WHERE id = ?", (msg_id,))
    conn.commit()
    conn.close()


# ========== 照片留言相关函数 ==========

def add_photo_comment(photo_id, author, content):
    """给照片留言，返回留言ID。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO photo_comment (photo_id, author, content, created_at) VALUES (?, ?, ?, ?)",
        (photo_id, author, content, current_time_str())
    )
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return comment_id


def get_photo_comments(photo_id):
    """获取照片的留言列表（按时间正序）。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT id, author, content, created_at
        FROM photo_comment
        WHERE photo_id = ?
        ORDER BY created_at ASC
    ''', (photo_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_photo_comment(comment_id):
    """删除照片留言。"""
    conn = get_db()
    conn.execute("DELETE FROM photo_comment WHERE id = ?", (comment_id,))
    conn.commit()
    conn.close()


# ========== 签到点赞相关函数 ==========

def add_log_like(log_id, author):
    """点赞（如果已存在则忽略），返回是否成功新增。"""
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO log_like (watering_log_id, author, created_at) VALUES (?, ?, ?)",
            (log_id, author, current_time_str())
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        # UNIQUE 约束冲突，说明已点赞
        conn.close()
        return False


def remove_log_like(log_id, author):
    """取消点赞。"""
    conn = get_db()
    conn.execute(
        "DELETE FROM log_like WHERE watering_log_id = ? AND author = ?",
        (log_id, author)
    )
    affected = conn.total_changes
    conn.commit()
    conn.close()
    return affected > 0


def get_log_likes(log_id):
    """获取签到记录的点赞列表。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT id, author, created_at
        FROM log_like
        WHERE watering_log_id = ?
        ORDER BY created_at ASC
    ''', (log_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_log_like_count(log_id):
    """获取点赞数量。"""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM log_like WHERE watering_log_id = ?",
        (log_id,)
    ).fetchone()
    conn.close()
    return row['cnt']


def check_log_liked(log_id, author):
    """检查某作者是否已点赞。"""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM log_like WHERE watering_log_id = ? AND author = ?",
        (log_id, author)
    ).fetchone()
    conn.close()
    return row['cnt'] > 0
