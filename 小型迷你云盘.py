import os
import sqlite3
from flask import (
    Flask, g, session, redirect, url_for, render_template_string,
    request, abort, jsonify, send_from_directory
)
from functools import wraps

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

FILE_ROOT = os.path.abspath('files')
os.makedirs(FILE_ROOT, exist_ok=True)

DATABASE = 'users.db'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    db.commit()

init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def safe_join(root, *paths):
    final_path = os.path.abspath(os.path.join(root, *paths))
    if not final_path.startswith(root):
        abort(403)
    return final_path

@app.template_filter('basename')
def basename_filter(path):
    return os.path.basename(path)

def is_media_file(path):
    ext = os.path.splitext(path)[1].lower()
    return ext in {'.mp4', '.webm', '.ogg', '.mp3', '.wav', '.m4a'}

@app.route('/', defaults={'req_path': ''})
@app.route('/<path:req_path>')
@login_required
def index(req_path):
    safe_path = safe_join(FILE_ROOT, req_path)
    if not os.path.isdir(safe_path):
        abort(404)
    dirs = []
    files = []
    for entry in sorted(os.listdir(safe_path), key=lambda x: x.lower()):
        full_path = os.path.join(safe_path, entry)
        rel_path = os.path.join(req_path, entry) if req_path else entry
        if os.path.isdir(full_path):
            dirs.append(rel_path)
        else:
            files.append(rel_path)
    parent_path = os.path.dirname(req_path) if req_path else None
    return render_template_string(INDEX_HTML, path=req_path, dirs=dirs, files=files,
                                  parent_path=parent_path, is_media=is_media_file)

@app.route('/upload/<path:upload_path>', methods=['POST'])
@login_required
def upload_file(upload_path):
    safe_path = safe_join(FILE_ROOT, upload_path)
    if not os.path.isdir(safe_path):
        abort(404)
    if 'file' not in request.files:
        return '无上传文件', 400
    file = request.files['file']
    if file.filename == '':
        return '未选择文件', 400
    filename = os.path.basename(file.filename)
    save_path = os.path.join(safe_path, filename)
    try:
        file.save(save_path)
    except OSError as e:
        return f'保存文件失败: {e}', 500
    return redirect(url_for('index', req_path=upload_path))

@app.route('/download/<path:download_path>')
@login_required
def download_file(download_path):
    safe_path = safe_join(FILE_ROOT, download_path)
    if not os.path.isfile(safe_path):
        abort(404)
    directory = os.path.dirname(safe_path)
    filename = os.path.basename(safe_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/delete', methods=['POST'])
@login_required
def delete():
    data = request.json
    if not data or 'path' not in data:
        return jsonify(success=False, error='参数缺失'), 400
    rel_path = data['path']
    abs_path = safe_join(FILE_ROOT, rel_path)
    if not os.path.exists(abs_path):
        return jsonify(success=False, error='文件或目录不存在'), 404
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        elif os.path.isdir(abs_path):
            import shutil
            shutil.rmtree(abs_path)
        else:
            return jsonify(success=False, error='未知文件类型'), 400
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True)

@app.route('/rename', methods=['POST'])
@login_required
def rename():
    data = request.json
    if not data or 'old_path' not in data or 'new_name' not in data:
        return jsonify(success=False, error='参数缺失'), 400
    old_rel = data['old_path']
    new_name = data['new_name'].strip()
    if '/' in new_name or '\\' in new_name or new_name == '':
        return jsonify(success=False, error='新名称不合法'), 400
    abs_old = safe_join(FILE_ROOT, old_rel)
    abs_new = safe_join(os.path.dirname(abs_old), new_name)
    if not os.path.exists(abs_old):
        return jsonify(success=False, error='原文件或目录不存在'), 404
    if os.path.exists(abs_new):
        return jsonify(success=False, error='目标名称已存在'), 400
    try:
        os.rename(abs_old, abs_new)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True)

@app.route('/mkdir', methods=['POST'])
@login_required
def mkdir():
    data = request.json
    if not data or 'parent_path' not in data or 'folder_name' not in data:
        return jsonify(success=False, error='参数缺失'), 400
    parent_rel = data['parent_path']
    folder_name = data['folder_name'].strip()
    if '/' in folder_name or '\\' in folder_name or folder_name == '':
        return jsonify(success=False, error='文件夹名称不合法'), 400
    abs_parent = safe_join(FILE_ROOT, parent_rel)
    if not os.path.isdir(abs_parent):
        return jsonify(success=False, error='父目录不存在'), 404
    abs_newfolder = os.path.join(abs_parent, folder_name)
    if os.path.exists(abs_newfolder):
        return jsonify(success=False, error='文件夹已存在'), 400
    try:
        os.mkdir(abs_newfolder)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True)

@app.route('/move', methods=['POST'])
@login_required
def move():  # 支持拖拽移动文件夹和文件
    data = request.json
    if not data or 'src_path' not in data or 'dst_path' not in data:
        return jsonify(success=False, error='参数缺失'), 400
    src_rel = data['src_path']
    dst_rel = data['dst_path']
    abs_src = safe_join(FILE_ROOT, src_rel)
    abs_dst_dir = safe_join(FILE_ROOT, dst_rel)
    if not os.path.exists(abs_src):
        return jsonify(success=False, error='源文件或目录不存在'), 404
    if not os.path.isdir(abs_dst_dir):
        return jsonify(success=False, error='目标目录不存在'), 404

    # 防止将父目录移动到子目录，造成死循环
    normalized_src_rel = os.path.normpath(src_rel)
    normalized_dst_rel = os.path.normpath(dst_rel)
    if normalized_dst_rel.startswith(normalized_src_rel + os.sep) or normalized_dst_rel == normalized_src_rel:
        return jsonify(success=False, error='无法移动到自身或子目录'), 400

    name = os.path.basename(abs_src)
    abs_dst = os.path.join(abs_dst_dir, name)
    if os.path.exists(abs_dst):
        return jsonify(success=False, error='目标位置已有同名文件或目录'), 400
    try:
        os.rename(abs_src, abs_dst)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    return jsonify(success=True)

@app.route('/play/<path:media_path>')
@login_required
def play_file(media_path):
    safe_path = safe_join(FILE_ROOT, media_path)
    if not os.path.isfile(safe_path):
        abort(404)
    if not is_media_file(media_path):
        return '不支持此格式在线播放', 400
    filename = os.path.basename(media_path)
    return render_template_string(PLAYER_HTML, file_url=url_for('download_file', download_path=media_path), filename=filename)

@app.route('/login', methods=['GET','POST'])
def login():
    error = ''
    if request.method == 'POST':
        name = request.form.get('username')
        pwd = request.form.get('password')
        if not name or not pwd:
            error = '请输入用户名和密码'
        else:
            db = get_db()
            user = db.execute('SELECT * FROM user WHERE username=? AND password=?', (name, pwd)).fetchone()
            if user:
                session.clear()
                session['user_id'] = user['id']
                return redirect(url_for('index'))
            else:
                error = '用户名或密码错误'
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/register', methods=['GET','POST'])
def register():
    error = ''
    if request.method == 'POST':
        name = request.form.get('username')
        pwd = request.form.get('password')
        if not name or not pwd:
            error = '请输入用户名和密码'
        else:
            try:
                db = get_db()
                db.execute('INSERT INTO user (username, password) VALUES (?, ?)', (name, pwd))
                db.commit()
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                error = '用户名已存在'
    return render_template_string(REGISTER_HTML, error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


LOGIN_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>登录</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex justify-content-center align-items-center" style="height:100vh;">
<div class="card shadow-sm p-4" style="min-width:320px; max-width: 400px; width:100%;">
  <h3 class="mb-3 text-center">登录</h3>
  {% if error %}
  <div class="alert alert-danger small mb-3">{{ error }}</div>
  {% endif %}
  <form method="post" novalidate>
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input type="text" class="form-control" id="username" name="username" required autofocus>
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input type="password" class="form-control" id="password" name="password" required>
    </div>
    <button class="btn btn-primary w-100" type="submit">登录</button>
  </form>
  <hr>
  <p class="text-center small mb-0">没有账号？ <a href="{{ url_for('register') }}">注册</a></p>
</div>
</body>
</html>
'''

REGISTER_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>注册</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="bg-light d-flex justify-content-center align-items-center" style="height:100vh;">
<div class="card shadow-sm p-4" style="min-width:320px; max-width: 400px; width:100%;">
  <h3 class="mb-3 text-center">注册</h3>
  {% if error %}
  <div class="alert alert-danger small mb-3">{{ error }}</div>
  {% endif %}
  <form method="post" novalidate>
    <div class="mb-3">
      <label for="username" class="form-label">用户名</label>
      <input type="text" class="form-control" id="username" name="username" required autofocus>
    </div>
    <div class="mb-3">
      <label for="password" class="form-label">密码</label>
      <input type="password" class="form-control" id="password" name="password" required>
    </div>
    <button class="btn btn-primary w-100" type="submit">注册</button>
  </form>
  <hr>
  <p class="text-center small mb-0">已有账号？ <a href="{{ url_for('login') }}">登录</a></p>
</div>
</body>
</html>
'''

INDEX_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <title>文件管理 - {{ path or "/" }}</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- Bootstrap 5 CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { font-family: Arial, sans-serif; background-color: #f8f9fa; min-height: 100vh; }
    #filelist li { cursor: grab; }
    #filelist li.dragging { opacity: 0.5; }
    .file-name { user-select: none; }
    a, button { user-select: none; }
  </style>
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-primary">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">文件管理</a>
    <div>
      <span class="text-light me-3">目录： /{{ path or "" }}</span>
      <a href="{{ url_for('logout') }}" class="btn btn-outline-light btn-sm">登出</a>
    </div>
  </div>
</nav>

<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
    <button class="btn btn-success" onclick="createFolder()">
      <i class="bi bi-folder-plus"></i> 新建文件夹
    </button>
    <form id="upload-form" action="{{ url_for('upload_file', upload_path=path) }}" method="post" enctype="multipart/form-data" class="d-flex gap-2 align-items-center flex-wrap">
      <input type="file" name="file" required class="form-control form-control-sm" style="max-width:300px;">
      <button type="submit" class="btn btn-primary btn-sm">上传文件</button>
    </form>
  </div>

  <ul id="filelist" class="list-group" ondragover="dragOver(event)" ondrop="drop(event, '{{ path }}')" >
    {% if parent_path is not none %}
      <li class="list-group-item d-flex justify-content-between align-items-center" draggable="false">
        <a href="{{ url_for('index', req_path=parent_path) }}" class="text-decoration-none">&larr; .. (返回上层)</a>
      </li>
    {% endif %}
    {% for d in dirs %}
    <li class="list-group-item d-flex justify-content-between align-items-center" draggable="true" ondragstart="dragStart(event)" data-path="{{ d }}">
      <div class="file-name">
        📁 
        <a href="{{ url_for('index', req_path=d) }}" class="link-primary text-decoration-none fw-semibold">{{ d|basename }}/</a>
      </div>
      <div class="btn-group btn-group-sm" role="group" aria-label="文件夹操作">
        <button class="btn btn-warning" onclick="renameItem('{{ d }}')" title="重命名">
          <i class="bi bi-pencil-square"></i>
        </button>
        <button class="btn btn-danger" onclick="deleteItem('{{ d }}')" title="删除">
          <i class="bi bi-trash"></i>
        </button>
      </div>
    </li>
    {% endfor %}
    {% for f in files %}
    <li class="list-group-item d-flex justify-content-between align-items-center" draggable="true" ondragstart="dragStart(event)" data-path="{{ f }}">
      <div class="file-name">
        📄 {{ f|basename }}
        [<a href="{{ url_for('download_file', download_path=f) }}" class="link-secondary" title="下载"><i class="bi bi-download"></i></a>]
        {% if is_media(f) %}
          [<a href="{{ url_for('play_file', media_path=f) }}" target="_blank" class="link-success" title="在线播放"><i class="bi bi-play-circle"></i></a>]
        {% endif %}
      </div>
      <div class="btn-group btn-group-sm" role="group" aria-label="文件操作">
        <button class="btn btn-warning" onclick="renameItem('{{ f }}')" title="重命名">
          <i class="bi bi-pencil-square"></i>
        </button>
        <button class="btn btn-danger" onclick="deleteItem('{{ f }}')" title="删除">
          <i class="bi bi-trash"></i>
        </button>
      </div>
    </li>
    {% endfor %}
  </ul>
</div>

<!-- Bootstrap Icons CDN -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.5/font/bootstrap-icons.css">

<!-- Bootstrap 5 JS Bundle (popper + bootstrap) -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

<script>
let draggedPath = null;

function dragStart(ev) {
  draggedPath = ev.target.getAttribute('data-path');
  ev.dataTransfer.effectAllowed = 'move';
  ev.target.classList.add('dragging');
}

function dragOver(ev) {
  ev.preventDefault();
}

function drop(ev, currentFolder) {
  ev.preventDefault();
  const li = document.querySelector('.dragging');
  if(li) li.classList.remove('dragging');
  if (!draggedPath) return;

  // 防止将自身或子目录移动到当前目录
  if (draggedPath === currentFolder || currentFolder.startsWith(draggedPath + '/')) {
    alert('无法移动到自身或子目录');
    draggedPath = null;
    return;
  }

  fetch('{{ url_for("move") }}', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ src_path: draggedPath, dst_path: currentFolder })
  }).then(r => r.json())
    .then(data => {
      if (data.success) {
        alert('移动成功');
        location.reload();
      } else {
        alert('错误: ' + data.error);
      }
    })
    .catch(() => alert('网络出错'));
  draggedPath = null;
}

function renameItem(oldPath) {
  let currentName = oldPath.split('/').pop();
  let newName = prompt("输入新名称", currentName);
  if (!newName) return;
  newName = newName.trim();
  if (newName.length === 0 || newName.includes('/') || newName.includes('\\')) {
    alert('名称不合法');
    return;
  }
  fetch('{{ url_for("rename") }}', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ old_path: oldPath, new_name: newName })
  }).then(r => r.json())
    .then(data => {
      if (data.success) {
        alert('重命名成功');
        location.reload();
      } else {
        alert('错误: ' + data.error);
      }
    })
    .catch(() => alert('网络出错'));
}

function deleteItem(path) {
  if (!confirm('确定删除？该操作不可恢复')) return;
  fetch('{{ url_for("delete") }}', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ path: path })
  }).then(r => r.json())
    .then(data => {
      if (data.success) {
        alert('删除成功');
        location.reload();
      } else {
        alert('错误: ' + data.error);
      }
    })
    .catch(() => alert('网络出错'));
}

function createFolder() {
  let folderName = prompt("新建文件夹名称");
  if (!folderName) return;
  folderName = folderName.trim();
  if (folderName.length === 0 || folderName.includes('/') || folderName.includes('\\')) {
    alert('文件夹名称不合法');
    return;
  }
  fetch('{{ url_for("mkdir") }}', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ parent_path: '{{ path }}', folder_name: folderName })
  }).then(r => r.json())
    .then(data => {
      if(data.success){
        alert('创建成功');
        location.reload();
      } else {
        alert('错误: '+data.error);
      }
    })
    .catch(() => alert('网络出错'));
}
</script>
</body>
</html>
'''

PLAYER_HTML = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <title>在线播放 - {{ filename }}</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <!-- Bootstrap 5 CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background-color: #f8f9fa; padding: 2rem; text-align: center; }
    video, audio { max-width: 100%; border-radius: 0.3rem; outline: none; }
  </style>
</head>
<body>
  <div class="container">
    <h2 class="mb-4">在线播放：{{ filename }}</h2>
    {% if file_url.endswith(('.mp4', '.webm', '.ogg')) %}
    <video controls autoplay muted playsinline>
      <source src="{{ file_url }}">
      浏览器不支持视频播放。
    </video>
    {% elif file_url.endswith(('.mp3', '.wav', '.m4a')) %}
    <audio controls autoplay>
      <source src="{{ file_url }}">
      浏览器不支持音频播放。
    </audio>
    {% else %}
    <p class="text-danger fw-semibold">不支持的媒体格式。</p>
    {% endif %}
    <div class="mt-4">
      <a href="{{ url_for('index') }}" class="btn btn-secondary">返回文件管理</a>
    </div>
  </div>
  <!-- Bootstrap JS Bundle -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
