import os
from flask import (
    Flask, request, redirect, url_for, render_template_string,
    send_from_directory, jsonify, flash, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin,
    login_user, logout_user,
    current_user, login_required
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from uuid import uuid4

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'files')
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

ALLOWED_EXTENSIONS = set([
    'txt', 'md', 'png', 'jpg', 'jpeg', 'gif', 'bmp',
    'mp4', 'webm', 'ogg'
])

app = Flask(__name__)
app.secret_key = 'change_this_to_a_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Share(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    path = db.Column(db.String(1024), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.token = uuid4().hex

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def secure_path_join(base, *paths):
    # 把路径安全join，防止目录穿越
    new_path = os.path.abspath(os.path.join(base, *paths))
    if not new_path.startswith(base):
        raise Exception("非法路径")
    return new_path

def allowed_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return '.' in filename and ext in ALLOWED_EXTENSIONS

def is_text_file(filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return ext in ('txt', 'md')

def build_tree(path):
    # 返回当前目录下的列表，分文件和文件夹
    try:
        items = os.listdir(path)
    except Exception:
        return {'dirs': [], 'files': []}
    dirs = []
    files = []
    for item in items:
        fullp = os.path.join(path, item)
        if os.path.isdir(fullp):
            dirs.append(item)
        else:
            files.append(item)
    dirs.sort()
    files.sort()
    return {'dirs': dirs, 'files': files}

base_template = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{% block title %}文件管理{% endblock %}</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<style>
body { padding-top: 70px; }
.navbar-brand { font-weight: bold; }
.breadcrumb-item+.breadcrumb-item::before {content: ">"}
pre { background: #f8f9fa; border-radius: 4px; padding: 10px; overflow-x: auto; }
img, video { max-width: 100%; height: auto; }
</style>
{% block style %}{% endblock %}
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-dark bg-primary fixed-top">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('files') }}">文件管理器</a>
    <div class="collapse navbar-collapse">
      <ul class="navbar-nav ms-auto">
        {% if current_user.is_authenticated %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('files') }}">浏览文件</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">退出</a></li>
        {% else %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">登录</a></li>
        {% endif %}
      </ul>
    </div>
  </div>
</nav>
<div class="container">
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div class="alert alert-info" role="alert">
        {% for msg in messages %}
          {{ msg }}<br/>
        {% endfor %}
      </div>
    {% endif %}
  {% endwith %}
  {% block body %}{% endblock %}
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body>
</html>
"""

@app.route('/register', methods=['GET','POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('files'))
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        if not u or not p:
            flash("用户名和密码不能为空")
            return redirect(url_for('register'))
        if User.query.filter_by(username=u).first():
            flash("用户名已存在")
            return redirect(url_for('register'))
        user = User(username=u)
        user.set_password(p)
        db.session.add(user)
        db.session.commit()
        flash("注册成功，请登录")
        return redirect(url_for('login'))
    return render_template_string("""
    {% extends base_template %}
    {% block title %}注册{% endblock %}
    {% block body %}
    <h2>注册新用户</h2>
    <form method="post">
      <div class="mb-3">
        <label>用户名</label>
        <input class="form-control" name="username" required />
      </div>
      <div class="mb-3">
        <label>密码</label>
        <input class="form-control" type="password" name="password" required />
      </div>
      <button class="btn btn-primary">注册</button>
      <a href="{{ url_for('login') }}" class="btn btn-link">登录</a>
    </form>
    {% endblock %}
    """, base_template=base_template)

@app.route('/login', methods=['GET','POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('files'))
    if request.method == 'POST':
        u = request.form.get('username','').strip()
        p = request.form.get('password','').strip()
        user = User.query.filter_by(username=u).first()
        if user and user.check_password(p):
            login_user(user)
            return redirect(url_for('files'))
        flash("账号或密码错误")
        return redirect(url_for('login'))
    return render_template_string("""
    {% extends base_template %}
    {% block title %}登录{% endblock %}
    {% block body %}
    <h2>登录</h2>
    <form method="post">
      <div class="mb-3">
        <label>用户名</label>
        <input class="form-control" name="username" required />
      </div>
      <div class="mb-3">
        <label>密码</label>
        <input class="form-control" type="password" name="password" required />
      </div>
      <button class="btn btn-primary">登录</button>
      <a href="{{ url_for('register') }}" class="btn btn-link">注册</a>
    </form>
    {% endblock %}
    """, base_template=base_template)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def breadcrumb_paths(path):
    parts = []
    if not path:
        return parts
    p = ''
    for sec in path.strip('/').split('/'):
        p = p+'/'+sec if p else sec
        parts.append((sec, p))
    return parts

def render_breadcrumb(path):
    crumbs = breadcrumb_paths(path)
    html = '<nav aria-label="breadcrumb"><ol class="breadcrumb">'
    html += '<li class="breadcrumb-item"><a href="%s">根目录</a></li>' % url_for('files')
    for name, p in crumbs[:-1]:
        hp = url_for('files', subpath=p)
        html += f'<li class="breadcrumb-item"><a href="{hp}">{name}</a></li>'
    if crumbs:
        html += f'<li class="breadcrumb-item active" aria-current="page">{crumbs[-1][0]}</li>'
    html += '</ol></nav>'
    return html

@app.route('/')
def index():
    return redirect(url_for('files'))

@app.route('/files/', defaults={'subpath': ''})
@app.route('/files/<path:subpath>')
@login_required
def files(subpath):
    safe_subpath = secure_filename(subpath)
    try:
        fullpath = secure_path_join(UPLOAD_FOLDER, safe_subpath)
    except Exception:
        flash('非法路径')
        return redirect(url_for('files'))

    if not os.path.exists(fullpath):
        flash('目录不存在')
        return redirect(url_for('files'))

    if not os.path.isdir(fullpath):
        flash('路径不是文件夹')
        return redirect(url_for('files'))

    tree = build_tree(fullpath)
    bread_html = render_breadcrumb(safe_subpath)

    template = """
    {% extends base_template %}
    {% block title %}文件浏览{% endblock %}
    {% block body %}
    {{ bread_html|safe }}
    <div class="d-flex mb-3">
      <form id="uploadForm" class="d-flex" enctype="multipart/form-data" method="post" action="{{ url_for('upload_file', subpath=safe_subpath) }}">
        <input type="file" name="file" class="form-control form-control-sm" />
        <button class="btn btn-sm btn-primary ms-2">上传</button>
      </form>
      <button class="btn btn-sm btn-success ms-3" id="btnNewFolder">新建文件夹</button>
    </div>
    <table class="table table-sm table-bordered align-middle">
      <thead>
        <tr>
          <th>名称</th>
          <th class="text-center" style="width:150px;">操作</th>
        </tr>
      </thead>
      <tbody>
       {% for d in tree.dirs %}
        <tr>
          <td><a href="{{ url_for('files', subpath=(safe_subpath + '/' if safe_subpath else '') + d) }}"><span class="me-2">📁</span>{{ d }}</a></td>
          <td class="text-center">
            <button class="btn btn-outline-danger btn-sm btnDel" data-path="{{ (safe_subpath + '/' if safe_subpath else '') + d }}">删除</button>
            <button class="btn btn-outline-secondary btn-sm btnRename" data-path="{{ (safe_subpath + '/' if safe_subpath else '') + d }}">重命名</button>
          </td>
        </tr>
       {% endfor %}
       {% for f in tree.files %}
        <tr>
          <td>
            {% if is_text_file(f) %}
            <span class="me-2">📄</span><a href="{{ url_for('edit_file', subpath=(safe_subpath + '/' if safe_subpath else '') + f) }}">{{ f }}</a>
            {% elif f.lower().endswith(('.png','.jpg','.jpeg','.bmp','.gif')) %}
            <span class="me-2">🖼️</span><a href="{{ url_for('view_file', subpath=(safe_subpath + '/' if safe_subpath else '') + f) }}">{{ f }}</a>
            {% elif f.lower().endswith(('.mp4','.webm','.ogg')) %}
            <span class="me-2">🎞️</span><a href="{{ url_for('view_file', subpath=(safe_subpath + '/' if safe_subpath else '') + f) }}">{{ f }}</a>
            {% else %}
            <span class="me-2">📄</span><a href="{{ url_for('download_file', subpath=(safe_subpath + '/' if safe_subpath else '') + f) }}">{{ f }}</a>
            {% endif %}
          </td>
          <td class="text-center">
            <a class="btn btn-outline-primary btn-sm" href="{{ url_for('download_file', subpath=(safe_subpath + '/' if safe_subpath else '') + f) }}" download>下载</a>
            <button class="btn btn-outline-danger btn-sm btnDel" data-path="{{ (safe_subpath + '/' if safe_subpath else '') + f }}">删除</button>
            <button class="btn btn-outline-secondary btn-sm btnRename" data-path="{{ (safe_subpath + '/' if safe_subpath else '') + f }}">重命名</button>
          </td>
        </tr>
       {% endfor %}
      </tbody>
    </table>
    <hr />
    <h5>生成分享链接</h5>
    <form id="formShare" class="row g-2 mb-3">
      <div class="col-auto">
        <input type="text" class="form-control" readonly id="sharePath" value="{{ safe_subpath }}">
      </div>
      <div class="col-auto">
        <button class="btn btn-primary" type="submit">生成分享链接</button>
      </div>
    </form>
    <div id="shareResult"></div>
    {% endblock %}
    {% block scripts %}
    <script>
    // 新建文件夹
    document.getElementById('btnNewFolder').addEventListener('click', function(){
      let name=prompt('请输入新文件夹名称');
      if(!name)return alert('名称不能为空');
      fetch("{{ url_for('mkdir') }}", {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({parent:"{{ safe_subpath }}", folder_name:name})
      }).then(r=>r.json()).then(j=> {
        alert(j.msg);
        if(j.ok) location.reload();
      }).catch(()=>alert('请求失败'));
    });
    // 删除
    document.querySelectorAll('.btnDel').forEach(b=>{
      b.onclick = function(){
        if(!confirm("确定删除吗？")) return;
        fetch("{{ url_for('delete') }}", {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({path:this.dataset.path})
        }).then(r=>r.json()).then(j=>{
          alert(j.msg);
          if(j.ok) location.reload();
        }).catch(()=>alert('请求失败'));
      };
    });
    // 重命名
    document.querySelectorAll('.btnRename').forEach(b=>{
      b.onclick = function(){
        let oldname=this.dataset.path;
        let newname=prompt('请输入新名称', oldname.split('/').pop());
        if(!newname) return alert('新名称不能为空');
        fetch("{{ url_for('rename') }}", {
          method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({old_path:oldname, new_name:newname})
        }).then(r=>r.json()).then(j=>{
          alert(j.msg);
          if(j.ok) location.reload();
        }).catch(()=>alert('请求失败'));
      };
    });
    // 生成分享链接
    document.getElementById('formShare').onsubmit = function(e){
      e.preventDefault();
      let p = document.getElementById('sharePath').value;
      fetch("{{ url_for('share_create') }}", {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({path:p})
      }).then(r => r.json()).then(j => {
        if(j.ok){
          document.getElementById('shareResult').innerHTML =
            '<div class="alert alert-info">分享链接：<a href="'+j.url+'" target="_blank">'+j.url+'</a></div>';
        } else {
          alert(j.msg || '失败');
        }
      }).catch(()=>alert('请求失败'));
    };
    </script>
    {% endblock %}
    """
    return render_template_string(template,
        base_template=base_template, safe_subpath=safe_subpath,
        tree=tree, bread_html=bread_html, is_text_file=is_text_file)

@app.route('/upload/<path:subpath>', methods=['POST'])
@login_required
def upload_file(subpath):
    try:
        folder = secure_path_join(UPLOAD_FOLDER, secure_filename(subpath))
    except:
        flash("非法路径")
        return redirect(url_for('files'))

    if not os.path.isdir(folder):
        flash("不是目录")
        return redirect(url_for('files'))

    file = request.files.get('file')
    if not file or file.filename == '':
        flash("未选择文件")
        return redirect(url_for('files', subpath=subpath))

    filename = secure_filename(file.filename)
    if filename == '':
        flash("非法文件名")
        return redirect(url_for('files', subpath=subpath))

    file_path = os.path.join(folder, filename)
    file.save(file_path)
    flash("上传成功")
    return redirect(url_for('files', subpath=subpath))

@app.route('/download/<path:subpath>')
@login_required
def download_file(subpath):
    try:
        full_path = secure_path_join(UPLOAD_FOLDER, secure_filename(subpath))
    except:
        abort(404)

    if not os.path.isfile(full_path):
        abort(404)

    folder, filename = os.path.split(full_path)
    return send_from_directory(folder, filename, as_attachment=True)

@app.route('/view/<path:subpath>')
@login_required
def view_file(subpath):
    try:
        full_path = secure_path_join(UPLOAD_FOLDER, secure_filename(subpath))
    except:
        abort(404)
    if not os.path.isfile(full_path):
        abort(404)
    ext = full_path.rsplit('.', 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        abort(403)
    folder, filename = os.path.split(full_path)
    if ext in ('png', 'jpg', 'jpeg', 'bmp', 'gif'):
        # 图片直接显示
        return render_template_string("""
        {% extends base_template %}
        {% block title %}图片查看{% endblock %}
        {% block body %}
          <h4>图片预览: {{ filename }}</h4>
          <img src="{{ url_for('file_raw', subpath=subpath) }}" alt="{{ filename }}" />
          <p><a href="{{ url_for('files', subpath=subpath.rsplit('/',1)[0]) }}">返回</a></p>
        {% endblock %}
        """, base_template=base_template, filename=filename, subpath=subpath)
    elif ext in ('mp4','webm','ogg'):
        # 视频播放
        return render_template_string("""
        {% extends base_template %}
        {% block title %}视频查看{% endblock %}
        {% block body %}
          <h4>视频播放: {{ filename }}</h4>
          <video controls autoplay style="max-width:100%">
            <source src="{{ url_for('file_raw', subpath=subpath) }}" type="video/{{ filename.rsplit('.',1)[-1] }}">
            您的浏览器不支持视频播放。
          </video>
          <p><a href="{{ url_for('files', subpath=subpath.rsplit('/',1)[0]) }}">返回</a></p>
        {% endblock %}
        """, base_template=base_template, filename=filename, subpath=subpath)
    else:
        return redirect(url_for('download_file', subpath=subpath))

@app.route('/file/<path:subpath>')
@login_required
def file_raw(subpath):
    try:
        full_path = secure_path_join(UPLOAD_FOLDER, secure_filename(subpath))
    except:
        abort(404)
    if not os.path.isfile(full_path):
        abort(404)
    folder, filename = os.path.split(full_path)
    return send_from_directory(folder, filename)

@app.route('/edit/<path:subpath>', methods=['GET','POST'])
@login_required
def edit_file(subpath):
    try:
        full_path = secure_path_join(UPLOAD_FOLDER, secure_filename(subpath))
    except:
        flash('非法路径')
        return redirect(url_for('files'))
    if not os.path.isfile(full_path):
        flash('文件不存在')
        return redirect(url_for('files'))

    if not is_text_file(full_path):
        flash('只能编辑文本文件(.txt .md)')
        return redirect(url_for('files'))

    if request.method == 'POST':
        content = request.form.get('content','')
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            flash('保存成功')
        except Exception as e:
            flash('保存失败: '+str(e))
        return redirect(url_for('edit_file', subpath=subpath))

    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        flash('读取文件失败: '+str(e))
        return redirect(url_for('files'))
    filename = os.path.basename(full_path)
    return render_template_string("""
    {% extends base_template %}
    {% block title %}编辑 {{ filename }}{% endblock %}
    {% block body %}
    <h4>编辑文件: {{ filename }}</h4>
    <form method="post">
      <textarea name="content" style="width:100%; height:400px; font-family:monospace; font-size:14px;">{{ content }}</textarea>
      <br/>
      <button class="btn btn-primary mt-2">保存</button>
      <a href="{{ url_for('files', subpath=subpath.rsplit('/', 1)[0]) }}" class="btn btn-secondary mt-2">返回</a>
    </form>
    {% endblock %}
    """, base_template=base_template, filename=filename, content=content, subpath=subpath)

@app.route('/mkdir', methods=['POST'])
@login_required
def mkdir():
    data = request.get_json() or {}
    parent = data.get('parent','')
    folder_name = data.get('folder_name','').strip()
    if not folder_name:
        return jsonify(ok=False, msg="文件夹名不能为空")
    try:
        parent_safe = secure_filename(parent)
        folder_safe = secure_filename(folder_name)
        path = secure_path_join(UPLOAD_FOLDER, parent_safe, folder_safe)
    except:
        return jsonify(ok=False, msg="非法路径")

    if os.path.exists(path):
        return jsonify(ok=False, msg="文件夹已存在")
    try:
        os.makedirs(path)
        return jsonify(ok=True, msg="创建成功")
    except Exception as e:
        return jsonify(ok=False, msg="创建失败："+str(e))

@app.route('/delete', methods=['POST'])
@login_required
def delete():
    data = request.get_json() or {}
    pathstr = data.get('path','').strip()
    if not pathstr:
        return jsonify(ok=False, msg="路径不能为空")
    try:
        fullpath = secure_path_join(UPLOAD_FOLDER, secure_filename(pathstr))
    except:
        return jsonify(ok=False, msg="非法路径")

    if not os.path.exists(fullpath):
        return jsonify(ok=False, msg="文件或目录不存在")
    try:
        if os.path.isfile(fullpath):
            os.remove(fullpath)
        else:
            # 递归删除目录
            import shutil
            shutil.rmtree(fullpath)
        return jsonify(ok=True, msg="删除成功")
    except Exception as e:
        return jsonify(ok=False, msg="删除失败："+str(e))

@app.route('/rename', methods=['POST'])
@login_required
def rename():
    data = request.get_json() or {}
    old_path = data.get('old_path','').strip()
    new_name = data.get('new_name','').strip()
    if not old_path or not new_name:
        return jsonify(ok=False, msg="参数错误")
    try:
        old_full = secure_path_join(UPLOAD_FOLDER, secure_filename(old_path))
    except:
        return jsonify(ok=False, msg="非法路径")
    if not os.path.exists(old_full):
        return jsonify(ok=False, msg="文件或目录不存在")
    new_name_sec = secure_filename(new_name)
    new_full = os.path.join(os.path.dirname(old_full), new_name_sec)
    if os.path.exists(new_full):
        return jsonify(ok=False, msg="目标名称已存在")
    try:
        os.rename(old_full, new_full)
        return jsonify(ok=True, msg="重命名成功")
    except Exception as e:
        return jsonify(ok=False, msg="重命名失败："+str(e))

@app.route('/move', methods=['POST'])
@login_required
def move():
    data = request.get_json() or {}
    src = data.get('src','').strip()
    dst = data.get('dst','').strip()
    if not src or not dst:
        return jsonify(ok=False, msg="参数错误")
    try:
        src_full = secure_path_join(UPLOAD_FOLDER, secure_filename(src))
        dst_full = secure_path_join(UPLOAD_FOLDER, secure_filename(dst))
    except:
        return jsonify(ok=False, msg="非法路径")
    if not os.path.exists(src_full):
        return jsonify(ok=False, msg="源文件不存在")
    if not os.path.isdir(dst_full):
        return jsonify(ok=False, msg="目标必须是目录")
    try:
        base = os.path.basename(src_full)
        target_path = os.path.join(dst_full, base)
        if os.path.exists(target_path):
            return jsonify(ok=False, msg="目标目录已有同名文件或目录")
        os.rename(src_full, target_path)
        return jsonify(ok=True, msg="移动成功")
    except Exception as e:
        return jsonify(ok=False, msg="移动失败："+str(e))

@app.route('/share', methods=['POST'])
@login_required
def share_create():
    data = request.get_json() or {}
    path = data.get('path','').strip()
    try:
        path_safe = secure_filename(path)
        fullpath = secure_path_join(UPLOAD_FOLDER, path_safe)
    except:
        return jsonify(ok=False, msg="非法路径")
    if not os.path.exists(fullpath):
        return jsonify(ok=False, msg="文件或目录不存在")
    share = Share(path=path_safe)
    db.session.add(share)
    db.session.commit()
    url = url_for('share_access', token=share.token, _external=True)
    return jsonify(ok=True, url=url)

@app.route('/s/<token>')
def share_access(token):
    share = Share.query.filter_by(token=token).first_or_404()
    try:
        fullpath = secure_path_join(UPLOAD_FOLDER, share.path)
    except:
        abort(404)
    if os.path.isdir(fullpath):
        # 显示目录（同 files）
        tree = build_tree(fullpath)
        bread_html = render_breadcrumb(share.path)
        return render_template_string("""
        {% extends base_template %}
        {% block title %}分享的目录{% endblock %}
        {% block body %}
        <h4>分享目录（只读）: {{ share.path }}</h4>
        {{ bread_html|safe }}
        <ul>
        {% for d in tree.dirs %}
          <li>📁 {{ d }}</li>
        {% endfor %}
        {% for f in tree.files %}
          <li>📄 {{ f }}</li>
        {% endfor %}
        </ul>
        {% endblock %}
        """, base_template=base_template, tree=tree, share=share, bread_html=bread_html)
    elif os.path.isfile(fullpath):
        ext = fullpath.rsplit('.',1)[-1].lower()
        if is_text_file(fullpath):
            try:
                with open(fullpath,'r',encoding='utf-8') as f:
                    content = f.read()
            except:
                content = ""
            return render_template_string("""
            {% extends base_template %}
            {% block title %}分享的文件{% endblock %}
            {% block body %}
            <h4>分享文本文件: {{ share.path }}</h4>
            <pre>{{ content }}</pre>
            {% endblock %}
            """, base_template=base_template, share=share, content=content)
        elif ext in ('png','jpg','jpeg','bmp','gif'):
            return render_template_string("""
            {% extends base_template %}
            {% block title %}分享的图片{% endblock %}
            {% block body %}
            <h4>分享图片: {{ share.path }}</h4>
            <img src="{{ url_for('share_raw_file', token=share.token) }}" alt="共享图片" style="max-width:100%"/>
            {% endblock %}
            """, base_template=base_template, share=share)
        elif ext in ('mp4','webm','ogg'):
            return render_template_string("""
            {% extends base_template %}
            {% block title %}分享的视频{% endblock %}
            {% block body %}
            <h4>分享视频: {{ share.path }}</h4>
            <video controls style="max-width: 100%;" autoplay>
              <source src="{{ url_for('share_raw_file', token=share.token) }}" type="video/{{ share.path.rsplit('.',1)[-1] }}"/>
              你的浏览器不支持播放视频。
            </video>
            {% endblock %}
            """, base_template=base_template, share=share)
        else:
            return redirect(url_for('share_raw_file', token=share.token))
    else:
        abort(404)

@app.route('/s/<token>/raw')
def share_raw_file(token):
    share = Share.query.filter_by(token=token).first_or_404()
    try:
        fullpath = secure_path_join(UPLOAD_FOLDER, share.path)
    except:
        abort(404)
    if not os.path.isfile(fullpath):
        abort(404)
    folder, filename = os.path.split(fullpath)
    return send_from_directory(folder, filename)

# 初始化数据库和首个用户
@app.before_first_request
def setup():
    db.create_all()
    if not User.query.first():
        u = User(username='admin')
        u.set_password('admin')
        db.session.add(u)
        db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
