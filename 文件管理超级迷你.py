# app.py
import os
import shutil
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string
from werkzeug.utils import secure_filename
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

# ———— 配置 ————
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
MAX_CONTENT_LENGTH = 200 * 1024 * 1024  # 最大允许上传 200MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# ———— 简单 HTTP Basic Auth ————
auth = HTTPBasicAuth()
users = {
    "admin": generate_password_hash("mypassword")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users[username], password):
        return username


# ———— 工具函数 ————

def is_safe_path(basedir, path):
    # 防止目录穿越
    return os.path.realpath(path).startswith(os.path.realpath(basedir))

def secure_path(rel_path):
    # 先按 '/' 分割，再对每段做 secure_filename，丢弃空段和 '..'
    parts = []
    for part in rel_path.replace('\\', '/').split('/'):
        if part and part != '..':
            parts.append(secure_filename(part))
    return os.path.join(*parts) if parts else ''

def get_tree(rel_path=''):
    """返回该相对目录下的条目列表，包含元信息"""
    abs_dir = os.path.join(UPLOAD_FOLDER, secure_path(rel_path))
    result = []
    try:
        for name in sorted(os.listdir(abs_dir)):
            abs_path = os.path.join(abs_dir, name)
            rel = os.path.join(rel_path, name).replace('\\', '/')
            stat = os.stat(abs_path)
            result.append({
                'name': name,
                'path': rel,
                'type': 'folder' if os.path.isdir(abs_path) else 'file',
                'size': stat.st_size,
                'mtime': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            })
    except PermissionError:
        pass
    return result


# ———— 路由 ————

@app.route('/')
@auth.login_required
def index():
    # 用 render_template_string 一次性内嵌前端页面
    return render_template_string('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>Flask 文件管理器</title>
  <style>
    body { font-family: sans-serif; margin: 20px; }
    .breadcrumb { margin-bottom: 10px; }
    .breadcrumb span { cursor: pointer; color: blue; }
    .breadcrumb span:hover { text-decoration: underline; }
    #file-table { width: 100%; border-collapse: collapse; }
    #file-table th, #file-table td { border: 1px solid #ddd; padding: 8px; }
    #file-table th { background: #f4f4f4; }
    .actions button { margin-right: 5px; }
  </style>
</head>
<body>
  <h2>Flask 文件管理器</h2>
  <div class="breadcrumb" id="breadcrumb"></div>
  <div style="margin-bottom:10px;">
    <input type="file" id="file-input" multiple>
    <button id="btn-upload">上传</button>
    <button id="btn-newfolder">新建文件夹</button>
  </div>
  <table id="file-table">
    <thead>
      <tr><th>名称</th><th>类型</th><th>大小</th><th>最后修改</th><th>操作</th></tr>
    </thead>
    <tbody id="file-body"></tbody>
  </table>
<script>
let currentPath = '';

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  let k = bytes / 1024;
  if (k < 1024) return k.toFixed(2) + ' KB';
  let m = k / 1024;
  return m.toFixed(2) + ' MB';
}

function renderBreadcrumb() {
  const bc = document.getElementById('breadcrumb');
  bc.innerHTML = '';
  let parts = currentPath ? currentPath.split('/') : [];
  let sofar = '';
  let root = document.createElement('span');
  root.textContent = '根目录';
  root.onclick = ()=>{ currentPath=''; loadTree(); };
  bc.appendChild(root);
  parts.forEach((p,i)=>{
    bc.appendChild(document.createTextNode(' / '));
    sofar += (i>0?'/':'') + p;
    let sp = document.createElement('span');
    sp.textContent = p;
    sp.onclick = ()=>{ currentPath=sofar; loadTree(); };
    bc.appendChild(sp);
  });
}

async function loadTree() {
  renderBreadcrumb();
  let res = await fetch(`/api/tree?path=${encodeURIComponent(currentPath)}`);
  let { tree } = await res.json();
  let tb = document.getElementById('file-body');
  tb.innerHTML = '';
  tree.forEach(item=>{
    let tr = document.createElement('tr');
    // 名称
    let tdName = document.createElement('td');
    if(item.type==='folder'){
      let sp = document.createElement('span');
      sp.textContent = item.name;
      sp.style.color='blue'; sp.style.cursor='pointer';
      sp.onclick = ()=>{
        currentPath = item.path;
        loadTree();
      };
      tdName.appendChild(sp);
    } else {
      let a = document.createElement('a');
      a.href = '/download/' + encodeURIComponent(item.path);
      a.textContent = item.name;
      tdName.appendChild(a);
    }
    // 类型、大小、时间
    let tdType = document.createElement('td'); tdType.textContent=item.type;
    let tdSize = document.createElement('td'); tdSize.textContent = item.type==='file'?formatSize(item.size):'-';
    let tdM = document.createElement('td'); tdM.textContent=item.mtime;
    // 操作
    let tdAct = document.createElement('td'); tdAct.className='actions';
    let bR = document.createElement('button'); bR.textContent='重命名';
    bR.onclick = ()=>renameItem(item);
    let bD = document.createElement('button'); bD.textContent='删除';
    bD.onclick = ()=>deleteItem(item);
    tdAct.append(bR,bD);

    tr.append(tdName, tdType, tdSize, tdM, tdAct);
    tb.appendChild(tr);
  });
}

async function uploadFiles() {
  let inp = document.getElementById('file-input');
  if (!inp.files.length){ alert('请选择文件'); return; }
  let fd = new FormData();
  for(let f of inp.files) fd.append('files', f);
  fd.append('path', currentPath);
  let res = await fetch('/api/upload', { method:'POST', body: fd });
  let d = await res.json();
  alert(d.message);
  if(d.success) loadTree();
}

async function makeFolder() {
  let name = prompt('新建文件夹名称：');
  if(!name) return;
  let res = await fetch('/api/mkdir', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path:currentPath, name})
  });
  let d = await res.json();
  alert(d.message);
  if(d.success) loadTree();
}

async function renameItem(item) {
  let nn = prompt('新名称：', item.name);
  if(!nn) return;
  let res = await fetch('/api/rename', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({src:item.path, new_name: nn})
  });
  let d = await res.json();
  alert(d.message);
  if(d.success) loadTree();
}

async function deleteItem(item) {
  if(!confirm(`确认删除 "${item.name}"？`)) return;
  let res = await fetch('/api/delete', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: item.path})
  });
  let d = await res.json();
  alert(d.message);
  if(d.success) loadTree();
}

document.getElementById('btn-upload').onclick = uploadFiles;
document.getElementById('btn-newfolder').onclick = makeFolder;
window.onload = loadTree;
</script>
</body>
</html>
    ''')

@app.route('/api/tree')
@auth.login_required
def api_tree():
    rel = request.args.get('path', '')
    return jsonify(tree=get_tree(rel))

@app.route('/api/upload', methods=['POST'])
@auth.login_required
def api_upload():
    rel = request.form.get('path', '')
    target = os.path.join(UPLOAD_FOLDER, secure_path(rel))
    if not is_safe_path(UPLOAD_FOLDER, target):
        return jsonify(success=False, message="非法路径"), 400
    os.makedirs(target, exist_ok=True)
    files = request.files.getlist('files')
    if not files:
        return jsonify(success=False, message="未检测到文件"), 400
    saved = []
    for f in files:
        fn = secure_filename(f.filename)
        if not fn:
            continue
        dst = os.path.join(target, fn)
        if os.path.exists(dst):
            continue
        f.save(dst)
        saved.append(fn)
    msg = f"成功上传 {len(saved)} 个文件"
    return jsonify(success=True, message=msg, saved=saved)

@app.route('/api/mkdir', methods=['POST'])
@auth.login_required
def api_mkdir():
    data = request.get_json() or {}
    rel = data.get('path','')
    name= secure_filename(data.get('name',''))
    if not name:
        return jsonify(success=False, message="名称非法"), 400
    target = os.path.join(UPLOAD_FOLDER, secure_path(rel), name)
    if not is_safe_path(UPLOAD_FOLDER, target):
        return jsonify(success=False, message="非法路径"),400
    if os.path.exists(target):
        return jsonify(success=False, message="已存在"),400
    try:
        os.makedirs(target)
        return jsonify(success=True, message="新建成功")
    except Exception as e:
        return jsonify(success=False, message=f"创建失败：{e}"),500

@app.route('/api/rename', methods=['POST'])
@auth.login_required
def api_rename():
    data = request.get_json() or {}
    src = secure_path(data.get('src',''))
    newn = secure_filename(data.get('new_name',''))
    if not src or not newn:
        return jsonify(success=False, message="参数错误"),400
    abs_src = os.path.join(UPLOAD_FOLDER, src)
    abs_dst = os.path.join(os.path.dirname(abs_src), newn)
    if not is_safe_path(UPLOAD_FOLDER, abs_src) or not os.path.exists(abs_src):
        return jsonify(success=False, message="源不存在"),400
    if os.path.exists(abs_dst):
        return jsonify(success=False, message="目标已存在"),400
    try:
        os.rename(abs_src, abs_dst)
        return jsonify(success=True, message="重命名成功")
    except Exception as e:
        return jsonify(success=False, message=f"失败：{e}"),500

@app.route('/api/delete', methods=['POST'])
@auth.login_required
def api_delete():
    data = request.get_json() or {}
    rel = secure_path(data.get('path',''))
    abs_p = os.path.join(UPLOAD_FOLDER, rel)
    if not is_safe_path(UPLOAD_FOLDER, abs_p) or not os.path.exists(abs_p):
        return jsonify(success=False, message="不存在"),400
    try:
        if os.path.isdir(abs_p):
            shutil.rmtree(abs_p)
        else:
            os.remove(abs_p)
        return jsonify(success=True, message="删除成功")
    except Exception as e:
        return jsonify(success=False, message=f"失败：{e}"),500

@app.route('/download/<path:filepath>')
@auth.login_required
def download_file(filepath):
    rel = secure_path(filepath)
    abs_fp = os.path.join(UPLOAD_FOLDER, rel)
    if not is_safe_path(UPLOAD_FOLDER, abs_fp) or not os.path.isfile(abs_fp):
        abort(404)
    return send_from_directory(os.path.dirname(abs_fp), os.path.basename(abs_fp), as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
