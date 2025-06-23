import os
import sqlite3
import shutil
from functools import wraps
from flask import (
    Flask, request, send_from_directory, abort, render_template_string,
    redirect, url_for, flash, jsonify, session
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from urllib.parse import unquote

app = Flask(__name__)
app.secret_key = 'change_this_to_a_random_secret_key'  # Please change this to a random secret key for production

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')  # SQLite database path
USER_FILES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')  # Root directory for user files
os.makedirs(USER_FILES_ROOT, exist_ok=True)  # Ensure the directory exists

def get_db_connection():  # Get a database connection, rows as dictionary
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database():  # Initialize the user table
    connection = get_db_connection()
    cursor = connection.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    connection.commit()
    connection.close()

initialize_database()  # Initialize DB at startup

def login_required(function):  # Login required decorator
    @wraps(function)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.path))
        return function(*args, **kwargs)
    return wrapper

def safe_join(base_path, *paths):  # Safely join paths; prevent path traversal
    final_path = os.path.abspath(os.path.join(base_path, *paths))
    if not final_path.startswith(base_path):
        raise ValueError("Attempted access outside of base directory")
    return final_path

def build_breadcrumb(sub_path):  # Build breadcrumb list for navigation
    crumbs = [("Root", url_for('list_files', subpath=''))]
    if not sub_path:
        return crumbs
    parts = sub_path.strip('/').split('/')
    accumulated_path = []
    for part in parts:
        accumulated_path.append(part)
        crumbs.append((part, url_for('list_files', subpath='/'.join(accumulated_path))))
    return crumbs

def is_image_file(filename):  # Check if file is an image by extension
    ext = filename.lower().rsplit('.', 1)[-1]
    return ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff']

def is_video_file(filename):  # Check if file is a video by extension
    ext = filename.lower().rsplit('.', 1)[-1]
    return ext in ['mp4', 'webm', 'ogg', 'mov', 'avi', 'flv', 'mkv']

def get_current_user_dir():  # Get the file directory for the current user
    current_username = session.get('username')
    if not current_username:
        abort(403)
    user_directory = os.path.join(USER_FILES_ROOT, current_username)
    os.makedirs(user_directory, exist_ok=True)
    return user_directory

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password2', '')

        if not username or not password or not password_confirm:
            flash("Please complete all fields", "warning")
            return redirect(request.url)
        if password != password_confirm:
            flash("Passwords do not match", "danger")
            return redirect(request.url)

        password_hash = generate_password_hash(password)
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
            connection.commit()
            flash("Registration successful, please log in", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash("Username already exists", "danger")
            return redirect(request.url)
        finally:
            connection.close()

    return render_template_string(TEMPLATES['register'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        connection.close()

        if user and check_password_hash(user['password_hash'], password):
            session['username'] = username
            flash("Login successful", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('list_files'))
        else:
            flash("Invalid username or password", "danger")
            return redirect(request.url)

    return render_template_string(TEMPLATES['login'])

@app.route('/logout')
def logout():
    session.pop('username', None)  # Clear login session
    flash("Logged out", "info")
    return redirect(url_for('login'))

@app.route('/changepwd', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        old_password = request.form.get('oldpassword', '')
        new_password = request.form.get('newpassword', '')
        new_password_confirm = request.form.get('newpassword2', '')

        if not old_password or not new_password or not new_password_confirm:
            flash("Please fill all fields", "warning")
            return redirect(request.url)
        if new_password != new_password_confirm:
            flash("New passwords do not match", "danger")
            return redirect(request.url)

        current_username = session['username']
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (current_username,))
        user = cursor.fetchone()
        if not user or not check_password_hash(user['password_hash'], old_password):
            flash("Old password incorrect", "danger")
            connection.close()
            return redirect(request.url)

        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, current_username))
        connection.commit()
        connection.close()
        flash("Password changed successfully, please login again", "success")
        return redirect(url_for('logout'))

    return render_template_string(TEMPLATES['changepwd'])

@app.route('/files/', defaults={'subpath': ''})
@app.route('/files/<path:subpath>')
@login_required
def list_files(subpath):
    subpath = unquote(subpath)
    user_dir = get_current_user_dir()
    try:
        abs_path = safe_join(user_dir, subpath)
    except ValueError:
        abort(403)

    if not os.path.isdir(abs_path):
        abort(404, description="Directory not found")

    entries = []
    for entry_name in os.listdir(abs_path):
        entry_path = os.path.join(abs_path, entry_name)
        entry_info = {
            'name': entry_name,
            'is_dir': os.path.isdir(entry_path),
            'is_image': False,
            'is_video': False
        }
        if not entry_info['is_dir']:
            entry_info['is_image'] = is_image_file(entry_name)
            entry_info['is_video'] = is_video_file(entry_name)
        entries.append(entry_info)
    entries.sort(key=lambda entry: (not entry['is_dir'], entry['name'].lower()))  # directories first, then alphabetically

    parent_path = os.path.dirname(subpath) if subpath else None
    breadcrumb = build_breadcrumb(subpath)

    return render_template_string(TEMPLATES['list'],
                                  entries=entries,
                                  current_path=subpath,
                                  parent_path=parent_path,
                                  breadcrumb=breadcrumb,
                                  username=session.get('username'))

@app.route('/upload/', defaults={'subpath': ''}, methods=['GET', 'POST'])
@app.route('/upload/<path:subpath>', methods=['GET', 'POST'])
@login_required
def upload_file(subpath):
    subpath = unquote(subpath)
    user_dir = get_current_user_dir()
    try:
        upload_dir = safe_join(user_dir, subpath)
    except ValueError:
        abort(403)

    os.makedirs(upload_dir, exist_ok=True)

    if request.method == 'POST':
        if 'file' not in request.files:
            flash("No file part in the request", "danger")
            return redirect(request.url)
        upload_file = request.files['file']
        if upload_file.filename == '':
            flash("No selected file", "warning")
            return redirect(request.url)
        filename = secure_filename(upload_file.filename)
        save_path = os.path.join(upload_dir, filename)
        upload_file.save(save_path)
        flash(f"File '{filename}' uploaded successfully!", "success")
        return redirect(url_for('list_files', subpath=subpath))

    breadcrumb = build_breadcrumb(subpath)
    return render_template_string(TEMPLATES['upload'],
                                  current_path=subpath,
                                  breadcrumb=breadcrumb,
                                  username=session.get('username'))

@app.route('/download/<path:filepath>')
@login_required
def download_file(filepath):
    filepath = unquote(filepath)
    user_dir = get_current_user_dir()
    try:
        abs_path = safe_join(user_dir, filepath)
    except ValueError:
        abort(403)

    if not os.path.isfile(abs_path):
        abort(404)
    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/move', methods=['POST'])
@login_required
def api_move():
    request_data = request.json or {}
    source_path = request_data.get('src_path')
    destination_path = request_data.get('dst_path')
    if not source_path or not destination_path:
        return jsonify(success=False, message="Missing parameters"), 400

    user_dir = get_current_user_dir()
    try:
        abs_source = safe_join(user_dir, source_path)
        abs_destination = safe_join(user_dir, destination_path)
    except ValueError:
        return jsonify(success=False, message="Invalid path"), 403

    if not os.path.exists(abs_source):
        return jsonify(success=False, message="Source does not exist"), 404
    if not os.path.isdir(abs_destination):
        return jsonify(success=False, message="Destination must be a directory"), 400

    dest_final = os.path.join(abs_destination, os.path.basename(abs_source))
    if os.path.exists(dest_final):
        return jsonify(success=False, message="Destination already has a file/folder with the same name"), 409

    try:
        os.rename(abs_source, dest_final)
    except Exception as ex:
        return jsonify(success=False, message=f"Move failed: {ex}"), 500

    return jsonify(success=True)

@app.route('/api/delete', methods=['POST'])
@login_required
def api_delete():
    request_data = request.json or {}
    target_path = request_data.get('target_path')
    if not target_path:
        return jsonify(success=False, message="Missing parameter"), 400

    user_dir = get_current_user_dir()
    try:
        abs_target = safe_join(user_dir, target_path)
    except ValueError:
        return jsonify(success=False, message="Invalid path"), 403

    if not os.path.exists(abs_target):
        return jsonify(success=False, message="File or folder does not exist"), 404

    try:
        if os.path.isfile(abs_target):
            os.remove(abs_target)
        else:
            shutil.rmtree(abs_target)
    except Exception as ex:
        return jsonify(success=False, message=f"Delete failed: {ex}"), 500

    return jsonify(success=True)

@app.route('/api/rename', methods=['POST'])
@login_required
def api_rename():
    request_data = request.json or {}
    target_path = request_data.get('target_path')
    new_name = request_data.get('new_name')
    if not target_path or not new_name:
        return jsonify(success=False, message="Missing parameter"), 400

    user_dir = get_current_user_dir()
    try:
        abs_target = safe_join(user_dir, target_path)
    except ValueError:
        return jsonify(success=False, message="Invalid path"), 403

    if not os.path.exists(abs_target):
        return jsonify(success=False, message="File or folder does not exist"), 404

    parent_directory = os.path.dirname(abs_target)
    new_name_safe = secure_filename(new_name)
    new_abs_path = os.path.join(parent_directory, new_name_safe)

    if os.path.exists(new_abs_path):
        return jsonify(success=False, message="A file or folder with new name exists in the same directory"), 409

    try:
        os.rename(abs_target, new_abs_path)
    except Exception as ex:
        return jsonify(success=False, message=f"Rename failed: {ex}"), 500

    return jsonify(success=True)

def lcs_length(string1, string2):  # Calculates longest common subsequence length for two strings
    length1 = len(string1)
    length2 = len(string2)
    dp_matrix = []
    for index_i in range(length1 + 1):
        dp_matrix.append([0] * (length2 + 1))
    for index_i in range(length1):
        for index_j in range(length2):
            if string1[index_i] == string2[index_j]:
                dp_matrix[index_i + 1][index_j + 1] = dp_matrix[index_i][index_j] + 1
            else:
                dp_matrix[index_i + 1][index_j + 1] = max(dp_matrix[index_i][index_j + 1], dp_matrix[index_i + 1][index_j])
    return dp_matrix[length1][length2]

def walk_user_files(root_directory):  # Recursively traverse all files and directories under root_directory
    results = []
    to_process_paths = ['']  # empty string represents root relative path
    while to_process_paths:
        current_relative_path = to_process_paths.pop()
        absolute_path = os.path.join(root_directory, current_relative_path)
        try:
            entries_in_directory = os.listdir(absolute_path)
        except Exception:
            continue
        for entry in entries_in_directory:
            entry_relative_path = os.path.join(current_relative_path, entry)
            entry_absolute_path = os.path.join(root_directory, entry_relative_path)
            if os.path.isdir(entry_absolute_path):
                results.append({'path': entry_relative_path, 'is_dir': True})
                to_process_paths.append(entry_relative_path)
            else:
                results.append({'path': entry_relative_path, 'is_dir': False})
    return results

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip()
        if not keyword:
            flash("Please input search keyword", "warning")
            return redirect(url_for('search'))

        user_directory = get_current_user_dir()
        all_files = walk_user_files(user_directory)

        matches = []
        keyword_lower = keyword.lower()
        for file_entry in all_files:
            base_name_lower = os.path.basename(file_entry['path']).lower()
            lcs_score = lcs_length(base_name_lower, keyword_lower)
            if lcs_score > 0:
                matches.append((lcs_score, base_name_lower, file_entry))
        matches.sort(key=lambda match_tuple: (-match_tuple[0], match_tuple[1]))  # Sort by LCS descending, filename ascending

        search_results = []
        for lcs_score, base_lower, file_entry in matches:
            search_results.append(file_entry)
        current_user = session['username']

        return render_template_string(TEMPLATES['search_results'],
                                      keyword=keyword,
                                      results=search_results,
                                      username=current_user)
    else:
        current_user = session['username']
        return render_template_string(TEMPLATES['search_page'], username=current_user)
TEMPLATES = {
    'base': '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>用户文件管理系统</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <!-- 引入Bootstrap 5样式 -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet" />
  <style>
    /* 右键菜单淡入动画效果 */
    #contextMenuDropdown.show {
      animation: fadeInDropdown 0.15s ease forwards;
    }
    @keyframes fadeInDropdown {
      from {opacity: 0; transform: translateY(-10px);}
      to {opacity: 1; transform: translateY(0);}
    }
    /* 拖拽时高亮显示 */
    tr.dragover {
      background-color: #a9def9 !important;
      transition: background-color 0.3s ease;
    }
    tr {
      transition: background-color 0.3s ease;
    }
    /* 改变光标为抓手，拖拽时为抓紧手 */
    tr[draggable="true"] {
      cursor: grab;
    }
    tr[draggable="true"]:active {
      cursor: grabbing;
    }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('list_files', subpath='') }}">文件管理系统</a>
    <div class="collapse navbar-collapse">
      {% if session.username %}
      <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
        <!-- 显示登录用户名 -->
        <li class="nav-item pe-2 text-white">用户: <strong>{{ session.username }}</strong></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('search') }}">搜索</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('change_password') }}">修改密码</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">登出</a></li>
      </ul>
      {% else %}
      <ul class="navbar-nav ms-auto mb-2 mb-lg-0">
        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
      </ul>
      {% endif %}
    </div>
  </div>
</nav>
<div class="container">
  <!-- 显示闪现消息通知 -->
  {% with messages = get_flashed_messages(with_categories=true) %}
  {% if messages %}
    {% for category, message in messages %}
    <div class="alert alert-{{category}} alert-dismissible fade show" role="alert">
      {{ message }}
      <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
    </div>
    {% endfor %}
  {% endif %}
  {% endwith %}
  {% block content %}{% endblock %}
</div>

<!-- 引入Bootstrap 5 JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
''',
    'register': '''
{% extends base %}
{% block content %}
<div class="mx-auto" style="max-width: 400px;">
  <h3 class="mb-4">注册</h3>
  <form method="post" novalidate>
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <!-- 用户名输入: 3-20字符，字母数字下划线 -->
      <input type="text" class="form-control" id="username" name="username" required minlength="3" maxlength="20"
             pattern="^[a-zA-Z0-9_]+$" autofocus />
      <small class="form-text text-muted">只能包含字母、数字、下划线，长度3-20</small>
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input type="password" class="form-control" id="password" name="password" required minlength="6" maxlength="64" />
    </div>
    <div class="mb-3">
      <label for="password2" class="form-label">确认密码</label>
      <input type="password" class="form-control" id="password2" name="password2" required minlength="6" maxlength="64" />
    </div>
    <button type="submit" class="btn btn-primary w-100">注册</button>
    <div class="mt-3 text-center">
      <a href="{{ url_for('login') }}">已有账号？去登录</a>
    </div>
  </form>
</div>
{% endblock %}
''',
    'login': '''
{% extends base %}
{% block content %}
<div class="mx-auto" style="max-width: 400px;">
  <h3 class="mb-4">登录</h3>
  <form method="post" novalidate>
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input type="text" class="form-control" id="username" name="username" required autofocus />
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input type="password" class="form-control" id="password" name="password" required />
    </div>
    <button type="submit" class="btn btn-primary w-100">登录</button>
    <div class="mt-3 text-center">
      <a href="{{ url_for('register') }}">没有账号？去注册</a>
    </div>
  </form>
</div>
{% endblock %}
''',
    'changepwd': '''
{% extends base %}
{% block content %}
<div class="mx-auto" style="max-width: 400px;">
  <h3 class="mb-4">修改密码</h3>
  <form method="post" novalidate>
    <div class="mb-3">
      <label for="oldpassword" class="form-label">旧密码</label>
      <input type="password" class="form-control" id="oldpassword" name="oldpassword" required autofocus />
    </div>
    <div class="mb-3">
      <label for="newpassword" class="form-label">新密码</label>
      <input type="password" class="form-control" id="newpassword" name="newpassword" required minlength="6" maxlength="64" />
    </div>
    <div class="mb-3">
      <label for="newpassword2" class="form-label">确认新密码</label>
      <input type="password" class="form-control" id="newpassword2" name="newpassword2" required minlength="6" maxlength="64" />
    </div>
    <button type="submit" class="btn btn-primary w-100">修改密码</button>
    <div class="mt-3 text-center">
      <a href="{{ url_for('list_files') }}">返回文件管理</a>
    </div>
  </form>
</div>
{% endblock %}
''',
    'list': '''
{% extends base %}
{% block content %}
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    {% for name, link in breadcrumb %}
      <li class="breadcrumb-item {% if loop.last %}active{% endif %}"
          {% if loop.last %}aria-current="page"{% else %}><a href="{{ link }}">{% endif %}>
        {{ name }}
      {% if not loop.last %}</a>{% endif %}
      </li>
    {% endfor %}
  </ol>
</nav>

<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>欢迎，{{ username }}，当前目录：{{ '/' + current_path if current_path else '/' }}</h4>
  <a href="{{ url_for('upload_file', subpath=current_path) }}" class="btn btn-success">上传文件</a>
</div>

<table class="table table-hover">
  <thead>
    <tr><th>名称</th><th>类型</th><th>操作</th></tr>
  </thead>
  <tbody>
    {% if current_path %}
    <tr>
      <td><a href="{{ url_for('list_files', subpath=parent_path) }}">⬆️ 返回上一级</a></td><td>目录</td><td></td>
    </tr>
    {% endif %}
    {% for entry in entries %}
    <tr draggable="true"
        data-name="{{ entry.name }}"
        data-type="{{ 'dir' if entry.is_dir else 'file' }}"
        data-path="{{ (current_path + '/' if current_path else '') + entry.name|e }}"
        {% if entry.is_dir %}
          ondragover="dragOverHandler(event)"
          ondragleave="dragLeaveHandler(event)"
          ondrop="dropHandler(event)"
        {% endif %}
        oncontextmenu="showContextMenu(event)">
      <td>
        {% if entry.is_dir %}
          <a href="{{ url_for('list_files', subpath=(current_path + '/' if current_path else '') + entry.name) }}">
            📁 {{ entry.name }}
          </a>
        {% else %}
          {{ entry.name }}
        {% endif %}
      </td>
      <td>{{ "目录" if entry.is_dir else "文件" }}</td>
      <td>
        {% if not entry.is_dir %}
          <a href="{{ url_for('download_file', filepath=(current_path + '/' if current_path else '') + entry.name) }}" class="btn btn-primary btn-sm">下载</a>
          {% if entry.is_image %}
          <button class="btn btn-info btn-sm ms-1"
                  onclick="showPreview('image', '{{ url_for('download_file', filepath=(current_path + '/' if current_path else '') + entry.name) }}')">查看</button>
          {% elif entry.is_video %}
          <button class="btn btn-info btn-sm ms-1"
                  onclick="showPreview('video', '{{ url_for('download_file', filepath=(current_path + '/' if current_path else '') + entry.name) }}')">播放</button>
          {% endif %}
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<div id="contextMenuDropdown" class="dropdown-menu shadow"
     style="display:none; position:absolute; z-index:1050; min-width:140px;"
     aria-labelledby="dropdownMenuButton">
  <button class="dropdown-item" id="rename-action">重命名</button>
  <button class="dropdown-item text-danger" id="delete-action">删除</button>
</div>

<div class="modal fade" id="previewModal" tabindex="-1" aria-labelledby="previewModalLabel" aria-hidden="true">
  <div class="modal-dialog modal-xl modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="previewModalLabel">预览</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
      </div>
      <div class="modal-body text-center">
        <img id="previewImage" src="" alt="图片预览" class="img-fluid" style="max-height:70vh; display:none;" />
        <video id="previewVideo" controls style="max-width:100%; max-height:70vh; display:none;">
          <source src="" type="video/mp4" />
          您的浏览器不支持视频播放。
        </video>
      </div>
    </div>
  </div>
</div>

<script>
  let draggedPath = null;  // 当前拖拽文件路径
  let currentTarget = null;  // 当前右键操作对象
  const contextMenu = document.getElementById('contextMenuDropdown');  // 右键菜单DOM

  // 绑定所有可拖拽文件夹/文件的事件
  function bindRowEvents() {
    document.querySelectorAll('tr[draggable="true"]').forEach(row => {
      row.addEventListener('dragstart', event => {
        draggedPath = event.currentTarget.dataset.path; // 拖拽的路径
        event.dataTransfer.setData('text/plain', draggedPath);
        event.dataTransfer.effectAllowed = 'move';
      });
      row.addEventListener('dragend', event => {  // 拖拽结束，移除高亮
        draggedPath = null;
        document.querySelectorAll('tr.dragover').forEach(el => el.classList.remove('dragover'));
      });
      row.addEventListener('contextmenu', showContextMenu);  // 右键菜单打开
    });
  }
  bindRowEvents();

  function dragOverHandler(event) {
    event.preventDefault();
    event.currentTarget.classList.add('dragover');
    event.dataTransfer.dropEffect = 'move';
  }
  function dragLeaveHandler(event){
    event.currentTarget.classList.remove('dragover');
  }
  function dropHandler(event) {
    event.preventDefault();
    let target = event.currentTarget;
    target.classList.remove('dragover');
    let targetPath = target.dataset.path;
    if (!draggedPath || !targetPath) return;
    if (draggedPath === targetPath) {
      alert('不能移动到自身');
      return;
    }
    if (targetPath.startsWith(draggedPath + '/')) {
      alert('不能移动到自身子目录');
      return;
    }
    fetch('{{ url_for("api_move") }}', {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({src_path: draggedPath, dst_path: targetPath})
    }).then(res => res.json()).then(data => {
      if (data.success) location.reload();
      else alert("移动失败：" + data.message);
    }).catch(e => alert("请求异常：" + e));
  }
  document.querySelectorAll('tr[draggable="true"][data-type="dir"]').forEach(row => {
    row.addEventListener('dragover', dragOverHandler);
    row.addEventListener('dragleave', dragLeaveHandler);
    row.addEventListener('drop', dropHandler);
  });

  // 右键菜单显示，定位菜单位置并显示
  function showContextMenu(event){
    event.preventDefault();
    currentTarget = event.currentTarget;
    contextMenu.style.left = event.pageX + "px";
    contextMenu.style.top = event.pageY + "px";
    contextMenu.classList.add('show');
    contextMenu.style.display = 'block';
  }

  // 点击页面空白处关闭菜单
  document.addEventListener('click', () => {
    if (contextMenu.classList.contains('show')){
      contextMenu.classList.remove('show');
      setTimeout(() => contextMenu.style.display = 'none', 150);  // 等待动画结束隐藏
      currentTarget = null;
    }
  });

  // 删除事件，确认后调用API
  document.getElementById('delete-action').addEventListener('click', () => {
    if (!currentTarget) return;
    let path = currentTarget.dataset.path;
    if (!confirm(`确定删除："${path}"？文件夹将递归删除！`)) {
      contextMenu.classList.remove('show');
      contextMenu.style.display = 'none';
      return;
    }
    fetch('{{ url_for("api_delete") }}', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({target_path: path})
    }).then(res => res.json()).then(data => {
      if(data.success) location.reload();
      else alert('删除失败：'+data.message);
    }).catch(e => alert('请求异常：'+e));
    contextMenu.classList.remove('show');
    contextMenu.style.display = 'none';
  });

  // 重命名事件，弹窗输入新名称并调用API
  document.getElementById('rename-action').addEventListener('click', () => {
    if (!currentTarget) return;
    let oldPath = currentTarget.dataset.path;
    let oldName = currentTarget.dataset.name;
    let newName = prompt("输入新的名称", oldName);
    if (!newName || newName.trim() === "") {
      alert("名称不能为空");
      contextMenu.classList.remove('show');
      contextMenu.style.display = 'none';
      return;
    }
    fetch('{{ url_for("api_rename") }}', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({target_path: oldPath, new_name: newName})
    }).then(res => res.json()).then(data => {
      if(data.success) location.reload();
      else alert("重命名失败：" + data.message);
    }).catch(e => alert("请求异常：" + e));
    contextMenu.classList.remove('show');
    contextMenu.style.display = 'none';
  });

  // 预览相关——弹出模态框查看图片或播放视频
  const previewModal = new bootstrap.Modal(document.getElementById('previewModal'));
  const previewImage = document.getElementById('previewImage');
  const previewVideo = document.getElementById('previewVideo');

  function showPreview(type, url) {
    if (type === 'image'){
      previewImage.src = url;
      previewImage.style.display = 'block';
      previewVideo.style.display = 'none';
      previewVideo.pause();
      previewModal.show();
    } else if (type === 'video'){
      previewVideo.src = url;
      previewVideo.style.display = 'block';
      previewImage.style.display = 'none';
      previewModal.show();
      previewVideo.load();
      previewVideo.play();
    }
  }
  // 关闭模态窗口时停止视频播放和清空地址，释放资源
  document.getElementById('previewModal').addEventListener('hidden.bs.modal', () => {
    previewVideo.pause();
    previewVideo.src = '';
  });
</script>
{% endblock %}
''',
    'upload': '''
{% extends base %}
{% block content %}
<nav aria-label="breadcrumb">
  <ol class="breadcrumb">
    {% for name, link in breadcrumb %}
      <li class="breadcrumb-item {% if loop.last %}active{% endif %}" {% if loop.last %}aria-current="page"{% else %}>
        <a href="{{ link }}">{{ name }}</a>{% endif %}
      </li>
    {% endfor %}
  </ol>
</nav>

<h4>上传文件到：{{ '/' + current_path if current_path else '/' }}</h4>
<form method="post" enctype="multipart/form-data" class="mb-3">
  <div class="mb-3">
    <input type="file" class="form-control" name="file" required />
  </div>
  <button type="submit" class="btn btn-primary">上传</button>
  <a href="{{ url_for('list_files', subpath=current_path) }}" class="btn btn-secondary ms-2">返回</a>
</form>
{% endblock %}
''',
    'search_page': '''
{% extends base %}
{% block content %}
<div class="mx-auto" style="max-width: 600px;">
  <h3 class="mb-4">全目录搜索 - {{ username }}</h3>
  <form method="post" class="d-flex mb-3" novalidate>
    <input type="text" name="keyword" class="form-control me-2" placeholder="请输入搜索关键字" required autofocus />
    <button type="submit" class="btn btn-primary">搜索</button>
  </form>
  <a href="{{ url_for('list_files') }}">返回文件管理</a>
</div>
{% endblock %}
''',
    'search_results': '''
{% extends base %}
{% block content %}
<h3>搜索结果：关键词 "{{ keyword }}" (用户: {{ username }})</h3>
{% if results %}
  <ul class="list-group">
    {% for item in results %}
      <li class="list-group-item">
        {% if item.is_dir %}
          📁 <a href="{{ url_for('list_files', subpath=item.path) }}">{{ item.path }}</a>
        {% else %}
          📄 <a href="{{ url_for('download_file', filepath=item.path) }}">{{ item.path }}</a>
        {% endif %}
      </li>
    {% endfor %}
  </ul>
{% else %}
  <div class="alert alert-info">没有匹配结果</div>
{% endif %}
<br />
<a href="{{ url_for('search') }}" class="btn btn-secondary">新搜索</a>
<a href="{{ url_for('list_files') }}" class="btn btn-secondary ms-2">返回文件管理</a>
{% endblock %}
'''
}


if __name__ == '__main__':
    # Register the base template globally for Jinja2
    app.jinja_env.globals.update(base=TEMPLATES['base'])
    app.run(debug=True)  # Run the app in debug mode
