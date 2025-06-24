import os
import sqlite3
import shutil
from functools import wraps
from flask import (
    Flask, request, send_from_directory, abort, render_template,
    redirect, url_for, flash, jsonify, session
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from urllib.parse import unquote
from jinja2 import DictLoader

# 初始化 Flask 应用
app = Flask(__name__)
app.secret_key = 'change_this_to_a_random_secret_key'  # 生产环境中请更改为随机的密钥

# 设置数据库路径和用户文件根目录
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.db')  # SQLite 数据库路径
USER_FILES_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')  # 用户文件的根目录
os.makedirs(USER_FILES_ROOT, exist_ok=True)  # 确保目录存在

def get_db_connection():
    """
    获取一个数据库连接，行作为字典返回。
    """
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def initialize_database():
    """
    初始化数据库中的用户表。
    """
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

# 在应用启动时初始化数据库
initialize_database()

def login_required(function):
    """
    登录保护装饰器，未登录用户重定向到登录页面。
    """
    @wraps(function)
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.path))
        return function(*args, **kwargs)
    return wrapper

def safe_join(base_path, *paths):
    """
    安全地连接路径，防止路径遍历攻击。
    """
    final_path = os.path.abspath(os.path.join(base_path, *paths))
    if not final_path.startswith(base_path):
        raise ValueError("Attempted access outside of base directory")
    return final_path

def build_breadcrumb(sub_path):
    """
    构建导航面包屑列表。
    """
    crumbs = [("Root", url_for('list_files', subpath=''))]
    if not sub_path:
        return crumbs
    parts = sub_path.strip('/').split('/')
    accumulated_path = []
    for part in parts:
        accumulated_path.append(part)
        crumbs.append((part, url_for('list_files', subpath='/'.join(accumulated_path))))
    return crumbs

def is_image_file(filename):
    """
    根据文件扩展名判断是否为图片文件。
    """
    ext = filename.lower().rsplit('.', 1)[-1]
    return ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff']

def is_video_file(filename):
    """
    根据文件扩展名判断是否为视频文件。
    """
    ext = filename.lower().rsplit('.', 1)[-1]
    return ext in ['mp4', 'webm', 'ogg', 'mov', 'avi', 'flv', 'mkv']

def get_current_user_dir():
    """
    获取当前用户的文件目录，若不存在则创建。
    """
    current_username = session.get('username')
    if not current_username:
        abort(403)
    user_directory = os.path.join(USER_FILES_ROOT, current_username)
    os.makedirs(user_directory, exist_ok=True)
    return user_directory

# 模板字典
TEMPLATES = {
    # ...（保持原有的模板内容不变）
    # 模板内容太长，这里省略，完整代码在下方完整代码部分提供。
}

# 注册模板字典到 Flask 应用的 Jinja2 环境
app.jinja_loader = DictLoader(TEMPLATES)

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    用户注册路由。
    """
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password_confirm = request.form.get('password2', '')

        # 表单验证
        if not username or not password or not password_confirm:
            flash("请填写所有字段", "warning")
            return redirect(request.url)
        if password != password_confirm:
            flash("两次输入的密码不一致", "danger")
            return redirect(request.url)

        # 密码哈希并保存用户信息
        password_hash = generate_password_hash(password)
        connection = get_db_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
            connection.commit()
            flash("注册成功，请登录", "success")
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            # 用户名已存在
            flash("用户名已存在", "danger")
            return redirect(request.url)
        finally:
            connection.close()

    return render_template('register')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    用户登录路由。
    """
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
            flash("登录成功", "success")
            next_page = request.args.get('next')
            return redirect(next_page or url_for('list_files'))
        else:
            flash("用户名或密码错误", "danger")
            return redirect(request.url)

    return render_template('login')

@app.route('/logout')
def logout():
    """
    用户登出路由，清除会话并重定向到登录页面。
    """
    session.pop('username', None)
    flash("已退出登录", "info")
    return redirect(url_for('login'))

@app.route('/changepwd', methods=['GET', 'POST'])
@login_required
def change_password():
    """
    修改密码路由。
    """
    if request.method == 'POST':
        old_password = request.form.get('oldpassword', '')
        new_password = request.form.get('newpassword', '')
        new_password_confirm = request.form.get('newpassword2', '')

        # 表单验证
        if not old_password or not new_password or not new_password_confirm:
            flash("请填写所有字段", "warning")
            return redirect(request.url)
        if new_password != new_password_confirm:
            flash("两次输入的新密码不一致", "danger")
            return redirect(request.url)

        current_username = session['username']
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (current_username,))
        user = cursor.fetchone()
        if not user or not check_password_hash(user['password_hash'], old_password):
            flash("旧密码不正确", "danger")
            connection.close()
            return redirect(request.url)

        # 更新密码
        new_hash = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, current_username))
        connection.commit()
        connection.close()
        flash("密码修改成功，请重新登录", "success")
        return redirect(url_for('logout'))

    return render_template('changepwd')

@app.route('/files/', defaults={'subpath': ''})
@app.route('/files/<path:subpath>')
@login_required
def list_files(subpath):
    """
    列出用户目录下的所有文件和文件夹。
    """
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

    # 排序：目录在前，文件在后，按名称排序
    entries.sort(key=lambda entry: (not entry['is_dir'], entry['name'].lower()))

    parent_path = os.path.dirname(subpath) if subpath else None
    breadcrumb = build_breadcrumb(subpath)

    return render_template('list',
                           entries=entries,
                           current_path=subpath,
                           parent_path=parent_path,
                           breadcrumb=breadcrumb,
                           username=session.get('username'))

@app.route('/upload/', defaults={'subpath': ''}, methods=['GET', 'POST'])
@app.route('/upload/<path:subpath>', methods=['GET', 'POST'])
@login_required
def upload_file(subpath):
    """
    上传文件到指定目录。
    """
    subpath = unquote(subpath)
    user_dir = get_current_user_dir()
    try:
        upload_dir = safe_join(user_dir, subpath)
    except ValueError:
        abort(403)

    os.makedirs(upload_dir, exist_ok=True)

    if request.method == 'POST':
        if 'file' not in request.files:
            flash("请求中没有文件部分", "danger")
            return redirect(request.url)
        upload_file = request.files['file']
        if upload_file.filename == '':
            flash("未选择文件", "warning")
            return redirect(request.url)
        filename = secure_filename(upload_file.filename)
        save_path = os.path.join(upload_dir, filename)
        upload_file.save(save_path)
        flash(f"文件 '{filename}' 上传成功！", "success")
        return redirect(url_for('list_files', subpath=subpath))

    breadcrumb = build_breadcrumb(subpath)
    return render_template('upload',
                           current_path=subpath,
                           breadcrumb=breadcrumb,
                           username=session.get('username'))

@app.route('/download/<path:filepath>')
@login_required
def download_file(filepath):
    """
    提供文件下载。
    """
    filepath = unquote(filepath)
    user_dir = get_current_user_dir()
    try:
        abs_path = safe_join(user_dir, filepath)
    except ValueError:
        abort(403)

    if not os.path.isfile(abs_path):
        abort(404, description="File not found")
    directory = os.path.dirname(abs_path)
    filename = os.path.basename(abs_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/move', methods=['POST'])
@login_required
def api_move():
    """
    移动文件或目录的 API 接口。
    """
    request_data = request.json or {}
    source_path = request_data.get('src_path')
    destination_path = request_data.get('dst_path')
    if not source_path or not destination_path:
        return jsonify(success=False, message="缺少参数"), 400

    user_dir = get_current_user_dir()
    try:
        abs_source = safe_join(user_dir, source_path)
        abs_destination = safe_join(user_dir, destination_path)
    except ValueError:
        return jsonify(success=False, message="路径无效"), 403

    if not os.path.exists(abs_source):
        return jsonify(success=False, message="源文件/目录不存在"), 404
    if not os.path.isdir(abs_destination):
        return jsonify(success=False, message="目标必须是一个目录"), 400

    dest_final = os.path.join(abs_destination, os.path.basename(abs_source))
    if os.path.exists(dest_final):
        return jsonify(success=False, message="目标目录已存在同名文件/文件夹"), 409

    try:
        os.rename(abs_source, dest_final)
    except Exception as ex:
        return jsonify(success=False, message=f"移动失败：{ex}"), 500

    return jsonify(success=True)

@app.route('/api/delete', methods=['POST'])
@login_required
def api_delete():
    """
    删除文件或目录的 API 接口。
    """
    request_data = request.json or {}
    target_path = request_data.get('target_path')
    if not target_path:
        return jsonify(success=False, message="缺少参数"), 400

    user_dir = get_current_user_dir()
    try:
        abs_target = safe_join(user_dir, target_path)
    except ValueError:
        return jsonify(success=False, message="路径无效"), 403

    if not os.path.exists(abs_target):
        return jsonify(success=False, message="文件或文件夹不存在"), 404

    try:
        if os.path.isfile(abs_target):
            os.remove(abs_target)
        else:
            shutil.rmtree(abs_target)
    except Exception as ex:
        return jsonify(success=False, message=f"删除失败：{ex}"), 500

    return jsonify(success=True)

@app.route('/api/rename', methods=['POST'])
@login_required
def api_rename():
    """
    重命名文件或目录的 API 接口。
    """
    request_data = request.json or {}
    target_path = request_data.get('target_path')
    new_name = request_data.get('new_name')
    if not target_path or not new_name:
        return jsonify(success=False, message="缺少参数"), 400

    user_dir = get_current_user_dir()
    try:
        abs_target = safe_join(user_dir, target_path)
    except ValueError:
        return jsonify(success=False, message="路径无效"), 403

    if not os.path.exists(abs_target):
        return jsonify(success=False, message="文件或文件夹不存在"), 404

    parent_directory = os.path.dirname(abs_target)
    new_name_safe = secure_filename(new_name)
    new_abs_path = os.path.join(parent_directory, new_name_safe)

    if os.path.exists(new_abs_path):
        return jsonify(success=False, message="同目录下已存在同名文件或文件夹"), 409

    try:
        os.rename(abs_target, new_abs_path)
    except Exception as ex:
        return jsonify(success=False, message=f"重命名失败：{ex}"), 500

    return jsonify(success=True)

def lcs_length(string1, string2):
    """
    计算两个字符串的最长公共子序列长度。
    """
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

def walk_user_files(root_directory):
    """
    递归遍历 root_directory 下的所有文件和目录。
    """
    results = []
    to_process_paths = ['']  # 空字符串表示根目录的相对路径
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
    """
    全局搜索功能，使用最长公共子序列算法进行模糊匹配。
    """
    if request.method == 'POST':
        keyword = request.form.get('keyword', '').strip()
        if not keyword:
            flash("请输入搜索关键字", "warning")
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
        # 按 LCS 降序排序，其次按文件名升序排序
        matches.sort(key=lambda match_tuple: (-match_tuple[0], match_tuple[1]))

        search_results = []
        for lcs_score, base_lower, file_entry in matches:
            search_results.append(file_entry)
        current_user = session['username']

        return render_template('search_results',
                               keyword=keyword,
                               results=search_results,
                               username=current_user)
    else:
        current_user = session['username']
        return render_template('search_page', username=current_user)

if __name__ == '__main__':
    app.run(debug=True)  # 在调试模式下运行应用



1. 基础模板 `base.html

<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>用户文件管理系统</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <!-- 引入 Bootstrap 5 样式 -->
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
    /* 拖拽时高亮显示行 */
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
<!-- 导航栏 -->
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
  
  <!-- 子模板内容将插入到这里 -->
  {% block content %}{% endblock %}
</div>

<!-- 引入 Bootstrap 5 JS -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

<!-- 如果有需要，子模板可以在这里插入额外的 JavaScript -->
{% block extra_scripts %}{% endblock %}

</body>
</html>


---

2. 注册页面模板 `register.html
{% extends 'base.html' %}

{% block content %}
<div class="mx-auto" style="max-width: 400px;">
  <h3 class="mb-4">注册</h3>
  <form method="post" novalidate>
    <!-- 用户名输入框 -->
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <!-- 用户名要求3-20个字符，只能包含字母、数字、下划线 -->
      <input type="text" class="form-control" id="username" name="username" required minlength="3" maxlength="20"
             pattern="^[a-zA-Z0-9_]+$" autofocus />
      <small class="form-text text-muted">只能包含字母、数字、下划线，长度3-20</small>
    </div>
    <!-- 密码输入框 -->
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input type="password" class="form-control" id="password" name="password" required minlength="6" maxlength="64" />
    </div>
    <!-- 确认密码输入框 -->
    <div class="mb-3">
      <label for="password2" class="form-label">确认密码</label>
      <input type="password" class="form-control" id="password2" name="password2" required minlength="6" maxlength="64" />
    </div>
    <!-- 提交按钮 -->
    <button type="submit" class="btn btn-primary w-100">注册</button>
    <!-- 已有账号链接 -->
    <div class="mt-3 text-center">
      <a href="{{ url_for('login') }}">已有账号？去登录</a>
    </div>
  </form>
</div>
{% endblock %}
---
3. 登录页面模板 `login.html
{% extends 'base.html' %}

{% block content %}
<div class="mx-auto" style="max-width: 400px;">
  <h3 class="mb-4">登录</h3>
  <form method="post" novalidate>
    <!-- 用户名输入框 -->
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input type="text" class="form-control" id="username" name="username" required autofocus />
    </div>
    <!-- 密码输入框 -->
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input type="password" class="form-control" id="password" name="password" required />
    </div>
    <!-- 提交按钮 -->
    <button type="submit" class="btn btn-primary w-100">登录</button>
    <!-- 没有账号链接 -->
    <div class="mt-3 text-center">
      <a href="{{ url_for('register') }}">没有账号？去注册</a>
    </div>
  </form>
</div>
{% endblock %}

---

4. 修改密码页面模板 `changepwd.html`
{% extends 'base.html' %}

{% block content %}
<div class="mx-auto" style="max-width: 400px;">
  <h3 class="mb-4">修改密码</h3>
  <form method="post" novalidate>
    <!-- 旧密码输入框 -->
    <div class="mb-3">
      <label for="oldpassword" class="form-label">旧密码</label>
      <input type="password" class="form-control" id="oldpassword" name="oldpassword" required autofocus />
    </div>
    <!-- 新密码输入框 -->
    <div class="mb-3">
      <label for="newpassword" class="form-label">新密码</label>
      <input type="password" class="form-control" id="newpassword" name="newpassword" required minlength="6" maxlength="64" />
    </div>
    <!-- 确认新密码输入框 -->
    <div class="mb-3">
      <label for="newpassword2" class="form-label">确认新密码</label>
      <input type="password" class="form-control" id="newpassword2" name="newpassword2" required minlength="6" maxlength="64" />
    </div>
    <!-- 提交按钮 -->
    <button type="submit" class="btn btn-primary w-100">修改密码</button>
    <!-- 返回文件管理链接 -->
    <div class="mt-3 text-center">
      <a href="{{ url_for('list_files') }}">返回文件管理</a>
    </div>
  </form>
</div>
{% endblock %}
---
5. 文件列表页面模板 `list.html`
{% extends 'base.html' %}

{% block content %}
<!-- 面包屑导航 -->
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

<!-- 目录标题和上传按钮 -->
<div class="d-flex justify-content-between align-items-center mb-3">
  <h4>欢迎，{{ username }}，当前目录：{{ '/' + current_path if current_path else '/' }}</h4>
  <a href="{{ url_for('upload_file', subpath=current_path) }}" class="btn btn-success">上传文件</a>
</div>

<!-- 文件列表表格 -->
<table class="table table-hover">
  <thead>
    <tr><th>名称</th><th>类型</th><th>操作</th></tr>
  </thead>
  <tbody>
    <!-- 如果不是根目录，显示返回上一级链接 -->
    {% if current_path %}
    <tr>
      <td><a href="{{ url_for('list_files', subpath=parent_path) }}">⬆️ 返回上一级</a></td><td>目录</td><td></td>
    </tr>
    {% endif %}
    <!-- 列出文件和目录 -->
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
          <!-- 目录链接 -->
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
          <!-- 下载按钮 -->
          <a href="{{ url_for('download_file', filepath=(current_path + '/' if current_path else '') + entry.name) }}" class="btn btn-primary btn-sm">下载</a>
          {% if entry.is_image %}
          <!-- 查看图片按钮 -->
          <button class="btn btn-info btn-sm ms-1"
                  onclick="showPreview('image', '{{ url_for('download_file', filepath=(current_path + '/' if current_path else '') + entry.name) }}')">查看</button>
          {% elif entry.is_video %}
          <!-- 播放视频按钮 -->
          <button class="btn btn-info btn-sm ms-1"
                  onclick="showPreview('video', '{{ url_for('download_file', filepath=(current_path + '/' if current_path else '') + entry.name) }}')">播放</button>
          {% endif %}
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<!-- 右键菜单 -->
<div id="contextMenuDropdown" class="dropdown-menu shadow"
     style="display:none; position:absolute; z-index:1050; min-width:140px;">
  <button class="dropdown-item" id="rename-action">重命名</button>
  <button class="dropdown-item text-danger" id="delete-action">删除</button>
</div>

<!-- 预览模态框 -->
<div class="modal fade" id="previewModal" tabindex="-1" aria-labelledby="previewModalLabel" aria-hidden="true">
  <div class="modal-dialog modal-xl modal-dialog-centered">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="previewModalLabel">预览</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
      </div>
      <div class="modal-body text-center">
        <!-- 图片预览 -->
        <img id="previewImage" src="" alt="图片预览" class="img-fluid" style="max-height:70vh; display:none;" />
        <!-- 视频预览 -->
        <video id="previewVideo" controls style="max-width:100%; max-height:70vh; display:none;">
          <source src="" type="video/mp4" />
          您的浏览器不支持视频播放。
        </video>
      </div>
    </div>
  </div>
</div>

{% endblock %}

{% block extra_scripts %}
<!-- 额外的 JavaScript 脚本 -->
<script>
  // 当前拖拽的文件路径
  let draggedPath = null;
  // 当前右键点击的行
  let currentTarget = null;
  // 获取右键菜单 DOM 元素
  const contextMenu = document.getElementById('contextMenuDropdown');
  // 获取 API 接口的 URL
  const apiMoveUrl = "{{ url_for('api_move') }}";
  const apiDeleteUrl = "{{ url_for('api_delete') }}";
  const apiRenameUrl = "{{ url_for('api_rename') }}";

  // 绑定行的事件处理
  function bindRowEvents() {
    document.querySelectorAll('tr[draggable="true"]').forEach(row => {
      // 拖拽开始事件
      row.addEventListener('dragstart', event => {
        draggedPath = event.currentTarget.dataset.path; // 记录拖拽的路径
        event.dataTransfer.setData('text/plain', draggedPath);
        event.dataTransfer.effectAllowed = 'move';
      });
      // 拖拽结束事件
      row.addEventListener('dragend', event => {
        draggedPath = null;
        document.querySelectorAll('tr.dragover').forEach(el => el.classList.remove('dragover'));
      });
      // 右键菜单事件
      row.addEventListener('contextmenu', showContextMenu);
    });
  }
  bindRowEvents();

  // 拖拽经过目标元素时的处理
  function dragOverHandler(event) {
    event.preventDefault();
    event.currentTarget.classList.add('dragover');
    event.dataTransfer.dropEffect = 'move';
  }

  // 拖拽离开目标元素时的处理
  function dragLeaveHandler(event){
    event.currentTarget.classList.remove('dragover');
  }

  // 拖拽放下（释放鼠标）时的处理
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
    // 调用移动 API
    fetch(apiMoveUrl, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({src_path: draggedPath, dst_path: targetPath})
    }).then(res => res.json()).then(data => {
      if (data.success) location.reload();
      else alert("移动失败：" + data.message);
    }).catch(e => alert("请求异常：" + e));
  }

  // 显示右键菜单
  function showContextMenu(event){
    event.preventDefault();
    currentTarget = event.currentTarget;
    contextMenu.style.left = event.pageX + "px";
    contextMenu.style.top = event.pageY + "px";
    contextMenu.classList.add('show');
    contextMenu.style.display = 'block';
  }

  // 点击页面其他位置关闭右键菜单
  document.addEventListener('click', () => {
    if (contextMenu.classList.contains('show')){
      contextMenu.classList.remove('show');
      setTimeout(() => contextMenu.style.display = 'none', 150);  // 动画结束后隐藏
      currentTarget = null;
    }
  });

  // 删除操作
  document.getElementById('delete-action').addEventListener('click', () => {
    if (!currentTarget) return;
    let path = currentTarget.dataset.path;
    if (!confirm(`确定删除："${path}"？文件夹将递归删除！`)) {
      contextMenu.classList.remove('show');
      contextMenu.style.display = 'none';
      return;
    }
    // 调用删除 API
    fetch(apiDeleteUrl, {
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

  // 重命名操作
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
    // 调用重命名 API
    fetch(apiRenameUrl, {
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

  // 预览相关
  const previewModal = new bootstrap.Modal(document.getElementById('previewModal'));
  const previewImage = document.getElementById('previewImage');
  const previewVideo = document.getElementById('previewVideo');

  // 显示预览
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

  // 关闭预览模态框时，停止视频播放并清空地址
  document.getElementById('previewModal').addEventListener('hidden.bs.modal', () => {
    previewVideo.pause();
    previewVideo.src = '';
  });
</script>
{% endblock %}
---
6. 上传文件页面模板 `upload.html`
{% extends 'base.html' %}

{% block content %}
<!-- 面包屑导航 -->
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

<!-- 上传文件表单 -->
<h4>上传文件到：{{ '/' + current_path if current_path else '/' }}</h4>
<form method="post" enctype="multipart/form-data" class="mb-3">
  <div class="mb-3">
    <input type="file" class="form-control" name="file" required />
  </div>
  <button type="submit" class="btn btn-primary">上传</button>
  <a href="{{ url_for('list_files', subpath=current_path) }}" class="btn btn-secondary ms-2">返回</a>
</form>
{% endblock %}
```

---

**7. 搜索页面模板 `search_page.html`**

```html
{% extends 'base.html' %}

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
---
8. 搜索结果页面模板 `search_results.html`
{% extends 'base.html' %}

{% block content %}
<h3>搜索结果：关键词 "{{ keyword }}" (用户: {{ username }})</h3>
{% if results %}
  <!-- 搜索结果列表 -->
  <ul class="list-group">
    {% for item in results %}
      <li class="list-group-item">
        {% if item.is_dir %}
          <!-- 目录链接 -->
          📁 <a href="{{ url_for('list_files', subpath=item.path) }}">{{ item.path }}</a>
        {% else %}
          <!-- 文件链接 -->
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
