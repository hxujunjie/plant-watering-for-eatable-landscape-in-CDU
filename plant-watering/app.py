import os
import io
import csv
from flask import Flask, render_template, request, jsonify, send_file
from PIL import Image, ImageOps
from database import init_db, add_watering_log, add_photo, get_recent_logs, \
    delete_watering_log, get_last_watering, get_all_names, get_logs_by_date, \
    get_marked_dates, get_all_photos_grouped_by_date, get_all_logs_for_export

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
    img = ImageOps.exif_transpose(img)
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buffer = io.BytesIO()
    fmt = img.format if img.format else 'JPEG'
    if fmt == 'PNG':
        img.save(buffer, format='PNG', optimize=True)
    else:
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')
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
    return render_template('index.html', last_watering=last_watering, names=names)


@app.route('/records')
def records():
    """记录页。"""
    return render_template('records.html')


@app.route('/api/checkin', methods=['POST'])
def checkin():
    """处理签到请求。"""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': '请输入姓名'}), 400

    log_id = add_watering_log(name)

    photo_count = 0
    files = request.files.getlist('photos')
    saved_files = []
    try:
        for file in files:
            if file and allowed_file(file.filename):
                buffer, ext = compress_image(file.stream)
                filename = f"{log_id}_{photo_count}_{os.urandom(4).hex()}.{ext}"
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                os.makedirs(UPLOAD_FOLDER, exist_ok=True)
                with open(filepath, 'wb') as f:
                    f.write(buffer.getvalue())
                saved_files.append(filepath)
                add_photo(log_id, f'/uploads/{filename}')
                photo_count += 1
    except Exception:
        delete_watering_log(log_id)
        for filepath in saved_files:
            if os.path.exists(filepath):
                os.remove(filepath)
        return jsonify({'success': False, 'error': '照片处理失败，请换一张照片重试'}), 400

    return jsonify({
        'success': True,
        'message': '签到成功',
        'name': name,
        'photo_count': photo_count
    })


@app.route('/api/logs', methods=['GET'])
def api_logs():
    """获取签到记录列表（分页）。"""
    page = request.args.get('page', 1, type=int)
    limit = 20
    offset = (page - 1) * limit
    logs = get_recent_logs(limit=limit, offset=offset)
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
    """获取某天的签到详情。"""
    year = request.args.get('year', type=int)
    month = request.args.get('month', type=int)
    day = request.args.get('day', type=int)
    if not all([year, month, day]):
        return jsonify({'error': '缺少参数'}), 400
    logs = get_logs_by_date(year, month, day)
    return jsonify({'logs': logs})


@app.route('/api/photos', methods=['GET'])
def api_photos():
    """获取所有照片（按日期分组）。"""
    groups = get_all_photos_grouped_by_date()
    return jsonify({'groups': groups})


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
        download_name='watering_log.xlsx'
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
        download_name='watering_log.csv'
    )


if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    app.run(debug=True, host='0.0.0.0', port=PORT)
