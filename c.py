import os
import uuid
import sqlite3
from flask import (
    Flask, g, render_template_string,
    request, redirect, url_for,
    session, flash, send_from_directory,
    abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps

# ---------- 配置 ----------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')

# 上传根目录，每个用户一个子目录
UPLOAD_ROOT = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# 单文件最大 100MB
MAX_CONTENT_LENGTH = 100 * 1024 * 1024

SECRET_KEY = 'dev-secret-key'

# ---------- Flask 初始化 ----------
app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH
)

# ---------- 数据库管理 ----------
def get_db():
    """返回当前请求的 SQLite 连接，Row factory 支持通过列名访问。"""
    if 'db' not in g:
        conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db

@app.before_first_request
def init_db():
    """首次请求前初始化所需表结构。"""
    db = get_db()
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS user (
        id   INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        pwd  TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS folder (
        id        INTEGER PRIMARY KEY,
        name      TEXT,
        parent_id INTEGER,
        owner_id  INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS file (
        id           INTEGER PRIMARY KEY,
        filename     TEXT,
        stored_name  TEXT,
        folder_id    INTEGER,
        owner_id     INTEGER
    )""")
    db.commit()

@app.teardown_appcontext
def close_db(exc):
    """请求结束后关闭连接。"""
    db = g.pop('db', None)
    if db:
        db.close()

# ---------- 登录保护 ----------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('user_id'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrapper

# ---------- 用户上传目录路径 ----------
def user_upload_path(user_id):
    """返回并确保存在 uploads/<user_id> 目录。"""
    path = os.path.join(UPLOAD_ROOT, str(user_id))
    os.makedirs(path, exist_ok=True)
    return path

# ---------- 基础 HTML（含 JS 交互） ----------
BASE_HTML = """
<!doctype html>
<html><head>
  <meta charset="utf-8">
  <title>{{title or '云盘'}}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.0/dist/css/bootstrap.min.css"
        rel="stylesheet">
  <style>
    .droppable { background: #f0f8ff; }
    #ctx-menu { position:absolute; display:none; background:#fff; border:1px solid #ccc; z-index:1000; }
    #ctx-menu li { padding:6px 12px; cursor:pointer; }
    #ctx-menu li:hover { background:#eee; }
  </style>
</head><body onclick="hideMenu()">
<nav class="navbar navbar-expand-lg navbar-light bg-light">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">云盘</a>
    <ul class="navbar-nav ms-auto">
    {% if session.user_id %}
      <li class="nav-item"><span class="nav-link">Hi,{{session.username}}</span></li>
      <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">退出</a></li>
    {% else %}
      <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
      <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
    {% endif %}
    </ul>
  </div>
</nav>
<div class="container mt-4">
  {% for cat,msg in get_flashed_messages(with_categories=true) %}
    <div class="alert alert-{{cat}}">{{msg}}</div>
  {% endfor %}
  {{body|safe}}
</div>

<!-- 右键菜单 -->
<ul id="ctx-menu"><li onclick="doDelete()">删除</li></ul>

<script>
let dragItem = null, dragType = null;
function hideMenu(){
  document.getElementById('ctx-menu').style.display='none';
}
function showMenu(e,id,type){
  e.preventDefault();
  window.ctxTarget={id:type+'-'+id, type:type};
  const m=document.getElementById('ctx-menu');
  m.style.top=e.pageY+'px'; m.style.left=e.pageX+'px';
  m.style.display='block';
}
function doDelete(){
  const [type,id] = window.ctxTarget.id.split('-');
  fetch('/delete',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({id, type})
  })
  .then(r=>r.json()).then(ret=>{
    if(ret.ok) location.reload();
    else alert(ret.msg);
  });
}
function onDragStart(e){
  dragItem = e.currentTarget.dataset.id;
  dragType = e.currentTarget.dataset.type;
  e.dataTransfer.effectAllowed='move';
}
function onDragOver(e){
  e.preventDefault();
  e.currentTarget.classList.add('droppable');
}
function onDragLeave(e){
  e.currentTarget.classList.remove('droppable');
}
function onDrop(e){
  e.preventDefault(); e.currentTarget.classList.remove('droppable');
  const targetId = e.currentTarget.dataset.id;
  fetch('/move',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      id: dragItem,
      type: dragType,
      new_parent: targetId
    })
  })
  .then(r=>r.json()).then(ret=>{
    if(ret.ok) location.reload();
    else alert(ret.msg);
  });
}
</script>
</body></html>
"""

# ---------- 注册 ----------
@app.route('/register', methods=('GET','POST'))
def register():
    if request.method=='POST':
        name = request.form.get('username','').strip()
        pwd  = request.form.get('password','').strip()
        db   = get_db(); c = db.cursor()
        err = None
        if not name or not pwd:
            err = '用户名和密码不能为空'
        elif c.execute("SELECT 1 FROM user WHERE name=?", (name,)).fetchone():
            err = '用户名已存在'
        if err:
            flash(err,'warning')
        else:
            c.execute("INSERT INTO user(name,pwd) VALUES(?,?)",
                      (name, generate_password_hash(pwd)))
            db.commit()
            flash('注册成功，请登录','success')
            return redirect(url_for('login'))

    body = """
    <h2>注册</h2>
    <form method="post">
      <input name="username" placeholder="用户名" class="form-control mb-2">
      <input name="password" placeholder="密码" type="password" class="form-control mb-2">
      <button class="btn btn-primary">注册</button>
    </form>
    """
    return render_template_string(BASE_HTML, body=body)

# ---------- 登录 ----------
@app.route('/login', methods=('GET','POST'))
def login():
    if request.method=='POST':
        name = request.form.get('username','').strip()
        pwd  = request.form.get('password','').strip()
        user = get_db().execute(
            "SELECT * FROM user WHERE name=?", (name,)
        ).fetchone()
        if user and check_password_hash(user['pwd'], pwd):
            session.clear()
            session['user_id']  = user['id']
            session['username'] = user['name']
            return redirect(url_for('index'))
        flash('登录失败','danger')

    body = """
    <h2>登录</h2>
    <form method="post">
      <input name="username" placeholder="用户名" class="form-control mb-2">
      <input name="password" placeholder="密码" type="password" class="form-control mb-2">
      <button class="btn btn-primary">登录</button>
    </form>
    """
    return render_template_string(BASE_HTML, body=body)

# ---------- 登出 ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- 首页 / 目录列表 ----------
@app.route('/', defaults={'folder_id':None})
@app.route('/folder/<int:folder_id>')
@login_required
def index(folder_id):
    uid = session['user_id']; db = get_db()
    # 校验当前目录
    current = None
    if folder_id:
        current = db.execute(
            "SELECT * FROM folder WHERE id=? AND owner_id=?", (folder_id,uid)
        ).fetchone()
        if not current:
            abort(404)

    # 列子文件夹 & 文件
    if folder_id:
        folders = db.execute("""
          SELECT * FROM folder
          WHERE owner_id=? AND parent_id=?
        """, (uid,folder_id)).fetchall()
        files = db.execute("""
          SELECT * FROM file
          WHERE owner_id=? AND folder_id=?
        """, (uid,folder_id)).fetchall()
    else:
        folders = db.execute("""
          SELECT * FROM folder
          WHERE owner_id=? AND parent_id IS NULL
        """, (uid,)).fetchall()
        files = db.execute("""
          SELECT * FROM file
          WHERE owner_id=? AND folder_id IS NULL
        """, (uid,)).fetchall()

    # 渲染主体
    body = render_template_string("""
    <h3>
      {% if current %}
        <a href="{{url_for('index',folder_id=current.parent_id)}}">← 上级</a>
        {{current.name}}
      {% else %}根目录{% endif %}
    </h3>

    <!-- 创建文件夹 -->
    <form class="d-flex mb-3" method="post"
          action="{{url_for('create_folder',parent_id=folder_id or '')}}">
      <input name="name" placeholder="新建文件夹" class="form-control me-2">
      <button class="btn btn-primary">创建</button>
    </form>

    <!-- 上传文件 -->
    <form class="d-flex mb-3" method="post" enctype="multipart/form-data"
          action="{{url_for('upload',folder_id=folder_id or '')}}">
      <input type="file" name="file" class="form-control me-2">
      <button class="btn btn-success">上传</button>
    </form>

    <table class="table">
      <tr><th>类型</th><th>名称</th><th>操作</th></tr>
      {% for f in folders %}
      <tr draggable="true" data-id="{{f.id}}" data-type="folder"
          ondragstart="onDragStart(event)"
          oncontextmenu="showMenu(event,{{f.id}},'folder')"
          ondragover="onDragOver(event)" ondragleave="onDragLeave(event)"
          ondrop="onDrop(event)">
        <td>📁</td>
        <td><a href="{{url_for('index',folder_id=f.id)}}">{{f.name}}</a></td>
        <td></td>
      </tr>
      {% endfor %}
      {% for f in files %}
      <tr draggable="true" data-id="{{f.id}}" data-type="file"
          ondragstart="onDragStart(event)"
          oncontextmenu="showMenu(event,{{f.id}},'file')">
        <td>📄</td>
        <td>{{f.filename}}</td>
        <td>
          <a class="btn btn-sm btn-outline-primary"
             href="{{url_for('download',file_id=f.id)}}">
            下载
          </a>
        </td>
      </tr>
      {% endfor %}
    </table>
    """, current=current, folders=folders, files=files, folder_id=folder_id)
    return render_template_string(BASE_HTML, body=body)

# ---------- 新建文件夹 ----------
@app.route('/folder/create/<int:parent_id>', methods=('POST',))
@app.route('/folder/create', methods=('POST',), defaults={'parent_id':None})
@login_required
def create_folder(parent_id):
    name = request.form.get('name','').strip()
    if not name:
        flash('名称不能为空','warning')
    else:
        db = get_db()
        db.execute("INSERT INTO folder(name,parent_id,owner_id) VALUES(?,?,?)",
                   (name,parent_id,session['user_id']))
        db.commit()
        flash('创建成功','success')
    return redirect(request.referrer or url_for('index'))

# ---------- 上传文件 ----------
@app.route('/upload/<int:folder_id>', methods=('POST',))
@app.route('/upload', methods=('POST',), defaults={'folder_id':None})
@login_required
def upload(folder_id):
    f = request.files.get('file')
    if not f or not f.filename:
        flash('请选择文件','warning')
        return redirect(request.referrer or url_for('index'))

    # 原始文件名 & 后缀
    orig_name = secure_filename(f.filename)
    ext = os.path.splitext(orig_name)[1]
    # 存储名
    stored_name = uuid.uuid4().hex + ext

    # 构造物理目录：user_upload_path + 每级 folder.name
    base = user_upload_path(session['user_id'])
    # 追溯 folder_id 层级
    parts, cur = [], folder_id
    db = get_db()
    while cur:
        row = db.execute(
            "SELECT name,parent_id FROM folder WHERE id=? AND owner_id=?",
            (cur, session['user_id'])
        ).fetchone()
        if not row: abort(404)
        parts.append(row['name'])
        cur = row['parent_id']
    for p in reversed(parts):
        base = os.path.join(base, secure_filename(p))
        os.makedirs(base, exist_ok=True)

    # 保存到磁盘
    dest = os.path.join(base, stored_name)
    f.save(dest)

    # 写入元数据
    db.execute("""INSERT INTO file(filename,stored_name,folder_id,owner_id)
                  VALUES(?,?,?,?)""",
               (orig_name,stored_name,folder_id,session['user_id']))
    db.commit()
    flash('上传成功','success')
    return redirect(request.referrer or url_for('index'))

# ---------- 下载文件 ----------
@app.route('/download/<int:file_id>')
@login_required
def download(file_id):
    db = get_db()
    rec = db.execute("""SELECT filename,stored_name,folder_id
                        FROM file WHERE id=? AND owner_id=?""",
                     (file_id, session['user_id'])).fetchone()
    if not rec: abort(404)

    # 重建物理路径
    base = user_upload_path(session['user_id'])
    parts, cur = [], rec['folder_id']
    while cur:
        row = db.execute(
            "SELECT name,parent_id FROM folder WHERE id=? AND owner_id=?",
            (cur, session['user_id'])
        ).fetchone()
        parts.append(row['name'])
        cur = row['parent_id']
    for p in reversed(parts):
        base = os.path.join(base, secure_filename(p))

    return send_from_directory(
        base, rec['stored_name'],
        as_attachment=True, download_name=rec['filename']
    )

# ---------- 移动（拖拽） ----------
@app.route('/move', methods=('POST',))
@login_required
def move():
    d = request.get_json()
    _id, typ, newp = d.get('id'), d.get('type'), d.get('new_parent')
    db = get_db()

    # 防止把 folder 移到自身
    if typ=='folder' and str(_id)==str(newp):
        return jsonify(ok=False, msg="不能移动到自身")

    if typ=='folder':
        db.execute("UPDATE folder SET parent_id=? WHERE id=?", (newp, _id))
    else:
        db.execute("UPDATE file SET folder_id=? WHERE id=?", (newp, _id))

    db.commit()
    return jsonify(ok=True)

# ---------- 删除（递归） ----------
@app.route('/delete', methods=('POST',))
@login_required
def delete():
    d = request.get_json()
    _id, dtype = d.get('id'), d.get('type')
    db = get_db(); c = db.cursor()
    uid = session['user_id']

    # 删除文件
    if dtype=='file':
        rec = c.execute(
            "SELECT stored_name,folder_id FROM file WHERE id=? AND owner_id=?",
            (_id, uid)
        ).fetchone()
        if not rec:
            return jsonify(ok=False, msg="文件不存在")

        # 定位并删除物理文件
        base = user_upload_path(uid)
        parts, cur = [], rec['folder_id']
        while cur:
            row = db.execute(
                "SELECT name,parent_id FROM folder WHERE id=? AND owner_id=?",
                (cur, uid)
            ).fetchone()
            parts.append(row['name'])
            cur = row['parent_id']
        for p in reversed(parts):
            base = os.path.join(base, secure_filename(p))
        path = os.path.join(base, rec['stored_name'])
        if os.path.exists(path):
            os.remove(path)

        c.execute("DELETE FROM file WHERE id=?", (_id,))

    # 删除文件夹及其所有子文件夹和文件
    else:
        to_del = [int(_id)]; idx = 0
        # 收集所有子孙 folder_id
        while idx < len(to_del):
            fid = to_del[idx]
            subs = c.execute(
                "SELECT id FROM folder WHERE parent_id=? AND owner_id=?",
                (fid, uid)
            ).fetchall()
            to_del += [s['id'] for s in subs]
            idx += 1

        # 删除每个 folder 下的文件（物理+元数据）
        for fid in to_del:
            files = c.execute(
                "SELECT stored_name,folder_id FROM file WHERE folder_id=? AND owner_id=?",
                (fid, uid)
            ).fetchall()
            for f in files:
                base = user_upload_path(uid)
                parts, cur = [], f['folder_id']
                while cur:
                    row = db.execute(
                        "SELECT name,parent_id FROM folder WHERE id=? AND owner_id=?",
                        (cur, uid)
                    ).fetchone()
                    parts.append(row['name'])
                    cur = row['parent_id']
                for p in reversed(parts):
                    base = os.path.join(base, secure_filename(p))
                path = os.path.join(base, f['stored_name'])
                if os.path.exists(path):
                    os.remove(path)
            c.execute("DELETE FROM file WHERE folder_id=?", (fid,))

        # 删除所有 folder 记录
        seq = ','.join('?'*len(to_del))
        c.execute(
            f"DELETE FROM folder WHERE id IN ({seq}) AND owner_id=?",
            tuple(to_del)+(uid,)
        )

    db.commit()
    return jsonify(ok=True)

# ---------- 启动 ----------
if __name__ == '__main__':
    app.run(debug=True)
