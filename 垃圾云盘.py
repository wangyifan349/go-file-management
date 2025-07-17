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
    for entry in os.listdir(safe_path):
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
    file.save(save_path)
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
            # 删除时递归删除目录内所有内容
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
<title>登录</title>
<h2>登录</h2>
<form method="post">
  用户名：<input name="username" required><br>
  密码：<input name="password" type="password" required><br>
  <button type="submit">登录</button>
</form>
<p style="color:red;">{{ error }}</p>
<p><a href="{{ url_for("register") }}">注册新账号</a></p>
'''

REGISTER_HTML = '''
<!doctype html>
<title>注册</title>
<h2>注册</h2>
<form method="post">
  用户名：<input name="username" required><br>
  密码：<input name="password" type="password" required><br>
  <button type="submit">注册</button>
</form>
<p style="color:red;">{{ error }}</p>
<p><a href="{{ url_for("login") }}">已有账号，登录</a></p>
'''

INDEX_HTML = '''
<!doctype html>
<html>
<head>
  <title>文件管理 - {{ path or "/" }}</title>
  <meta charset="utf-8">
  <style>
    body { font-family: Arial, sans-serif; }
    ul { list-style-type:none; padding-left:0; }
    li { margin: 5px 0; cursor: grab; }
    button { margin-left: 5px; }
    #drop-area { border: 2px dashed #ccc; padding: 20px; margin-top: 15px; }
  </style>
</head>
<body>
<h2>目录： /{{ path }}</h2>
<p><a href="{{ url_for('logout') }}">登出</a></p>

<button onclick="createFolder()">创建新文件夹</button>

<ul id="filelist" ondragover="dragOver(event)" ondrop="drop(event, '{{ path }}')" >
  {% if parent_path is not none %}
    <li draggable="false"><a href="{{ url_for('index', req_path=parent_path) }}">.. (返回上层)</a></li>
  {% endif %}
  {% for d in dirs %}
    <li draggable="true"
        ondragstart="dragStart(event)"
        data-path="{{ d }}">
      📁 <a href="{{ url_for('index', req_path=d) }}">{{ d|basename }}/</a>
      <button onclick="renameItem('{{ d }}')">重命名</button>
      <button onclick="deleteItem('{{ d }}')">删除</button>
    </li>
  {% endfor %}
  {% for f in files %}
    <li draggable="true"
        ondragstart="dragStart(event)"
        data-path="{{ f }}">
      📄 {{ f|basename }}
      [<a href="{{ url_for('download_file', download_path=f) }}">下载</a>]
      <button onclick="renameItem('{{ f }}')">重命名</button>
      <button onclick="deleteItem('{{ f }}')">删除</button>
      {% if is_media(f) %}
        [<a href="{{ url_for('play_file', media_path=f) }}" target="_blank">在线播放</a>]
      {% endif %}
    </li>
  {% endfor %}
</ul>

<h3>上传文件</h3>
<form id="upload-form" action="{{ url_for('upload_file', upload_path=path) }}" method="post" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <button type="submit">上传</button>
</form>

<script>

let draggedPath = null;

function dragStart(ev) {
  draggedPath = ev.target.getAttribute('data-path');
  ev.dataTransfer.effectAllowed = 'move';
}

function dragOver(ev) {
  ev.preventDefault();
}

function drop(ev, currentFolder) {
  ev.preventDefault();
  if (!draggedPath) return;
  // 拖拽目标是当前folder子目录，避免循环嵌套
  if (draggedPath === currentFolder || currentFolder.startsWith(draggedPath + '/')) {
    alert('无法移动到自身或子目录');
    draggedPath = null;
    return;
  }
  // 调用move接口，把draggedPath移动到currentFolder
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
        alert('错误:' + data.error);
      }
    })
    .catch(() => alert('网络出错'));
  draggedPath = null;
}

function renameItem(oldPath) {
  let newName = prompt("输入新名称", oldPath.split('/').pop());
  if (!newName) return;
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
        alert('错误:' + data.error);
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
        alert('错误:' + data.error);
      }
    })
    .catch(() => alert('网络出错'));
}

function createFolder() {
  let folderName = prompt("新建文件夹名称");
  if (!folderName) return;
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
        alert('错误:'+data.error);
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
<title>在线播放 - {{ filename }}</title>
<h2>在线播放：{{ filename }}</h2>
{% if file_url.endswith(('.mp4', '.webm', '.ogg')) %}
  <video width="640" height="360" controls autoplay>
    <source src="{{ file_url }}">
    浏览器不支持视频播放。
  </video>
{% elif file_url.endswith(('.mp3', '.wav', '.m4a')) %}
  <audio controls autoplay>
    <source src="{{ file_url }}">
    浏览器不支持音频播放。
  </audio>
{% else %}
  <p>不支持的媒体格式。</p>
{% endif %}
<p><a href="{{ url_for('index') }}">返回</a></p>
'''

if __name__ == '__main__':
    app.run(debug=True)
