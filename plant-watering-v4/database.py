import sqlite3
import os
from datetime import datetime, timezone, timedelta
from plant_library import PLANT_LIBRARY, match_tag_to_plant, get_plant_by_id, calc_cultivation_level, CULTIVATION_QUOTES, is_action_tag

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

        -- 植物解锁图鉴
        CREATE TABLE IF NOT EXISTS plant_unlock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plant_lib_id INTEGER,
            custom_name TEXT,
            tag_name TEXT NOT NULL,
            unlocked_at TEXT NOT NULL DEFAULT '',
            record_count INTEGER DEFAULT 0,
            care_days INTEGER DEFAULT 0,
            last_record_at TEXT,
            cover_photo_path TEXT
        );

        -- 园艺计划
        CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL DEFAULT 'todo',
            plant_lib_id INTEGER,
            custom_plant_name TEXT,
            content TEXT NOT NULL,
            due_date TEXT,
            completed INTEGER DEFAULT 0,
            completed_at TEXT,
            created_at TEXT NOT NULL DEFAULT ''
        );
    ''')
    conn.commit()

    # 迁移：为已有表添加新列
    _migrate_db(conn)

    # 添加 nickname 列（如果不存在）
    try:
        conn.execute('ALTER TABLE plant_unlock ADD COLUMN nickname TEXT DEFAULT ""')
    except:
        pass  # 列已存在

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


# ========== 成就系统相关函数 ==========

LEVELS = [
    (0, '种子', '🌱'),
    (50, '发芽', '🌿'),
    (150, '幼苗', '🪴'),
    (300, '成长', '🌳'),
    (500, '开花', '🌸'),
    (800, '结果', '🍎'),
    (1200, '大树', '🌲'),
    (1800, '园艺大师', '🏆'),
]

def get_user_stats():
    """获取用户统计数据（总经验、等级、各操作计数）。"""
    conn = get_db()
    log_count = conn.execute("SELECT COUNT(*) as cnt FROM watering_log").fetchone()['cnt']
    photo_count = conn.execute("SELECT COUNT(*) as cnt FROM photo").fetchone()['cnt']
    comment_count = conn.execute("SELECT COUNT(*) as cnt FROM photo_comment").fetchone()['cnt']
    like_count = conn.execute("SELECT COUNT(*) as cnt FROM log_like").fetchone()['cnt']
    board_count = conn.execute("SELECT COUNT(*) as cnt FROM board_message").fetchone()['cnt']
    tag_count = conn.execute("SELECT COUNT(*) as cnt FROM tag").fetchone()['cnt']

    # 计算总经验值
    total_xp = log_count * 5 + photo_count * 15 + comment_count * 3 + like_count * 2 + board_count * 3

    # 计算当前等级
    current_level = LEVELS[0]
    next_level = LEVELS[1] if len(LEVELS) > 1 else None
    for i in range(len(LEVELS) - 1, -1, -1):
        if total_xp >= LEVELS[i][0]:
            current_level = LEVELS[i]
            next_level = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
            break

    level_progress = 0
    if next_level:
        level_progress = (total_xp - current_level[0]) / (next_level[0] - current_level[0])

    # 获取最早和最晚记录日期
    first_log = conn.execute("SELECT created_at FROM watering_log ORDER BY created_at ASC LIMIT 1").fetchone()
    last_log = conn.execute("SELECT created_at FROM watering_log ORDER BY created_at DESC LIMIT 1").fetchone()

    conn.close()

    return {
        'total_xp': total_xp,
        'level_name': current_level[1],
        'level_icon': current_level[2],
        'level_xp': current_level[0],
        'next_level_name': next_level[1] if next_level else None,
        'next_level_xp': next_level[0] if next_level else None,
        'level_progress': min(level_progress, 1.0),
        'log_count': log_count,
        'photo_count': photo_count,
        'comment_count': comment_count,
        'like_count': like_count,
        'board_count': board_count,
        'tag_count': tag_count,
        'first_log_date': first_log['created_at'] if first_log else None,
        'last_log_date': last_log['created_at'] if last_log else None,
    }

def get_monthly_summary():
    """获取本月统计摘要。"""
    conn = get_db()
    now = current_time_str()
    month_prefix = now[:7]  # YYYY-MM

    month_logs = conn.execute(
        "SELECT COUNT(*) as cnt FROM watering_log WHERE created_at LIKE ?",
        (month_prefix + '%',)
    ).fetchone()['cnt']

    month_photos = conn.execute(
        "SELECT COUNT(*) as cnt FROM photo WHERE created_at LIKE ?",
        (month_prefix + '%',)
    ).fetchone()['cnt']

    # 获取本月最常记录的植物名
    top_name = conn.execute('''
        SELECT name, COUNT(*) as cnt FROM watering_log
        WHERE created_at LIKE ?
        GROUP BY name ORDER BY cnt DESC LIMIT 1
    ''', (month_prefix + '%',)).fetchone()

    # 获取本月总留言数
    month_comments = conn.execute(
        "SELECT COUNT(*) as cnt FROM photo_comment WHERE created_at LIKE ?",
        (month_prefix + '%',)
    ).fetchone()['cnt']

    conn.close()

    return {
        'month_logs': month_logs,
        'month_photos': month_photos,
        'month_comments': month_comments,
        'top_plant_name': top_name['name'] if top_name else None,
        'top_plant_count': top_name['cnt'] if top_name else 0,
    }


# ========== 植物图鉴相关函数 ==========

def sync_plant_unlocks():
    """扫描所有标签，匹配植物库，同步 plant_unlock 表。
    - 匹配到的标签：更新或创建 plant_unlock 记录（plant_lib_id 有值）
    - 未匹配到的标签：创建自定义条目（plant_lib_id 为 NULL，custom_name = tag_name）
    - 同时统计每个已解锁植物的 record_count 和 care_days
    """
    conn = get_db()
    tags = conn.execute("SELECT id, name FROM tag ORDER BY name").fetchall()

    for tag in tags:
        tag_name = tag['name']

        # 跳过行为标签（如开花、浇水等），它们不是植物名称
        if is_action_tag(tag_name):
            continue

        plant = match_tag_to_plant(tag_name)

        if plant:
            # 匹配到植物库：plant_lib_id 有值
            plant_lib_id = plant['id']
            existing = conn.execute(
                "SELECT id FROM plant_unlock WHERE plant_lib_id = ?",
                (plant_lib_id,)
            ).fetchone()

            if existing:
                # 已存在，更新 tag_name（取最新的匹配标签名）
                conn.execute(
                    "UPDATE plant_unlock SET tag_name = ? WHERE id = ?",
                    (tag_name, existing['id'])
                )
            else:
                # 新建解锁记录
                conn.execute(
                    "INSERT INTO plant_unlock (plant_lib_id, tag_name, unlocked_at) VALUES (?, ?, ?)",
                    (plant_lib_id, tag_name, current_time_str())
                )
        else:
            # 未匹配到植物库：检查是否已有该标签名的自定义条目
            existing = conn.execute(
                "SELECT id FROM plant_unlock WHERE plant_lib_id IS NULL AND tag_name = ?",
                (tag_name,)
            ).fetchone()

            if not existing:
                conn.execute(
                    "INSERT INTO plant_unlock (custom_name, tag_name, unlocked_at) VALUES (?, ?, ?)",
                    (tag_name, tag_name, current_time_str())
                )

    conn.commit()

    # 统计每个已解锁植物的 record_count、care_days、last_record_at、cover_photo_path
    unlocks = conn.execute("SELECT id, tag_name FROM plant_unlock").fetchall()
    for unlock in unlocks:
        tag_name = unlock['tag_name']

        # 通过 tag_name 找到 tag_id，再通过 photo_tag -> photo -> watering_log 统计
        tag_row = conn.execute(
            "SELECT id FROM tag WHERE name = ?", (tag_name,)
        ).fetchone()

        if tag_row:
            tag_id = tag_row['id']

            # record_count: 该标签关联的照片所属的不同签到记录数
            count_row = conn.execute('''
                SELECT COUNT(DISTINCT p.watering_log_id) as cnt
                FROM photo_tag pt
                JOIN photo p ON pt.photo_id = p.id
                WHERE pt.tag_id = ?
            ''', (tag_id,)).fetchone()
            record_count = count_row['cnt'] if count_row else 0

            # care_days: 该标签关联的照片所属签到记录的不同日期数
            days_row = conn.execute('''
                SELECT COUNT(DISTINCT date(w.created_at)) as cnt
                FROM photo_tag pt
                JOIN photo p ON pt.photo_id = p.id
                JOIN watering_log w ON p.watering_log_id = w.id
                WHERE pt.tag_id = ?
            ''', (tag_id,)).fetchone()
            care_days = days_row['cnt'] if days_row else 0

            # last_record_at: 最近一条关联记录的时间
            last_row = conn.execute('''
                SELECT MAX(w.created_at) as latest
                FROM photo_tag pt
                JOIN photo p ON pt.photo_id = p.id
                JOIN watering_log w ON p.watering_log_id = w.id
                WHERE pt.tag_id = ?
            ''', (tag_id,)).fetchone()
            last_record_at = last_row['latest'] if last_row else None

            # cover_photo_path: 该标签关联的最早一张照片路径
            cover_row = conn.execute('''
                SELECT p.file_path
                FROM photo_tag pt
                JOIN photo p ON pt.photo_id = p.id
                WHERE pt.tag_id = ?
                ORDER BY p.created_at ASC
                LIMIT 1
            ''', (tag_id,)).fetchone()
            cover_photo_path = cover_row['file_path'] if cover_row else None
        else:
            record_count = 0
            care_days = 0
            last_record_at = None
            cover_photo_path = None

        conn.execute('''
            UPDATE plant_unlock
            SET record_count = ?, care_days = ?, last_record_at = ?, cover_photo_path = ?
            WHERE id = ?
        ''', (record_count, care_days, last_record_at, cover_photo_path, unlock['id']))

    conn.commit()
    conn.close()


def get_all_codex_entries():
    """获取图鉴全部条目（预设植物+自定义），标记解锁状态。
    先调用 sync_plant_unlocks() 扫描所有标签，匹配植物库。
    返回列表，每个条目包含：id, name, category, unlocked, record_count, care_days, cover_url, description。
    """
    # 先同步标签到植物解锁表
    sync_plant_unlocks()

    conn = get_db()

    # 获取所有已解锁的记录
    unlocks = conn.execute('''
        SELECT id, plant_lib_id, custom_name, tag_name, unlocked_at,
               record_count, care_days, last_record_at, cover_photo_path, nickname
        FROM plant_unlock
        ORDER BY plant_lib_id ASC NULLS LAST, id ASC
    ''').fetchall()

    # 构建已解锁植物的映射：plant_lib_id -> unlock记录
    unlocked_by_lib_id = {}
    # 收集自定义植物
    custom_entries = []
    # 记录已出现的 plant_lib_id
    seen_lib_ids = set()

    for u in unlocks:
        if u['plant_lib_id'] is not None:
            unlocked_by_lib_id[u['plant_lib_id']] = dict(u)
            seen_lib_ids.add(u['plant_lib_id'])
        else:
            custom_entries.append(dict(u))

    # 构建结果列表
    entries = []

    # 1. 预设植物（20种）
    for plant in PLANT_LIBRARY:
        is_unlocked = plant['id'] in unlocked_by_lib_id
        unlock_info = unlocked_by_lib_id.get(plant['id'], {})

        # 计算培育等级
        cultivation_level = 0
        if is_unlocked:
            rc = unlock_info.get('record_count', 0) or 0
            cd = unlock_info.get('care_days', 0) or 0
            if rc > 0:
                cl = calc_cultivation_level(rc, cd)
                cultivation_level = cl['level']

        entries.append({
            'id': plant['id'],
            'name': plant['name'],
            'category': plant['category'],
            'care_tip': plant['care_tip'],
            'unlocked': is_unlocked,
            'record_count': unlock_info.get('record_count', 0) if is_unlocked else 0,
            'care_days': unlock_info.get('care_days', 0) if is_unlocked else 0,
            'cover_url': unlock_info.get('cover_photo_path', '') if is_unlocked else '',
            'description': plant['description'],
            'is_custom': False,
            'cultivation_level': cultivation_level,
            'silhouette_url': plant.get('silhouette_path', ''),
            'illustration_url': plant.get('illustration_path', ''),
            'nickname': unlock_info.get('nickname', '') if is_unlocked else '',
        })

    # 2. 自定义植物（不在植物库中的标签）
    for custom in custom_entries:
        entries.append({
            'id': custom['id'],
            'name': custom['custom_name'],
            'category': '自定义',
            'care_tip': '',
            'unlocked': True,
            'record_count': custom.get('record_count', 0),
            'care_days': custom.get('care_days', 0),
            'cover_url': custom.get('cover_photo_path', ''),
            'description': '用户自定义植物',
            'is_custom': True,
            'silhouette_url': '',
            'illustration_url': '',
            'nickname': custom.get('nickname', ''),
        })

    conn.close()
    return entries


def get_plant_detail(plant_lib_id):
    """获取某个预设植物的详细数据。
    返回：植物库信息 + 解锁信息 + 记录次数 + 养护天数 + 最近记录时间 + 封面照片。
    如果植物未解锁，unlocked 为 False，其余统计字段为默认值。
    """
    plant = get_plant_by_id(plant_lib_id)
    if not plant:
        return None

    conn = get_db()
    unlock = conn.execute(
        "SELECT * FROM plant_unlock WHERE plant_lib_id = ?",
        (plant_lib_id,)
    ).fetchone()
    conn.close()

    if unlock:
        return {
            'id': plant['id'],
            'name': plant['name'],
            'aliases': plant['aliases'],
            'category': plant['category'],
            'care_tip': plant['care_tip'],
            'description': plant['description'],
            'unlocked': True,
            'unlocked_at': unlock['unlocked_at'],
            'tag_name': unlock['tag_name'],
            'record_count': unlock['record_count'] or 0,
            'care_days': unlock['care_days'] or 0,
            'last_record_at': unlock['last_record_at'],
            'cover_url': unlock['cover_photo_path'] or '',
            'nickname': unlock['nickname'] or '',
        }
    else:
        return {
            'id': plant['id'],
            'name': plant['name'],
            'aliases': plant['aliases'],
            'category': plant['category'],
            'care_tip': plant['care_tip'],
            'description': plant['description'],
            'unlocked': False,
            'unlocked_at': None,
            'tag_name': None,
            'record_count': 0,
            'care_days': 0,
            'last_record_at': None,
            'cover_url': '',
            'nickname': '',
        }


def get_plant_timeline(plant_lib_id):
    """获取某个植物的所有照片（通过标签匹配），按时间正序排列。"""
    plant = get_plant_by_id(plant_lib_id)
    if not plant:
        return []
    db = get_db()
    # 通过别名找到匹配的tag_id
    tag_ids = []
    for alias in plant['aliases']:
        tag = db.execute('SELECT id FROM tag WHERE name = ?', (alias,)).fetchone()
        if tag:
            tag_ids.append(tag['id'])
    if not tag_ids:
        db.close()
        return []
    # 查询这些tag关联的照片
    placeholders = ','.join(['?'] * len(tag_ids))
    photos = db.execute('''
        SELECT p.id, p.file_path, p.caption, p.created_at, p.watering_log_id
        FROM photo p
        JOIN photo_tag pt ON p.id = pt.photo_id
        WHERE pt.tag_id IN (%s)
        ORDER BY p.created_at ASC
    ''' % placeholders, tag_ids).fetchall()
    db.close()
    return [dict(p) for p in photos]


def update_plant_nickname(plant_lib_id, nickname):
    """更新植物的昵称。"""
    db = get_db()
    db.execute('UPDATE plant_unlock SET nickname = ? WHERE plant_lib_id = ?', (nickname, plant_lib_id))
    db.commit()
    db.close()


def get_plant_monthly_stats(plant_lib_id):
    """获取某个植物的按月统计（记录次数+照片数量）。"""
    plant = get_plant_by_id(plant_lib_id)
    if not plant:
        return []
    db = get_db()
    tag_ids = []
    for alias in plant['aliases']:
        tag = db.execute('SELECT id FROM tag WHERE name = ?', (alias,)).fetchone()
        if tag:
            tag_ids.append(tag['id'])
    if not tag_ids:
        db.close()
        return []
    placeholders = ','.join(['?'] * len(tag_ids))
    rows = db.execute('''
        SELECT strftime('%%Y-%%m', p.created_at) as month,
               COUNT(DISTINCT p.watering_log_id) as log_count,
               COUNT(p.id) as photo_count
        FROM photo p
        JOIN photo_tag pt ON p.id = pt.photo_id
        WHERE pt.tag_id IN (%s)
        GROUP BY month
        ORDER BY month ASC
    ''' % placeholders, tag_ids).fetchall()
    db.close()
    return [dict(r) for r in rows]


# ========== 轻量化提醒相关函数 ==========

def get_plant_reminders():
    """获取已解锁植物的提醒信息（距上次记录天数）。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT plant_lib_id, custom_name, tag_name, last_record_at, record_count, care_days
        FROM plant_unlock
        WHERE last_record_at IS NOT NULL
        ORDER BY last_record_at ASC
    ''').fetchall()
    conn.close()

    now = datetime.now(BEIJING_TZ)
    reminders = []
    for r in rows:
        last_str = r['last_record_at']
        if not last_str:
            continue
        try:
            last_dt = datetime.strptime(last_str, '%Y-%m-%d %H:%M:%S')
            last_dt = last_dt.replace(tzinfo=BEIJING_TZ)
        except ValueError:
            try:
                last_dt = datetime.strptime(last_str[:10], '%Y-%m-%d')
                last_dt = last_dt.replace(tzinfo=BEIJING_TZ)
            except ValueError:
                continue
        days_since = (now - last_dt).days
        # 获取植物名
        if r['plant_lib_id']:
            plant = get_plant_by_id(r['plant_lib_id'])
            name = plant['name'] if plant else r['custom_name'] or r['tag_name']
        else:
            name = r['custom_name'] or r['tag_name']
        reminders.append({
            'plant_lib_id': r['plant_lib_id'],
            'name': name,
            'days_since_last': days_since,
            'last_record_at': last_str,
        })
    # 按days_since_last倒序排列
    reminders.sort(key=lambda x: x['days_since_last'], reverse=True)
    return reminders


# ========== 园艺计划相关函数 ==========

def add_plan(type, plant_lib_id, custom_plant_name, content, due_date):
    """新增一条园艺计划。"""
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO plans (type, plant_lib_id, custom_plant_name, content, due_date, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (type, plant_lib_id, custom_plant_name, content, due_date, current_time_str())
    )
    plan_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return plan_id


def get_plans(plant_lib_id):
    """获取某植物的所有计划（未完成在前，已完成在后）。"""
    conn = get_db()
    rows = conn.execute('''
        SELECT id, type, plant_lib_id, custom_plant_name, content, due_date,
               completed, completed_at, created_at
        FROM plans
        WHERE plant_lib_id = ?
        ORDER BY completed ASC, created_at DESC
    ''', (plant_lib_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_plan_count():
    """获取所有未完成计划的总数。"""
    conn = get_db()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM plans WHERE completed = 0"
    ).fetchone()
    conn.close()
    return row['cnt']


def complete_plan(plan_id):
    """将计划标记为已完成。"""
    conn = get_db()
    conn.execute(
        "UPDATE plans SET completed = 1, completed_at = ? WHERE id = ?",
        (current_time_str(), plan_id)
    )
    conn.commit()
    conn.close()


def delete_plan(plan_id):
    """删除一条计划。"""
    conn = get_db()
    conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    conn.commit()
    conn.close()


# ========== 单株植物培育等级 ==========

def get_plant_cultivation(plant_lib_id):
    """获取某植物的培育等级。"""
    plant = get_plant_by_id(plant_lib_id)
    if not plant:
        return None

    conn = get_db()
    unlock = conn.execute(
        "SELECT record_count, care_days FROM plant_unlock WHERE plant_lib_id = ?",
        (plant_lib_id,)
    ).fetchone()
    conn.close()

    record_count = unlock['record_count'] or 0 if unlock else 0
    care_days = unlock['care_days'] or 0 if unlock else 0

    result = calc_cultivation_level(record_count, care_days)
    result['plant_name'] = plant['name']
    # 填充文案
    quote_template = CULTIVATION_QUOTES.get(result['level'], '')
    result['quote'] = quote_template.replace('{plant}', plant['name'])
    return result


# ========== 里程碑成就系统 ==========

MILESTONES = [
    {'id': 'first_record', 'name': '初次记录', 'icon': '🌱', 'desc': '完成第一次签到'},
    {'id': 'week_streak', 'name': '周连续', 'icon': '📅', 'desc': '连续 7 天有记录'},
    {'id': 'month_streak', 'name': '月连续', 'icon': '🗓️', 'desc': '连续 30 天有记录'},
    {'id': 'collector_10', 'name': '收藏家', 'icon': '📚', 'desc': '解锁 10 种植物'},
    {'id': 'collector_25', 'name': '大收藏家', 'icon': '🏛️', 'desc': '解锁 25 种植物'},
    {'id': 'photographer', 'name': '摄影师', 'icon': '📷', 'desc': '累计上传 100 张照片'},
    {'id': 'social', 'name': '社交蝴蝶', 'icon': '🦋', 'desc': '发布 50 条留言'},
    {'id': 'botanist', 'name': '植物学家', 'icon': '🏆', 'desc': '达到最高等级'},
]


def check_consecutive_days(n):
    """检查最近n天是否连续有记录，返回连续天数。"""
    db = get_db()
    rows = db.execute('''
        SELECT DISTINCT DATE(created_at) as day
        FROM watering_log
        WHERE created_at >= DATE('now', '-' || ? || ' days')
        ORDER BY day DESC
    ''', (n,)).fetchall()
    db.close()
    if not rows:
        return 0
    consecutive = 0
    check_date = datetime.now(BEIJING_TZ).date()
    recorded_days = set(r['day'] for r in rows)
    for i in range(n):
        date_str = check_date.strftime('%Y-%m-%d')
        if date_str in recorded_days:
            consecutive += 1
            check_date -= timedelta(days=1)
        else:
            break
    return consecutive


def check_milestones():
    """检查所有里程碑的达成状态。返回列表，每个元素包含milestone信息+unlocked(bool)。"""
    db = get_db()
    stats = get_user_stats()
    results = []

    # 初次记录
    log_count = stats['log_count']
    results.append({'id': 'first_record', 'unlocked': log_count >= 1})

    # 周连续
    days = check_consecutive_days(7)
    results.append({'id': 'week_streak', 'unlocked': days >= 7})

    # 月连续
    days = check_consecutive_days(30)
    results.append({'id': 'month_streak', 'unlocked': days >= 30})

    # 收藏家 / 大收藏家
    unlocked_count = db.execute('SELECT COUNT(*) FROM plant_unlock WHERE plant_lib_id IS NOT NULL').fetchone()[0]
    results.append({'id': 'collector_10', 'unlocked': unlocked_count >= 10})
    results.append({'id': 'collector_25', 'unlocked': unlocked_count >= 25})

    # 摄影师
    results.append({'id': 'photographer', 'unlocked': stats['photo_count'] >= 100})

    # 社交蝴蝶
    board_count = db.execute('SELECT COUNT(*) FROM board_message').fetchone()[0]
    results.append({'id': 'social', 'unlocked': board_count >= 50})

    # 植物学家（最高等级 = LEVELS 最后一个）
    max_level_xp = LEVELS[-1][0]
    results.append({'id': 'botanist', 'unlocked': stats['total_xp'] >= max_level_xp})

    db.close()

    # 补充milestone的其他字段
    for r in results:
        m = next(x for x in MILESTONES if x['id'] == r['id'])
        r.update({k: v for k, v in m.items() if k != 'id'})

    return results
