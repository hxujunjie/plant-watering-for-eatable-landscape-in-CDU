import os
import io
import json
import csv
import uuid
import tempfile
from flask import Flask, render_template, request, jsonify, send_file, redirect
from PIL import Image
from database import (
    get_db, init_db, add_watering_log, add_photo, get_recent_logs, \
    delete_watering_log, get_last_watering, get_all_names, get_logs_by_date, \
    get_marked_dates, get_all_photos_grouped_by_date, get_all_logs_for_export, \
    set_photo_tags, get_photo_tags, get_all_tags, create_tag, delete_tag, \
    get_photos_by_tag, get_photos_by_tags_intersection, get_photos_with_tags_by_log_id, \
    get_recent_logs_with_details, get_logs_by_date_with_details, \
    get_all_photos_with_tags_grouped_by_date, \
    add_board_message, get_board_messages, delete_board_message, \
    add_photo_comment, get_photo_comments, delete_photo_comment, \
    add_log_like, remove_log_like, get_log_likes, get_log_like_count, check_log_liked, \
    get_user_stats, get_monthly_summary
)
import backup

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB 上传限制

# 支持环境变量配置（Hugging Face Spaces 使用 7860 端口）
PORT = int(os.environ.get('PORT', 5000))
UPLOAD_FOLDER = os.environ.get('UPLOAD_DIR', os.path.join(os.path.dirname(__file__), 'static', 'uploads'))
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

# 如果上传目录不在 static 下，额外注册为静态文件路由
if not UPLOAD_FOLDER.endswith('static' + os.sep + 'uploads') and not UPLOAD_FOLDER.endswith('static/uploads'):
    app.config['UPLOAD_FOLDER_STATIC'] = UPLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def compress_image(file_stream, max_size=1200):
    """压缩图片，长边不超过 max_size 像素。"""
    img = Image.open(file_stream)
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    fmt = img.format if img.format else 'JPEG'
    if fmt == 'PNG':
        img.save(buffer, format='PNG', optimize=True)
    else:
        img.save(buffer, format='JPEG', quality=85, optimize=True)
    buffer.seek(0)
    return buffer, 'png' if fmt == 'PNG' else 'jpg'


@app.before_request
def ensure_db():
    """确保每次请求前数据库已初始化。"""
    init_db()


@app.route('/')
def index():
    """签到页（首页）。"""
    last_watering = get_last_watering()
    names = get_all_names()
    stats = get_user_stats()
    monthly = get_monthly_summary()
    return render_template('index.html', last_watering=last_watering, names=names, stats=stats, monthly=monthly)


@app.route('/records')
def records():
    """记录页。"""
    return render_template('records.html')


@app.route('/api/checkin', methods=['POST'])
def checkin():
    """处理签到请求，支持每张照片的 caption 和 tags。"""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': '请输入姓名'}), 400

    log_id = add_watering_log(name)

    photo_count = 0
    files = request.files.getlist('photos')
    for idx, file in enumerate(files):
        if file and allowed_file(file.filename):
            buffer, ext = compress_image(file.stream)
            filename = f"{log_id}_{photo_count}_{os.urandom(4).hex()}.{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            os.makedirs(UPLOAD_FOLDER, exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(buffer.getvalue())

            # 获取该照片的 caption 和 tags
            caption = request.form.get(f'caption_{idx}', '').strip()
            tags_str = request.form.get(f'tags_{idx}', '[]').strip()
            try:
                tag_ids = json.loads(tags_str) if tags_str else []
            except (json.JSONDecodeError, TypeError):
                tag_ids = []

            # 保存照片（含 caption）
            photo_id = add_photo(log_id, f'/uploads/{filename}', caption=caption)

            # 设置照片标签
            if tag_ids:
                set_photo_tags(photo_id, tag_ids)

            photo_count += 1

    _trigger_backup()
    return jsonify({
        'success': True,
        'message': '签到成功',
        'name': name,
        'photo_count': photo_count
    })


def _trigger_backup():
    """异步触发备份（失败静默忽略）。"""
    try:
        backup.schedule_backup()
    except Exception:
        pass


@app.route('/api/logs', methods=['GET'])
def api_logs():
    """获取签到记录列表（分页），含照片 caption 和 tags，支持排序。"""
    page = request.args.get('page', 1, type=int)
    order = request.args.get('order', 'desc')
    limit = 20
    offset = (page - 1) * limit
    logs = get_recent_logs_with_details(limit=limit, offset=offset, order=order)
    return jsonify({'logs': logs})


@app.route('/api/names', methods=['GET'])
def api_names():
    """获取所有历史姓名。"""
    names = get_all_names()
    return jsonify({'names': names})


@app.route('/api/last_watering', methods=['GET'])
def api_last_watering():
    """获取最近一次浇水信息。"""
    last = get_last_watering()
    return jsonify({'last_watering': last})


@app.route('/api/delete/<int:log_id>', methods=['DELETE'])
def delete_log(log_id):
    """撤销签到记录。"""
    delete_watering_log(log_id)
    _trigger_backup()
    return jsonify({'success': True, 'message': '已撤销'})


@app.route('/api/calendar', methods=['GET'])
def api_calendar():
    """获取日历数据：某月的标记日期。"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    if not year or not month:
        return jsonify({'error': '缺少参数'}), 400
    dates = get_marked_dates(year, month)
    return jsonify({'dates': dates})


@app.route('/api/calendar/detail', methods=['GET'])
def api_calendar_detail():
    """获取某天的签到详情，含照片 caption 和 tags。"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    day = request.args.get('day', type=int)
    if not all([year, month, day]):
        return jsonify({'error': '缺少参数'}), 400
    logs = get_logs_by_date_with_details(year, month, day)
    return jsonify({'logs': logs})


@app.route('/api/photos', methods=['GET'])
def api_photos():
    """获取所有照片（按日期分组），含 caption 和 tags。"""
    groups = get_all_photos_with_tags_grouped_by_date()
    return jsonify({'groups': groups})


# ========== Tag 标签 API ==========

@app.route('/api/tags', methods=['GET'])
def api_tags():
    """获取所有标签。"""
    tags = get_all_tags()
    return jsonify({'tags': tags})


@app.route('/api/tags', methods=['POST'])
def api_create_tag():
    """创建新标签，body: {name: "..."}。"""
    data = request.get_json()
    if not data or not data.get('name', '').strip():
        return jsonify({'success': False, 'error': '标签名称不能为空'}), 400
    name = data['name'].strip()
    try:
        tag_id = create_tag(name)
        return jsonify({'success': True, 'tag': {'id': tag_id, 'name': name}})
    except Exception as e:
        # 可能是 UNIQUE 约束冲突（标签已存在）
        if 'UNIQUE' in str(e):
            return jsonify({'success': False, 'error': '标签已存在'}), 409
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def api_delete_tag(tag_id):
    """删除标签（关联的 photo_tag 会级联删除）。"""
    delete_tag(tag_id)
    return jsonify({'success': True, 'message': '标签已删除'})


@app.route('/api/photos/<int:photo_id>', methods=['GET'])
def api_get_photo(photo_id):
    """获取单张照片详情（含tags和caption），供全屏查看器编辑使用。"""
    conn = get_db()
    row = conn.execute("SELECT id, file_path, caption FROM photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({'error': '照片不存在'}), 404
    tags = get_photo_tags(photo_id)
    conn.close()
    return jsonify({
        'id': row['id'],
        'file_path': row['file_path'],
        'caption': row['caption'],
        'tags': tags
    })


@app.route('/api/photos/<int:photo_id>/tags', methods=['PUT'])
def api_set_photo_tags(photo_id):
    """设置照片标签，body: {tag_ids: [1, 2, 3]}。"""
    data = request.get_json()
    if not data or 'tag_ids' not in data:
        return jsonify({'success': False, 'error': '缺少 tag_ids 参数'}), 400
    tag_ids = data['tag_ids']
    if not isinstance(tag_ids, list):
        return jsonify({'success': False, 'error': 'tag_ids 必须是数组'}), 400
    set_photo_tags(photo_id, tag_ids)
    tags = get_photo_tags(photo_id)
    return jsonify({'success': True, 'tags': tags})


@app.route('/api/photos/<int:photo_id>/caption', methods=['PUT'])
def api_update_photo_caption(photo_id):
    """更新照片注释，body: {caption: "..."}。"""
    data = request.get_json()
    if not data or 'caption' not in data:
        return jsonify({'success': False, 'error': '缺少 caption 参数'}), 400
    caption = data['caption']
    from database import get_db
    conn = get_db()
    conn.execute("UPDATE photo SET caption = ? WHERE id = ?", (caption, photo_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'caption': caption})


@app.route('/api/photos/by-tag/<int:tag_id>', methods=['GET'])
def api_photos_by_tag(tag_id):
    """按单个标签筛选照片，支持排序。"""
    order = request.args.get('order', 'desc')
    photos = get_photos_by_tag(tag_id, order=order)
    return jsonify({'photos': photos})


@app.route('/api/photos/by-tags', methods=['GET'])
def api_photos_by_tags():
    """按多个标签交集筛选照片，query: ?tag_ids=1,2,3&order=desc"""
    tag_ids_str = request.args.get('tag_ids', '')
    order = request.args.get('order', 'desc')
    tag_ids = [int(x) for x in tag_ids_str.split(',') if x.strip().isdigit()]
    if not tag_ids:
        return jsonify({'photos': []})
    photos = get_photos_by_tags_intersection(tag_ids, order=order)
    return jsonify({'photos': photos})


# ========== GIF 合成 API ==========

GIF_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'gifs')

@app.route('/api/gif/create', methods=['POST'])
def create_gif():
    """合成GIF动画。"""
    data = request.get_json()
    photo_ids = data.get('photo_ids', [])
    fps = data.get('fps', 2)
    size = data.get('size', 0)
    reverse = data.get('reverse', False)

    if not isinstance(photo_ids, list) or len(photo_ids) < 3 or len(photo_ids) > 20:
        return jsonify({'success': False, 'error': '请选择3-20张照片'}), 400
    fps = max(1, min(10, int(fps)))

    from database import get_db
    conn = get_db()
    placeholders = ','.join(['?' for _ in photo_ids])
    rows = conn.execute(
        'SELECT id, file_path FROM photo WHERE id IN (' + placeholders + ')',
        photo_ids
    ).fetchall()
    conn.close()

    if len(rows) != len(photo_ids):
        return jsonify({'success': False, 'error': '部分照片不存在'}), 400

    id_to_path = {r['id']: r['file_path'] for r in rows}
    paths = [id_to_path[pid] for pid in photo_ids]
    if reverse:
        paths.reverse()

    images = []
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for path in paths:
        filepath = os.path.join(base_dir, path.lstrip('/'))
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '照片文件丢失'}), 404
        img = Image.open(filepath)
        if img.mode != 'RGB':
            img = img.convert('RGB')
        if size > 0:
            img.thumbnail((size, size), Image.LANCZOS)
        images.append(img)

    os.makedirs(GIF_OUTPUT_DIR, exist_ok=True)
    gif_filename = 'temp_' + uuid.uuid4().hex[:8] + '.gif'
    gif_path = os.path.join(GIF_OUTPUT_DIR, gif_filename)

    duration_ms = int(1000 / fps)
    images[0].save(
        gif_path,
        save_all=True,
        append_images=images[1:],
        duration=duration_ms,
        loop=0,
        optimize=True
    )

    file_size = os.path.getsize(gif_path)

    def _format_size(bytes_num):
        if bytes_num < 1024:
            return str(bytes_num) + 'B'
        elif bytes_num < 1024 * 1024:
            return str(round(bytes_num / 1024, 1)) + 'KB'
        else:
            return str(round(bytes_num / (1024 * 1024), 1)) + 'MB'

    return jsonify({
        'success': True,
        'gif_url': '/uploads/gifs/' + gif_filename,
        'file_size': _format_size(file_size),
        'frame_count': len(images),
        'duration_ms': duration_ms * len(images)
    })

# ========== 黑板留言 API ==========

@app.route('/api/board', methods=['GET'])
def api_get_board():
    """获取黑板留言列表，支持分页和搜索。"""
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    keyword = request.args.get('keyword', '').strip()
    offset = (page - 1) * limit
    messages, total = get_board_messages(limit=limit, offset=offset, keyword=keyword)
    return jsonify({
        'messages': messages,
        'total': total,
        'page': page,
        'limit': limit,
        'has_more': offset + limit < total
    })


@app.route('/api/board', methods=['POST'])
def api_post_board():
    """发布黑板留言，body: {author, content, color}。"""
    data = request.get_json()
    if not data or not data.get('content', '').strip():
        return jsonify({'success': False, 'error': '留言内容不能为空'}), 400
    author = data.get('author', '匿名').strip() or '匿名'
    content = data['content'].strip()
    color = data.get('color', '#2c2416')
    msg_id = add_board_message(author, content, color)
    return jsonify({'success': True, 'msg_id': msg_id})


@app.route('/api/board/<int:msg_id>', methods=['DELETE'])
def api_delete_board(msg_id):
    """删除黑板留言。"""
    delete_board_message(msg_id)
    return jsonify({'success': True, 'message': '留言已删除'})


# ========== 照片留言 API ==========

@app.route('/api/photos/<int:photo_id>/comments', methods=['GET'])
def api_get_photo_comments(photo_id):
    """获取照片的留言列表。"""
    comments = get_photo_comments(photo_id)
    return jsonify({'comments': comments})


@app.route('/api/photos/<int:photo_id>/comments', methods=['POST'])
def api_add_photo_comment(photo_id):
    """给照片添加留言，body: {author, content}。"""
    data = request.get_json()
    if not data or not data.get('content', '').strip():
        return jsonify({'success': False, 'error': '留言内容不能为空'}), 400
    author = data.get('author', '匿名').strip() or '匿名'
    content = data['content'].strip()
    comment_id = add_photo_comment(photo_id, author, content)
    return jsonify({'success': True, 'comment_id': comment_id})


@app.route('/api/photos/<int:photo_id>/comments/<int:comment_id>', methods=['DELETE'])
def api_delete_photo_comment(photo_id, comment_id):
    """删除照片留言。"""
    delete_photo_comment(comment_id)
    return jsonify({'success': True, 'message': '留言已删除'})


# ========== 签到点赞 API ==========

@app.route('/api/logs/<int:log_id>/like', methods=['POST'])
def api_like_log(log_id):
    """点赞签到记录，body: {author}。"""
    data = request.get_json()
    if not data or not data.get('author', '').strip():
        return jsonify({'success': False, 'error': '缺少 author 参数'}), 400
    author = data['author'].strip()
    added = add_log_like(log_id, author)
    count = get_log_like_count(log_id)
    return jsonify({'success': True, 'added': added, 'like_count': count})


@app.route('/api/logs/<int:log_id>/like', methods=['DELETE'])
def api_unlike_log(log_id):
    """取消点赞，body: {author}。"""
    data = request.get_json()
    if not data or not data.get('author', '').strip():
        return jsonify({'success': False, 'error': '缺少 author 参数'}), 400
    author = data['author'].strip()
    remove_log_like(log_id, author)
    count = get_log_like_count(log_id)
    return jsonify({'success': True, 'like_count': count})


@app.route('/api/logs/<int:log_id>/likes', methods=['GET'])
def api_get_log_likes(log_id):
    """获取签到记录的点赞列表和数量。"""
    likes = get_log_likes(log_id)
    count = get_log_like_count(log_id)
    return jsonify({'likes': likes, 'like_count': count})


# ========== 黑板页面路由 ==========

@app.route('/board')
def board_page():
    """黑板留言板页面。"""
    return render_template('board.html')


@app.route('/codex')
def codex_page():
    """植物图鉴页面。"""
    return render_template('codex.html')


@app.route('/api/codex')
def api_codex():
    """获取图鉴列表数据（全部植物+解锁状态）。"""
    from database import get_all_codex_entries
    entries = get_all_codex_entries()
    return jsonify({'entries': entries})


@app.route('/codex/<int:plant_id>')
def codex_detail(plant_id):
    """植物图鉴详情页。"""
    from database import get_plant_detail
    detail = get_plant_detail(plant_id)
    if not detail:
        return redirect('/codex')
    return render_template('codex_detail.html', plant_id=plant_id, detail=detail)


@app.route('/api/codex/<int:plant_id>/timeline')
def api_codex_timeline(plant_id):
    """获取植物的时间线照片。"""
    from database import get_plant_timeline
    photos = get_plant_timeline(plant_id)
    return jsonify({'photos': photos})


@app.route('/api/codex/<int:plant_id>/stats')
def api_codex_stats(plant_id):
    """获取植物的月度统计数据。"""
    from database import get_plant_monthly_stats
    stats = get_plant_monthly_stats(plant_id)
    return jsonify({'stats': stats})


@app.route('/api/codex/reminders')
def api_codex_reminders():
    """获取已解锁植物的提醒信息。"""
    from database import get_plant_reminders
    reminders = get_plant_reminders()
    return jsonify({'reminders': reminders})


@app.route('/api/codex/<int:plant_id>/plans', methods=['GET', 'POST'])
def api_plant_plans(plant_id):
    """获取或新增某植物的计划。"""
    from database import get_plans, add_plan
    if request.method == 'POST':
        data = request.get_json()
        if not data or not data.get('content', '').strip():
            return jsonify({'success': False, 'error': '计划内容不能为空'}), 400
        plan_type = data.get('type', 'todo')
        custom_plant_name = data.get('custom_plant_name', '')
        content = data['content'].strip()
        due_date = data.get('due_date', '')
        plan_id = add_plan(plan_type, plant_id, custom_plant_name, content, due_date)
        return jsonify({'success': True, 'plan_id': plan_id})
    else:
        plans = get_plans(plant_id)
        return jsonify({'plans': plans})


@app.route('/api/plans/<int:plan_id>/complete', methods=['PUT'])
def api_complete_plan(plan_id):
    """将计划标记为已完成。"""
    from database import complete_plan
    complete_plan(plan_id)
    return jsonify({'success': True})


@app.route('/api/plans/<int:plan_id>', methods=['DELETE'])
def api_delete_plan(plan_id):
    """删除一条计划。"""
    from database import delete_plan
    delete_plan(plan_id)
    return jsonify({'success': True})


@app.route('/api/plans/pending-count')
def api_pending_plan_count():
    """获取所有未完成计划的总数。"""
    from database import get_pending_plan_count
    count = get_pending_plan_count()
    return jsonify({'count': count})


@app.route('/api/codex/<int:plant_id>/cultivation')
def api_codex_cultivation(plant_id):
    """获取某植物的培育等级。"""
    from database import get_plant_cultivation
    cultivation = get_plant_cultivation(plant_id)
    if not cultivation:
        return jsonify({'error': '植物不存在'}), 404
    return jsonify(cultivation)


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    """提供上传文件的访问路由。"""
    from flask import send_from_directory
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/export/excel')
def export_excel():
    """导出 Excel 文件。"""
    from openpyxl import Workbook
    logs = get_all_logs_for_export()
    wb = Workbook()
    ws = wb.active
    ws.title = "浇水签到记录"
    ws.append(["ID", "姓名", "签到时间", "照片数量"])
    for log in logs:
        ws.append([log['id'], log['name'], log['created_at'], log['photo_count']])
    ws.column_dimensions['A'].width = 8
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 22
    ws.column_dimensions['D'].width = 10

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return send_file(
        io.BytesIO(buffer.getvalue()),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='浇水签到记录.xlsx'
    )


@app.route('/export/csv')
def export_csv():
    """导出 CSV 文件。"""
    logs = get_all_logs_for_export()
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(["ID", "姓名", "签到时间", "照片数量"])
    for log in logs:
        writer.writerow([log['id'], log['name'], log['created_at'], log['photo_count']])
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8-sig'))
    output.seek(0)
    return send_file(
        output,
        mimetype='text/csv; charset=utf-8',
        as_attachment=True,
        download_name='浇水签到记录.csv'
    )


# ========== 备份 / 恢复 (admin) ==========

def _check_admin(req):
    """校验管理员密码（从 header / form / args 中读取）。"""
    pwd = req.headers.get('X-Admin-Password') or req.form.get('admin_password') or req.args.get('admin_password')
    if not backup.has_admin_password():
        return False, '后端未配置 BACKUP_ADMIN_PASSWORD'
    if not backup.admin_password_ok(pwd):
        return False, '管理员密码错误'
    return True, ''


@app.route('/api/backup/status', methods=['GET'])
def backup_status():
    """前端查询是否启用了备份功能（不暴露任何敏感信息）。"""
    return jsonify({
        'configured': backup.is_configured(),
        'has_password': backup.has_admin_password(),
    })


@app.route('/admin/backup', methods=['POST'])
def admin_backup_download():
    """下载完整备份 zip。"""
    ok, msg = _check_admin(request)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 401
    try:
        data = backup.get_zip_bytes()
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    ts = _dt.now(_tz(_td(hours=8))).strftime('%Y%m%d_%H%M%S')
    return send_file(
        io.BytesIO(data),
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'plant-watering-backup-{ts}.zip'
    )


@app.route('/admin/backup/push', methods=['POST'])
def admin_backup_push():
    """立即推送一次备份到 GitHub。"""
    ok, msg = _check_admin(request)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 401
    if not backup.is_configured():
        return jsonify({'success': False, 'error': '后端未配置 BACKUP_GITHUB_TOKEN/REPO'}), 400
    try:
        info = backup.push_now()
        return jsonify({'success': True, 'info': info})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/admin/restore', methods=['POST'])
def admin_restore():
    """从上传的 zip 恢复数据。"""
    ok, msg = _check_admin(request)
    if not ok:
        return jsonify({'success': False, 'error': msg}), 401
    f = request.files.get('backup_file')
    if not f:
        return jsonify({'success': False, 'error': '请上传备份 zip 文件'}), 400
    try:
        data = f.read()
        backup.restore_from_zip(data)
        return jsonify({'success': True, 'message': '恢复成功，请刷新页面'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ========== 趣味功能 API ==========

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """获取用户成就统计数据。"""
    stats = get_user_stats()
    monthly = get_monthly_summary()

    # 查询最擅长植物（培育等级最高且记录次数最多的已解锁植物）
    top_plant = None
    from database import sync_plant_unlocks, get_plant_by_id, calc_cultivation_level
    sync_plant_unlocks()
    db = get_db()
    unlocks = db.execute('''
        SELECT plant_lib_id, record_count, care_days
        FROM plant_unlock
        WHERE plant_lib_id IS NOT NULL
    ''').fetchall()
    db.close()

    if unlocks:
        best = None
        for u in unlocks:
            rc = u['record_count'] or 0
            cd = u['care_days'] or 0
            if rc > 0:
                cl = calc_cultivation_level(rc, cd)
                if best is None or cl['level'] > best['level'] or (cl['level'] == best['level'] and rc > best['rc']):
                    best = {'level': cl['level'], 'rc': rc, 'plant_lib_id': u['plant_lib_id']}
        if best:
            plant = get_plant_by_id(best['plant_lib_id'])
            if plant:
                top_plant = {
                    'name': plant['name'],
                    'level': best['level'],
                    'level_name': cl.get('level_name', ''),
                    'plant_lib_id': best['plant_lib_id']
                }

    return jsonify({'stats': stats, 'monthly': monthly, 'top_plant': top_plant})


@app.route('/api/achievements')
def api_achievements():
    """获取里程碑成就列表。"""
    from database import check_milestones
    achievements = check_milestones()
    return jsonify({'achievements': achievements})


@app.route('/profile')
def profile_page():
    """个人档案页。"""
    return render_template('profile.html')


@app.route('/api/profile')
def api_profile():
    """获取个人档案聚合数据。"""
    from database import check_milestones, sync_plant_unlocks, get_plant_by_id, calc_cultivation_level, PLANT_LIBRARY

    stats = get_user_stats()
    achievements = check_milestones()

    # 图鉴进度
    sync_plant_unlocks()
    db = get_db()
    unlocked_count = db.execute('SELECT COUNT(*) FROM plant_unlock WHERE plant_lib_id IS NOT NULL').fetchone()[0]
    total_count = len(PLANT_LIBRARY)
    db.close()

    # 培育排行 TOP5（按培育等级排序）
    db = get_db()
    unlocks = db.execute('''
        SELECT plant_lib_id, record_count, care_days
        FROM plant_unlock
        WHERE plant_lib_id IS NOT NULL AND record_count > 0
    ''').fetchall()
    db.close()

    rank_list = []
    for u in unlocks:
        rc = u['record_count'] or 0
        cd = u['care_days'] or 0
        cl = calc_cultivation_level(rc, cd)
        plant = get_plant_by_id(u['plant_lib_id'])
        if plant:
            rank_list.append({
                'name': plant['name'],
                'level': cl['level'],
                'level_name': cl.get('level_name', ''),
                'plant_lib_id': u['plant_lib_id'],
                'record_count': rc,
            })
    rank_list.sort(key=lambda x: (-x['level'], -x['record_count']))
    rank_list = rank_list[:5]

    # 最爱记录的植物 TOP3（按签到记录中 name 出现次数）
    db = get_db()
    top_names = db.execute('''
        SELECT name, COUNT(*) as cnt FROM watering_log
        GROUP BY name ORDER BY cnt DESC LIMIT 3
    ''').fetchall()
    db.close()
    top_plants = [{'name': r['name'], 'count': r['cnt']} for r in top_names]

    return jsonify({
        'stats': stats,
        'achievements': achievements,
        'codex_progress': {'unlocked': unlocked_count, 'total': total_count},
        'rank_list': rank_list,
        'top_plants': top_plants,
    })


# ========== 启动逻辑 ==========

# 在模块加载时执行：先建表，再尝试从 GitHub 恢复（如果库为空且远端有备份）
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
init_db()
try:
    backup.restore_on_startup_if_empty()
    # 恢复后表结构可能来自旧版本，重新 init_db 不会破坏已有表
    init_db()
except Exception as _e:
    import logging as _logging
    _logging.getLogger(__name__).warning('Startup restore error: %s', _e)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=PORT)
