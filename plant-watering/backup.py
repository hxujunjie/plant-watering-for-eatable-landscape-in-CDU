"""GitHub 备份模块。

将 SQLite 数据库 (watering.db) + 上传图片 (uploads/) 打包成 zip，
通过 GitHub Contents API 推送到一个私有备份仓库。

环境变量：
- BACKUP_GITHUB_TOKEN     : GitHub fine-grained token，仅授权对备份仓库的 Contents 写权限
- BACKUP_GITHUB_REPO      : owner/repo 形式，例如 hxujunjie/plant-watering-backups
- BACKUP_GITHUB_BRANCH    : 默认 main
- BACKUP_ADMIN_PASSWORD   : 管理员密码，下载/推送/恢复操作需要校验
"""
import os
import io
import json
import csv
import base64
import zipfile
import sqlite3
import threading
import logging
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

BEIJING_TZ = timezone(timedelta(hours=8))

GITHUB_API = "https://api.github.com"
LATEST_FILENAME = "latest.zip"          # 最新备份指针（覆盖式）
SNAPSHOT_DIR = "snapshots"              # 历史快照目录
DEBOUNCE_SECONDS = 60                   # 写操作触发后延迟多少秒再推

DB_PATH = os.environ.get('DB_PATH', os.path.join(os.path.dirname(__file__), 'watering.db'))
UPLOAD_DIR = os.environ.get(
    'UPLOAD_DIR',
    os.path.join(os.path.dirname(__file__), 'static', 'uploads')
)

GITHUB_TOKEN = (os.environ.get('BACKUP_GITHUB_TOKEN') or '').strip()
GITHUB_REPO = (os.environ.get('BACKUP_GITHUB_REPO') or '').strip()
GITHUB_BRANCH = (os.environ.get('BACKUP_GITHUB_BRANCH') or 'main').strip() or 'main'
ADMIN_PASSWORD = (os.environ.get('BACKUP_ADMIN_PASSWORD') or '').strip()

_lock = threading.Lock()
_pending_timer = None


def is_configured():
    """是否完成基础配置（可推送到 GitHub）。"""
    return bool(GITHUB_TOKEN and GITHUB_REPO)


def has_admin_password():
    return bool(ADMIN_PASSWORD)


def admin_password_ok(provided):
    if not ADMIN_PASSWORD:
        return False
    return (provided or '') == ADMIN_PASSWORD


def _gh_headers():
    return {
        'Authorization': 'token ' + GITHUB_TOKEN,
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }


def _safe_copy_db():
    """用 SQLite Backup API 安全复制数据库到 bytes，防止读到写一半的文件。"""
    if not os.path.exists(DB_PATH):
        return b''
    tmp_path = DB_PATH + '.bak.tmp'
    src = sqlite3.connect(DB_PATH)
    try:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        dst = sqlite3.connect(tmp_path)
        with dst:
            src.backup(dst)
        dst.close()
        with open(tmp_path, 'rb') as f:
            data = f.read()
        return data
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _build_zip_bytes():
    """打包 db + uploads + csv/json + readme。"""
    buf = io.BytesIO()
    now_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d %H:%M:%S')

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1) 数据库（安全复制）
        db_bytes = _safe_copy_db()
        if db_bytes:
            zf.writestr('watering.db', db_bytes)

        # 2) 上传图片
        if os.path.isdir(UPLOAD_DIR):
            for fname in sorted(os.listdir(UPLOAD_DIR)):
                fpath = os.path.join(UPLOAD_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        zf.write(fpath, arcname='uploads/' + fname)
                    except Exception as e:
                        logger.warning('Skip file %s: %s', fname, e)

        # 3) 人类可读导出（CSV + JSON）
        try:
            if os.path.exists(DB_PATH):
                conn = sqlite3.connect(DB_PATH)
                conn.row_factory = sqlite3.Row
                rows = conn.execute('''
                    SELECT w.id, w.name, w.created_at,
                           (SELECT COUNT(*) FROM photo WHERE watering_log_id = w.id) AS photo_count
                    FROM watering_log w
                    ORDER BY w.created_at DESC
                ''').fetchall()

                si = io.StringIO()
                writer = csv.writer(si)
                writer.writerow(['ID', '姓名', '签到时间', '照片数量'])
                data_list = []
                for r in rows:
                    writer.writerow([r['id'], r['name'], r['created_at'], r['photo_count']])
                    photos = conn.execute(
                        "SELECT id, file_path, created_at FROM photo "
                        "WHERE watering_log_id = ? ORDER BY created_at",
                        (r['id'],)
                    ).fetchall()
                    data_list.append({
                        'id': r['id'],
                        'name': r['name'],
                        'created_at': r['created_at'],
                        'photo_count': r['photo_count'],
                        'photos': [
                            {
                                'id': p['id'],
                                'file_path': p['file_path'],
                                'created_at': p['created_at'],
                            } for p in photos
                        ],
                    })
                conn.close()
                # 加 BOM 让 Excel 直接识别 UTF-8
                zf.writestr('records.csv', '\ufeff' + si.getvalue())
                zf.writestr(
                    'records.json',
                    json.dumps(data_list, ensure_ascii=False, indent=2)
                )
        except Exception as e:
            logger.warning('Generate readable export failed: %s', e)

        # 4) README
        readme = (
            '# 浇水签到 - 完整备份\n\n'
            f'备份时间：{now_str}（北京时间 UTC+8）\n\n'
            '## 文件说明\n'
            '- watering.db   ：SQLite 数据库（包含所有签到记录元数据）\n'
            '- uploads/      ：所有上传照片（按 logid 命名）\n'
            '- records.csv   ：CSV 表格（用 Excel 直接打开，含中文 BOM）\n'
            '- records.json  ：完整 JSON 数据（含每条记录的照片清单）\n\n'
            '## 恢复方式\n'
            '1. 在程序"备份与恢复"区，输入管理员密码，上传整个 ZIP 包；\n'
            '2. 或手动把 watering.db 放到容器的 $DB_PATH，把 uploads/ 内容复制到 $UPLOAD_DIR。\n'
        )
        zf.writestr('README.txt', readme)

    buf.seek(0)
    return buf.getvalue()


def _gh_get_file_sha(path):
    """返回 GitHub 上指定路径的文件 sha；不存在返回 None。"""
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    r = requests.get(url, headers=_gh_headers(), params={'ref': GITHUB_BRANCH}, timeout=30)
    if r.status_code == 200:
        body = r.json()
        if isinstance(body, dict):
            return body.get('sha')
        return None
    if r.status_code == 404:
        return None
    raise RuntimeError(f'GitHub get sha failed: {r.status_code} {r.text[:300]}')


def _gh_put_file(path, content_bytes, message):
    sha = _gh_get_file_sha(path)
    payload = {
        'message': message,
        'branch': GITHUB_BRANCH,
        'content': base64.b64encode(content_bytes).decode('ascii'),
    }
    if sha:
        payload['sha'] = sha
    url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{path}'
    r = requests.put(url, headers=_gh_headers(), json=payload, timeout=120)
    if r.status_code not in (200, 201):
        raise RuntimeError(f'GitHub put failed: {r.status_code} {r.text[:300]}')


def push_now():
    """同步推送一次完整备份到 GitHub。返回 dict。"""
    if not is_configured():
        raise RuntimeError('备份未配置（缺少 BACKUP_GITHUB_TOKEN 或 BACKUP_GITHUB_REPO）')
    with _lock:
        data = _build_zip_bytes()
        size = len(data)
        ts = datetime.now(BEIJING_TZ).strftime('%Y%m%d_%H%M%S')
        snapshot_path = f'{SNAPSHOT_DIR}/{ts}.zip'
        # 先存历史快照（每次新建）
        _gh_put_file(snapshot_path, data, f'snapshot {ts}')
        # 再覆盖 latest.zip
        _gh_put_file(LATEST_FILENAME, data, f'update latest {ts}')
        return {'snapshot': snapshot_path, 'size': size, 'time': ts}


def schedule_backup():
    """异步、防抖：每次写操作后调用，DEBOUNCE_SECONDS 内合并为一次推送。"""
    global _pending_timer
    if not is_configured():
        return
    with _lock:
        if _pending_timer is not None:
            try:
                _pending_timer.cancel()
            except Exception:
                pass

        def _run():
            try:
                info = push_now()
                logger.info('Auto backup pushed: %s', info)
            except Exception as e:
                logger.error('Auto backup failed: %s', e)

        _pending_timer = threading.Timer(DEBOUNCE_SECONDS, _run)
        _pending_timer.daemon = True
        _pending_timer.start()


def get_zip_bytes():
    """供管理员下载用。"""
    return _build_zip_bytes()


def restore_from_zip(zip_bytes):
    """从 zip 中恢复 watering.db + uploads/。会覆盖现有文件。"""
    bio = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(bio, 'r') as zf:
        names = zf.namelist()
        if 'watering.db' not in names:
            raise RuntimeError('zip 中缺少 watering.db')

        # 数据库
        db_dir = os.path.dirname(DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        with zf.open('watering.db') as src, open(DB_PATH, 'wb') as dst:
            dst.write(src.read())

        # 上传文件
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        for n in names:
            if n.startswith('uploads/') and not n.endswith('/'):
                fname = os.path.basename(n)
                if not fname:
                    continue
                with zf.open(n) as src, open(os.path.join(UPLOAD_DIR, fname), 'wb') as dst:
                    dst.write(src.read())


def _db_is_empty():
    if not os.path.exists(DB_PATH):
        return True
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='watering_log'"
        ).fetchone()
        if not row:
            conn.close()
            return True
        cnt = conn.execute("SELECT COUNT(*) FROM watering_log").fetchone()[0]
        conn.close()
        return cnt == 0
    except Exception:
        return True


def restore_on_startup_if_empty():
    """启动时调用：如果数据库为空，则尝试从 GitHub 拉 latest.zip 恢复。"""
    if not is_configured():
        logger.info('Backup not configured, skip startup restore')
        return False
    if not _db_is_empty():
        logger.info('Database not empty, skip startup restore')
        return False
    try:
        url = f'{GITHUB_API}/repos/{GITHUB_REPO}/contents/{LATEST_FILENAME}'
        r = requests.get(url, headers=_gh_headers(), params={'ref': GITHUB_BRANCH}, timeout=30)
        if r.status_code == 404:
            logger.info('No latest.zip on GitHub yet')
            return False
        if r.status_code != 200:
            logger.warning('Fetch latest.zip metadata failed: %s %s', r.status_code, r.text[:200])
            return False
        info = r.json()
        download_url = info.get('download_url')
        if not download_url:
            return False
        rr = requests.get(download_url, timeout=180)
        if rr.status_code != 200:
            logger.warning('Download latest.zip failed: %s', rr.status_code)
            return False
        restore_from_zip(rr.content)
        logger.info('Restored from GitHub backup, size=%d', len(rr.content))
        return True
    except Exception as e:
        logger.error('Startup restore failed: %s', e)
        return False
