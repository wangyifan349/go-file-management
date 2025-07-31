import os
import shutil
import uuid
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config.update(
    SECRET_KEY='mysecretkey',
    SQLALCHEMY_DATABASE_URI='sqlite:///users.db',
    UPLOAD_FOLDER='uploads',
    ALLOWED_EXTENSIONS={'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'},
)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# === 模型 ===

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)
    shares = db.relationship('Share', backref='owner', lazy=True)

class Share(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    relative_path = db.Column(db.String(300), nullable=False)  # 分享路径（相对用户上传根目录）

# === 创建数据库及上传文件夹 ===
@app.before_first_request
def init_app():
    db.create_all()
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# === 工具函数 ===

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def user_base_dir(username):
    safe_name = secure_filename(username)
    base = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    if not os.path.exists(base):
        os.makedirs(base)
    return base

def safe_join(base, *paths):
    abs_path = os.path.abspath(os.path.join(base, *paths))
    if not abs_path.startswith(os.path.abspath(base)):
        raise RuntimeError("访问越界")
    return abs_path

def get_file_tree(base, rel_path=""):
    abs_path = safe_join(base, rel_path)
    tree = []
    if not os.path.exists(abs_path):
        return tree
    for item in sorted(os.listdir(abs_path)):
        item_abs = os.path.join(abs_path, item)
        rel_item = os.path.join(rel_path, item).replace("\\", "/")
        node = {
            "name": item,
            "path": rel_item,
            "type": "dir" if os.path.isdir(item_abs) else "file"
        }
        if node['type'] == 'dir':
            node['children'] = get_file_tree(base, rel_item)
        tree.append(node)
    return tree

# === 模板字符串管理 ===
templates = {
    "base": '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{% block title %}文件管理系统{% endblock %}</title>
<style>
body {font-family: "Microsoft Yahei", sans-serif; margin:20px;}
nav a {margin-right: 15px;}
ul {list-style: none; padding-left: 18px;}
li {margin:5px 0; cursor:pointer;}
.dir {font-weight:bold; color:#0b74de;}
.file {color:#444;}
#ctxMenu {position:absolute; background:#fff; border:1px solid #ccc; z-index:1000;}
#ctxMenu div {padding:5px 10px;}
#ctxMenu div:hover {background:#def;}
.error {color:red;}
</style>
{% block head %}{% endblock %}
</head>
<body>
<nav>
  <a href="{{ url_for('index') }}">首页</a>
  {% if current_user.is_authenticated %}
    <span>用户：{{ current_user.username }}</span>
    <a href="{{ url_for('logout') }}">登出</a>
    <a href="{{ url_for('my_shares') }}">我的分享</a>
  {% else %}
    <a href="{{ url_for('login') }}">登录</a>
    <a href="{{ url_for('register') }}">注册</a>
  {% endif %}
</nav>
<hr>
{% if error %}
  <div class="error">{{ error }}</div>
{% endif %}
{% block content %}{% endblock %}
{% block scripts %}{% endblock %}
</body>
</html>
''',

    "register": '''
{% extends "base" %}
{% block title %}注册{% endblock %}
{% block content %}
<h2>注册新用户</h2>
<form method="post">
  用户名：<input name="username" required><br><br>
  密码：<input type="password" name="password" required><br><br>
  <button>注册</button>
</form>
{% endblock %}
''',

    "login": '''
{% extends "base" %}
{% block title %}登录{% endblock %}
{% block content %}
<h2>用户登录</h2>
<form method="post">
  用户名：<input name="username" required><br><br>
  密码：<input type="password" name="password" required><br><br>
  <button>登录</button>
</form>
{% endblock %}
''',

    "index": '''
{% extends "base" %}
{% block title %}文件管理首页{% endblock %}
{% block content %}
<h2>文件管理</h2>
<form id="uploadForm" enctype="multipart/form-data">
  <input type="file" name="file" required>
  <input type="hidden" name="path" id="uploadPath" value="">
  <button>上传到当前目录</button>
</form>
<div id="treeContainer" style="margin-top:20px; user-select:none;"></div>
<div id="shareLink" style="color:green; margin-top:10px;"></div>
{% endblock %}
{% block scripts %}
<script>
let currentPath = "";
function fetchTree() {
  fetch(`/api/tree?path=${encodeURIComponent(currentPath)}`)
    .then(r => r.json())
    .then(res => {
      if(res.success) renderTree(res.tree);
      else alert(res.error);
    });
}

function renderTree(nodes, container=document.getElementById('treeContainer')) {
  container.innerHTML = "";
  const ul = document.createElement('ul');
  container.appendChild(ul);
  nodes.forEach(node => {
    const li = document.createElement('li');
    li.textContent = node.name;
    li.dataset.path = node.path;
    li.className = node.type;
    // 点击文件下载，点击目录打开
    if(node.type === 'dir') {
      li.onclick = () => {
        currentPath = node.path;
        document.getElementById('uploadPath').value = currentPath;
        fetchTree();
      };
    } else {
      li.onclick = () => {
        location.href = `/api/download?path=${encodeURIComponent(node.path)}`;
      };
    }
    // 右键菜单
    li.oncontextmenu = e => {
      e.preventDefault();
      showContextMenu(e.pageX, e.pageY, node);
    };
    
    // 子节点
    if(node.type === 'dir' && node.children && node.children.length) {
      const div = document.createElement('div');
      renderTree(node.children, div);
      li.appendChild(div);
    }
    ul.appendChild(li);
  });
}

function showContextMenu(x, y, node) {
  const oldMenu = document.getElementById('ctxMenu');
  if(oldMenu) oldMenu.remove();

  const menu = document.createElement('div');
  menu.id = 'ctxMenu';
  menu.style.left = x + 'px';
  menu.style.top = y + 'px';

  const actions = ['删除', '重命名', '移动'];
  actions.forEach(action => {
    const item = document.createElement('div');
    item.textContent = action;
    item.onclick = () => {
      if(action === '删除') doDelete(node);
      else if(action === '重命名') doRename(node);
      else if(action === '移动') doMove(node);
      menu.remove();
    };
    menu.appendChild(item);
  });

  if(node.type === 'dir') {
    const shareItem = document.createElement('div');
    shareItem.textContent = '分享目录';
    shareItem.onclick = () => {
      fetch('/api/share', {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: `path=${encodeURIComponent(node.path)}`
      }).then(r => r.json()).then(res => {
        if(res.success) {
          copyTextToClipboard(res.link);
          alert('分享链接已生成并复制到剪贴板:\n' + res.link);
          document.getElementById('shareLink').textContent = '分享链接: ' + res.link;
        }
        else alert(res.error);
        menu.remove();
      });
    };
    menu.appendChild(shareItem);
  }

  document.body.appendChild(menu);
}

// 把文本复制到剪贴板 (兼容性较好)
function copyTextToClipboard(text) {
  if(navigator.clipboard) {
    navigator.clipboard.writeText(text).catch(() => fallbackCopy(text));
  } else {
    fallbackCopy(text);
  }
}
function fallbackCopy(text) {
  const textarea = document.createElement('textarea');
  textarea.value = text;
  document.body.appendChild(textarea);
  textarea.select();
  try { document.execCommand('copy'); }
  catch {}
  textarea.remove();
}

// 删除操作, 删除文件或递归目录
function doDelete(node) {
  if(!confirm(`确定删除 "${node.name}" ? 目录支持递归删除`)) return;
  fetch('/api/delete', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body: `path=${encodeURIComponent(node.path)}`
  }).then(r => r.json()).then(res => {
    if(res.success) fetchTree();
    else alert(res.error);
  });
}

// 重命名
function doRename(node) {
  const newName = prompt('输入新名称', node.name);
  if(!newName) return;
  fetch('/api/rename', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:`path=${encodeURIComponent(node.path)}&new_name=${encodeURIComponent(newName)}`
  }).then(r => r.json()).then(res => {
    if(res.success) fetchTree();
    else alert(res.error);
  });
}

// 移动
function doMove(node) {
  const dest = prompt('输入目标目录（相对路径）', '');
  if(dest===null) return;
  fetch('/api/move', {
    method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body:`src=${encodeURIComponent(node.path)}&dst=${encodeURIComponent(dest)}`
  }).then(r => r.json()).then(res => {
    if(res.success) fetchTree();
    else alert(res.error);
  });
}

// 上传文件
document.getElementById('uploadForm').onsubmit = e => {
  e.preventDefault();
  const formData = new FormData(e.target);
  fetch('/api/upload', {method:'POST', body:formData})
    .then(r => r.json()).then(res => {
      if(res.success){
        fetchTree();
        e.target.reset();
      } else {
        alert(res.error);
      }
    });
};

fetchTree();

document.body.addEventListener('click', () => {
  const menu = document.getElementById('ctxMenu');
  if(menu) menu.remove();
});
</script>
{% endblock %}
''',

    "my_shares": '''
{% extends "base" %}
{% block title %}我的分享{% endblock %}
{% block content %}
<h2>我的分享目录</h2>
{% if shares %}
<ul>
  {% for s in shares %}
    <li>
      <strong>{{ s.path or "/" }}</strong>
      — <a href="{{ s.link }}" target="_blank">访问链接</a>
    </li>
  {% endfor %}
</ul>
{% else %}
<p>你还没有分享任何目录。</p>
{% endif %}
{% endblock %}
''',

    "shared_view": '''
{% extends "base" %}
{% block title %}{{ username }} 的分享：{{ base_path or "/" }}{% endblock %}
{% block content %}
<h2>公开分享目录：{{ base_path or "/" }}</h2>
<div id="treeContainer" style="user-select:none;"></div>
{% endblock %}
{% block scripts %}
<script>
const token = "{{ token }}";
let currentPath = "{{ base_path or '' }}";

function fetchTree(path=currentPath) {
  fetch(`/s/${token}/api/tree?path=${encodeURIComponent(path)}`)
    .then(r=>r.json())
    .then(res=>{
      if(res.success) renderTree(res.tree);
      else alert(res.error);
    });
}

function renderTree(nodes, container=document.getElementById('treeContainer')){
  container.innerHTML = "";
  const ul = document.createElement('ul');
  container.appendChild(ul);
  nodes.forEach(node=>{
    const li = document.createElement('li');
    li.textContent = node.name;
    li.dataset.path = node.path;
    li.className = node.type;
    if(node.type === "dir"){
      li.onclick = () => {
        currentPath = node.path;
        fetchTree(node.path);
      };
      if(node.children && node.children.length){
        const div = document.createElement('div');
        renderTree(node.children, div);
        li.appendChild(div);
      }
    } else {
      li.onclick = () => {
        location.href = `/s/${token}/api/download?path=${encodeURIComponent(node.path)}`;
      };
    }
    ul.appendChild(li);
  });
}

fetchTree();

</script>
{% endblock %}
'''
}

# === 路由实现 ===

@app.route('/')
@login_required
def index():
    return render_template_string(templates['index'], error=None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        if not username or not password:
            return render_template_string(templates['register'], error="用户名密码不能为空")
        if User.query.filter_by(username=username).first():
            return render_template_string(templates['register'], error="用户名已存在")
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        # 创建用户目录
        os.makedirs(user_base_dir(username), exist_ok=True)
        return redirect(url_for('login'))
    return render_template_string(templates['register'], error=None)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method=='POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','').strip()
        user = User.query.filter_by(username=username).first()
        if user and user.password==password:
            login_user(user)
            return redirect(url_for('index'))
        return render_template_string(templates['login'], error="用户名或密码错误")
    return render_template_string(templates['login'], error=None)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/api/tree')
@login_required
def api_tree():
    path = request.args.get('path','').strip('/')
    base = user_base_dir(current_user.username)
    try:
        tree = get_file_tree(base, path)
        return jsonify(success=True, tree=tree)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    if 'file' not in request.files:
        return jsonify(success=False, error="没有上传文件")
    file = request.files['file']
    if file.filename == '':
        return jsonify(success=False, error="没有选择文件")
    if not allowed_file(file.filename):
        return jsonify(success=False, error="文件格式不支持")
    path = request.form.get('path','').strip('/')
    base = user_base_dir(current_user.username)
    try:
        save_dir = safe_join(base, path)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        filename = secure_filename(file.filename)
        file.save(os.path.join(save_dir, filename))
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route('/api/delete', methods=['POST'])
@login_required
def api_delete():
    path = request.form.get('path','').strip('/')
    if not path:
        return jsonify(success=False, error="缺少路径参数")
    base = user_base_dir(current_user.username)
    try:
        target = safe_join(base, path)
        if not os.path.exists(target):
            return jsonify(success=False, error="文件或目录不存在")
        # 文件直接删除，目录执行递归删除
        if os.path.isfile(target):
            os.remove(target)
        else:
            shutil.rmtree(target)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route('/api/rename', methods=['POST'])
@login_required
def api_rename():
    old_path = request.form.get('path', '').strip('/')
    new_name = request.form.get('new_name', '').strip()
    if not old_path or not new_name:
        return jsonify(success=False, error="参数缺失")
    base = user_base_dir(current_user.username)
    try:
        old_abs = safe_join(base, old_path)
        if not os.path.exists(old_abs):
            return jsonify(success=False, error="原文件不存在")
        new_abs = os.path.abspath(os.path.join(os.path.dirname(old_abs), secure_filename(new_name)))
        if not new_abs.startswith(os.path.abspath(base)):
            return jsonify(success=False, error="新名称无效")
        os.rename(old_abs, new_abs)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route('/api/move', methods=['POST'])
@login_required
def api_move():
    src = request.form.get('src', '').strip('/')
    dst = request.form.get('dst', '').strip('/')
    if not src or not dst:
        return jsonify(success=False, error="缺少路径")
    base = user_base_dir(current_user.username)
    try:
        src_abs = safe_join(base, src)
        dst_abs = safe_join(base, dst)
        if not os.path.exists(src_abs):
            return jsonify(success=False, error="源文件不存在")
        # 若目标是目录，则移动到目录下
        if os.path.isdir(dst_abs):
            dst_abs = os.path.join(dst_abs, os.path.basename(src_abs))
        os.rename(src_abs, dst_abs)
        return jsonify(success=True)
    except Exception as e:
        return jsonify(success=False, error=str(e))

@app.route('/api/download')
@login_required
def api_download():
    path = request.args.get('path', '').strip('/')
    if not path:
        abort(404)
    base = user_base_dir(current_user.username)
    try:
        full_path = safe_join(base, path)
        if not os.path.isfile(full_path):
            abort(404)
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        return send_from_directory(directory, filename, as_attachment=True)
    except:
        abort(404)

# 分享接口，生成唯一token
@app.route('/api/share', methods=['POST'])
@login_required
def api_share():
    path = request.form.get('path', '').strip('/')
    if not path:
        return jsonify(success=False, error="缺少路径参数")
    base = user_base_dir(current_user.username)
    try:
        abs_path = safe_join(base, path)
        if not os.path.isdir(abs_path):
            return jsonify(success=False, error="必须是目录")
        share = Share.query.filter_by(owner=current_user, relative_path=path).first()
        if not share:
            share = Share(owner=current_user, relative_path=path)
            db.session.add(share)
            db.session.commit()
        return jsonify(success=True, link=url_for('shared_view', token=share.token, _external=True))
    except Exception as e:
        return jsonify(success=False, error=str(e))

# 取消分享功能（可自行添加调用）
@app.route('/api/unshare', methods=['POST'])
@login_required
def api_unshare():
    path = request.form.get('path','').strip('/')
    if not path:
        return jsonify(success=False, error="缺少参数")
    share = Share.query.filter_by(owner=current_user, relative_path=path).first()
    if not share:
        return jsonify(success=False, error="分享不存在")
    db.session.delete(share)
    db.session.commit()
    return jsonify(success=True)

@app.route('/my_shares')
@login_required
def my_shares():
    shares = Share.query.filter_by(owner=current_user).all()
    shares_info = [{"path": "/" + s.relative_path, "link": url_for('shared_view', token=s.token, _external=True)} for s in shares]
    return render_template_string(templates['my_shares'], shares=shares_info, error=None)

# 访问分享视图
@app.route('/s/<token>')
def shared_view(token):
    share = Share.query.filter_by(token=token).first_or_404()
    user = share.owner
    base_path = share.relative_path
    return render_template_string(templates['shared_view'], username=user.username, token=token, base_path=base_path)

# 分享视图访问共享目录的文件树
@app.route('/s/<token>/api/tree')
def shared_view_api_tree(token):
    share = Share.query.filter_by(token=token).first_or_404()
    rel_path = request.args.get('path', '').strip('/')
    user_base = user_base_dir(share.owner.username)
    share_base = safe_join(user_base, share.relative_path)
    try:
        tree = get_file_tree(share_base, rel_path)
        return jsonify(success=True, tree=tree)
    except Exception as e:
        return jsonify(success=False, error=str(e))

# 分享视图下载文件
@app.route('/s/<token>/api/download')
def shared_view_api_download(token):
    share = Share.query.filter_by(token=token).first_or_404()
    path = request.args.get('path', '').strip('/')
    user_base = user_base_dir(share.owner.username)
    share_base = safe_join(user_base, share.relative_path)
    try:
        file_path = safe_join(share_base, path)
        if not os.path.isfile(file_path):
            abort(404)
        directory = os.path.dirname(file_path)
        filename = os.path.basename(file_path)
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception:
        abort(404)

if __name__=='__main__':
    app.run(debug=True)
