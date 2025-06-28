import os
import sqlite3
import uuid
from flask import (
    Flask, g, render_template_string,
    request, redirect, url_for,
    session, flash, send_from_directory, abort, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------- 配置 ----------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MAX_CONTENT_LENGTH = 100 * 1024 * 1024
SECRET_KEY = 'dev-secret-key'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH
)

# ---------- 单文件模板 ----------
BASE_HTML = """
<!doctype html>
<html><head>
  <meta charset="utf-8">
  <title>{{ title or '云盘' }}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.2.0/dist/css/bootstrap.min.css" rel="stylesheet">
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
    {% if session.get('user_id') %}
      <li class="nav-item"><span class="nav-link">Hi,{{session.get('username')}}</span></li>
      <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">退出</a></li>
    {% else %}
      <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
      <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">注册</a></li>
    {% endif %}
    </ul>
  </div>
</nav>
<div class="container mt-4">
  {% with msgs = get_flashed_messages(with_categories=true) %}
    {% if msgs %}
      {% for cat,msg in msgs %}
        <div class="alert alert-{{cat}}">{{msg}}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}
  {{ body }}
</div>
<ul id="ctx-menu"><li onclick="doDelete()">删除</li></ul>
<script>
let dragItem = null, dragType = null;
function hideMenu(){
  document.getElementById('ctx-menu').style.display='none';
}
function showMenu(e,id,type){
  e.preventDefault();
  window.ctxTarget={id:type+'-'+id,type:type};
  const m=document.getElementById('ctx-menu');
  m.style.top=e.pageY+'px'; m.style.left=e.pageX+'px'; m.style.display='block';
}
function doDelete(){
  const [type,id]=window.ctxTarget.id.split('-');
  fetch('/delete', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id, type})
  }).then(r=>r.json()).then(ret=>{
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
  const targetId=e.currentTarget.dataset.id;
  fetch('/move',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({id:dragItem, type:dragType, new_parent:targetId})
  }).then(r=>r.json()).then(ret=>{
    if(ret.ok) location.reload();
    else alert(ret.msg);
  });
}
</script>
</body></html>
"""

# ---------- DB 操作 ----------
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.before_first_request
def init_db():
    db = get_db(); c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY, name TEXT UNIQUE, pwd TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS folder (
        id INTEGER PRIMARY KEY, name TEXT,
        parent_id INTEGER, owner_id INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS file (
        id INTEGER PRIMARY KEY, filename TEXT,
        stored_name TEXT, folder_id INTEGER, owner_id INTEGER)""")
    db.commit()

@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db: db.close()

# ---------- Auth ----------
from functools import wraps
def login_required(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get('user_id'): return redirect(url_for('login'))
        return f(*a,**k)
    return w

# ---------- 注册/登录/登出 ----------
@app.route('/register', methods=('GET','POST'))
def register():
    if request.method=='POST':
        name,pwd=request.form['username'],request.form['password']
        db,c=get_db(),get_db().cursor()
        err=None
        if not name or not pwd: err='用户名或密码不能为空'
        elif c.execute("SELECT 1 FROM user WHERE name=?", (name,)).fetchone(): err='用户已存在'
        if err: flash(err,'warning')
        else:
            c.execute("INSERT INTO user(name,pwd) VALUES(?,?)",
                      (name, generate_password_hash(pwd)))
            db.commit(); flash('注册成功','success'); return redirect(url_for('login'))
    body="""
    <h2>注册</h2><form method="post">
      <input name="username" placeholder="用户名" class="form-control mb-2">
      <input name="password" placeholder="密码" type="password" class="form-control mb-2">
      <button class="btn btn-primary">注册</button>
    </form>"""
    return render_template_string(BASE_HTML, body=body)

@app.route('/login', methods=('GET','POST'))
def login():
    if request.method=='POST':
        name,pwd=request.form['username'],request.form['password']
        user=get_db().execute("SELECT * FROM user WHERE name=?", (name,)).fetchone()
        if user and check_password_hash(user['pwd'],pwd):
            session.clear()
            session['user_id'],session['username']=user['id'],user['name']
            return redirect(url_for('index'))
        flash('登录失败','danger')
    body="""
    <h2>登录</h2><form method="post">
      <input name="username" placeholder="用户名" class="form-control mb-2">
      <input name="password" placeholder="密码" type="password" class="form-control mb-2">
      <button class="btn btn-primary">登录</button>
    </form>"""
    return render_template_string(BASE_HTML, body=body)

@app.route('/logout')
def logout():
    session.clear(); return redirect(url_for('login'))

# ---------- 列表/上传/新建 ----------
@app.route('/', defaults={'folder_id':None})
@app.route('/folder/<int:folder_id>')
@login_required
def index(folder_id):
    uid=session['user_id']; db=get_db()
    cur=None
    if folder_id:
        cur=db.execute(
            "SELECT * FROM folder WHERE id=? AND owner_id=?", (folder_id,uid)
        ).fetchone()
        if not cur: abort(404)
    folders=db.execute(
        "SELECT * FROM folder WHERE owner_id=? AND " +
        ("parent_id=?" if folder_id else "parent_id IS NULL"),
        (uid,folder_id) if folder_id else (uid,)
    ).fetchall()
    files=db.execute(
        "SELECT * FROM file WHERE owner_id=? AND " +
        ("folder_id=?" if folder_id else "folder_id IS NULL"),
        (uid,folder_id) if folder_id else (uid,)
    ).fetchall()
    body=render_template_string("""
    <h3>
      {% if cur %}<a href="{{url_for('index',folder_id=cur['parent_id'])}}">← 上级</a>{{cur['name']}}
      {% else %}根目录{% endif %}
    </h3>
    <form class="d-flex mb-3" method="post"
          action="{{url_for('create_folder',parent_id=folder_id or '')}}">
      <input name="name" placeholder="新建文件夹" class="form-control me-2">
      <button class="btn btn-primary">创建</button>
    </form>
    <form class="d-flex mb-3" method="post" enctype="multipart/form-data"
          action="{{url_for('upload',folder_id=folder_id or '')}}">
      <input type="file" name="file" class="form-control me-2">
      <button class="btn btn-success">上传</button>
    </form>
    <table class="table">
      <tr><th>类型</th><th>名称</th><th>操作</th></tr>
      {% for f in folders %}
      <tr draggable="true" data-id="{{f['id']}}" data-type="folder"
          ondragstart="onDragStart(event)"
          oncontextmenu="showMenu(event,{{f['id']}},'folder')"
          ondragover="onDragOver(event)" ondragleave="onDragLeave(event)"
          ondrop="onDrop(event)">
        <td>📁</td>
        <td><a href="{{url_for('index',folder_id=f['id'])}}">{{f['name']}}</a></td>
        <td></td>
      </tr>
      {% endfor %}
      {% for f in files %}
      <tr draggable="true" data-id="{{f['id']}}" data-type="file"
          ondragstart="onDragStart(event)"
          oncontextmenu="showMenu(event,{{f['id']}},'file')">
        <td>📄</td>
        <td>{{f['filename']}}</td>
        <td>
          <a class="btn btn-sm btn-outline-primary"
             href="{{url_for('download',file_id=f['id'])}}">下载</a>
        </td>
      </tr>
      {% endfor %}
    </table>
    """, cur=cur, folders=folders, files=files, folder_id=folder_id)
    return render_template_string(BASE_HTML, body=body)

@app.route('/folder/create', methods=('POST',), defaults={'parent_id':None})
@app.route('/folder/create/<int:parent_id>', methods=('POST',))
@login_required
def create_folder(parent_id):
    name=request.form.get('name','').strip()
    if name:
        db=get_db()
        db.execute("INSERT INTO folder(name,parent_id,owner_id) VALUES(?,?,?)",
                   (name,parent_id,session['user_id']))
        db.commit(); flash('创建成功','success')
    else:
        flash('名称不能为空','warning')
    return redirect(request.referrer or url_for('index'))

@app.route('/upload', methods=('POST',), defaults={'folder_id':None})
@app.route('/upload/<int:folder_id>', methods=('POST',))
@login_required
def upload(folder_id):
    file=request.files.get('file')
    if file:
        fn=secure_filename(file.filename)
        ext=os.path.splitext(fn)[1]
        stored=uuid.uuid4().hex+ext
        file.save(os.path.join(UPLOAD_FOLDER,stored))
        db=get_db()
        db.execute("INSERT INTO file(filename,stored_name,folder_id,owner_id) VALUES(?,?,?,?)",
                   (fn,stored,folder_id,session['user_id']))
        db.commit(); flash('上传成功','success')
    else:
        flash('请选择文件','warning')
    return redirect(request.referrer or url_for('index'))

# ---------- 下载 ----------
@app.route('/download/<int:file_id>')
@login_required
def download(file_id):
    f=get_db().execute(
        "SELECT * FROM file WHERE id=? AND owner_id=?", (file_id,session['user_id'])
    ).fetchone()
    if not f: abort(404)
    return send_from_directory(UPLOAD_FOLDER, f['stored_name'],
                               as_attachment=True, download_name=f['filename'])

# ---------- 移动 ----------
@app.route('/move', methods=['POST'])
@login_required
def move():
    d=request.get_json()
    _id,typ,newp=d.get('id'),d.get('type'),d.get('new_parent')
    db=get_db()
    if typ=='folder':
        if str(_id)==str(newp):
            return jsonify(ok=False,msg="不能移动到自身")
        db.execute("UPDATE folder SET parent_id=? WHERE id=?", (newp,_id))
    else:
        db.execute("UPDATE file SET folder_id=? WHERE id=?", (newp,_id))
    db.commit()
    return jsonify(ok=True)

# ---------- 删除（深度递归） ----------
@app.route('/delete', methods=['POST'])
@login_required
def delete():
    d=request.get_json(); _id,dtype=d.get('id'),d.get('type')
    db=get_db(); cur=db.cursor()
    uid=session['user_id']
    if dtype=='file':
        # 删除单个文件
        rec=cur.execute("SELECT stored_name FROM file WHERE id=? AND owner_id=?", (_id,uid)).fetchone()
        if not rec: return jsonify(ok=False,msg="文件不存在")
        path=os.path.join(UPLOAD_FOLDER, rec['stored_name'])
        if os.path.exists(path): os.remove(path)
        cur.execute("DELETE FROM file WHERE id=?", (_id,))
    else:
        # 递归收集 folder_id 列表
        to_delete = [int(_id)]
        idx=0
        while idx < len(to_delete):
            fid = to_delete[idx]
            subs = cur.execute("SELECT id FROM folder WHERE parent_id=? AND owner_id=?", (fid,uid)).fetchall()
            to_delete += [s['id'] for s in subs]
            idx+=1
        # 删除所有文件记录 & 物理文件
        for fid in to_delete:
            files = cur.execute("SELECT stored_name FROM file WHERE folder_id=? AND owner_id=?", (fid,uid)).fetchall()
            for f in files:
                path=os.path.join(UPLOAD_FOLDER, f['stored_name'])
                if os.path.exists(path): os.remove(path)
            cur.execute("DELETE FROM file WHERE folder_id=?", (fid,))
        # 删除所有 folder 记录
        cur.execute(
            "DELETE FROM folder WHERE id IN ({seq}) AND owner_id=?"
            .format(seq=','.join('?'*len(to_delete))),
            tuple(to_delete)+(uid,)
        )
    db.commit()
    return jsonify(ok=True)

if __name__ == '__main__':
    app.run(debug=True)
