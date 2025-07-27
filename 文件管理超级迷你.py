import os
import shutil
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string
from werkzeug.utils import secure_filename
from flask_httpauth import HTTPBasicAuth

app = Flask(__name__)
auth = HTTPBasicAuth()

# 简单用户名密码（生产环境请换更安全方案）
USER_DATA = {"admin": "123456"}
BASE_DIR = 'uploads'
os.makedirs(BASE_DIR, exist_ok=True)

@auth.verify_password
def verify(username, password):
    return USER_DATA.get(username) == password

def is_safe_path(basedir, path, follow_symlinks=True):
    if follow_symlinks:
        return os.path.realpath(path).startswith(os.path.realpath(basedir))
    return os.path.abspath(path).startswith(os.path.abspath(basedir))

def secure_path(path):
    """ 去掉 .. 等不安全成分 """
    parts = []
    for p in path.replace('\\','/').split('/'):
        if p in ('', '.', '..'):
            continue
        parts.append(p)
    return os.path.join(*parts) if parts else ''

def get_tree(path):
    """ 递归读目录 """
    abs_p = os.path.join(BASE_DIR, path)
    if not os.path.isdir(abs_p):
        return []
    items = []
    for name in sorted(os.listdir(abs_p), key=lambda x: x.lower()):
        node = {'name': name}
        child = os.path.join(path, name)
        abs_child = os.path.join(BASE_DIR, child)
        if os.path.isdir(abs_child):
            node['type'] = 'folder'
            node['children'] = get_tree(child)
        else:
            node['type'] = 'file'
        items.append(node)
    return items

@app.route('/')
@auth.login_required
def index():
    # 用 Bootstrap 4 + 少量自定义 CSS
    return render_template_string('''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>文件管理后台</title>
  <link
    href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css"
    rel="stylesheet">
  <style>
    .tree ul { list-style: none; padding-left: 1rem; }
    .tree li { position: relative; padding: .25rem 0; }
    .tree li .name { cursor: pointer; }
    .tree li.folder > .name::before {
      content: "\\f07b"; /* fa-folder */
      font-family: "Font Awesome 5 Free"; font-weight: 900;
      margin-right: .5rem;
    }
    .tree li.file > .name::before {
      content: "\\f15b"; /* fa-file */
      font-family: "Font Awesome 5 Free"; font-weight: 900;
      margin-right: .5rem;
    }
    .selected { background-color: #e2f0d9; }
    /* 右键菜单 */
    #contextMenu {
      position: absolute; z-index: 2000; display: none;
      background: #fff; border: 1px solid #ccc; 
      box-shadow: 2px 2px 6px rgba(0,0,0,0.15);
    }
    #contextMenu div {
      padding: .5rem 1rem; cursor: pointer;
    }
    #contextMenu div:hover { background: #f1f1f1; }
  </style>
  <script
    src="https://kit.fontawesome.com/a2e0e6f3ef.js" crossorigin="anonymous">
  </script>
</head>
<body class="p-4">
  <h2>文件管理后台</h2>
  <div class="mb-2">
    <strong>当前路径:</strong> <span id="currentPath">/</span>
  </div>
  <div class="tree border p-3" id="treeContainer" style="height:400px; overflow:auto;">
    <!-- 目录树 渲染到这里 -->
  </div>

  <div class="mt-3">
    <div class="form-inline">
      <input type="file" id="fileInput" multiple class="form-control-file">
      <button class="btn btn-primary ml-2" onclick="uploadFiles()">上传</button>
    </div>
    <div class="form-inline mt-2">
      <input type="text" id="newFolderName" placeholder="新文件夹名称"
             class="form-control">
      <button class="btn btn-secondary ml-2" onclick="createFolder()">
        创建文件夹
      </button>
    </div>
  </div>

  <div class="mt-3">
    <div id="message" class="text-success"></div>
    <div id="error" class="text-danger"></div>
  </div>

  <!-- 右键菜单 -->
  <div id="contextMenu">
    <div onclick="doDownload()"><i class="fas fa-download"></i> 下载</div>
    <div onclick="doRename()"><i class="fas fa-edit"></i> 重命名</div>
    <div onclick="doDelete()"><i class="fas fa-trash"></i> 删除</div>
  </div>

<script>
let currentPath = '';
let selected = null;

function clearMsg() {
  document.getElementById('message').textContent = '';
  document.getElementById('error').textContent = '';
}
function showMsg(msg) {
  clearMsg();
  document.getElementById('message').textContent = msg;
}
function showErr(msg) {
  clearMsg();
  document.getElementById('error').textContent = msg;
}

// 拉取目录树
function fetchTree(path='') {
  fetch(`/api/tree?path=${encodeURIComponent(path)}`)
    .then(r=>r.json()).then(data=>{
      if(data.error) return showErr(data.error);
      currentPath = path;
      document.getElementById('currentPath').textContent = '/' + path;
      selected = null;
      buildTree(data.tree, document.getElementById('treeContainer'));
    })
    .catch(()=>showErr('获取目录树失败'));
}

// 生成树形DOM
function buildTree(tree, container) {
  container.innerHTML = '';
  const ul = document.createElement('ul');
  tree.forEach(item => {
    const li = document.createElement('li');
    li.classList.add(item.type);
    // 展开/折叠处理
    if(item.type==='folder') {
      li.classList.add('collapsed');
    }
    const span = document.createElement('span');
    span.textContent = item.name;
    span.className = 'name';

    // 单击展示子目录或下载
    span.onclick = e => {
      e.stopPropagation();
      if(item.type==='folder') {
        let next = currentPath? currentPath + '/' + item.name : item.name;
        fetchTree(next);
      } else {
        // 点击文件直接下载
        let fp = currentPath? currentPath + '/' + item.name : item.name;
        window.location.href = '/download/' + encodeURIComponent(fp);
      }
    };

    // 右键菜单
    li.oncontextmenu = e => {
      e.preventDefault(); e.stopPropagation();
      selectNode(li, item);
      showContextMenu(e.pageX, e.pageY);
    };

    // 拖拽：移动
    li.draggable = true;
    li.ondragstart = e => {
      e.dataTransfer.setData('text/plain', item.name);
      e.dataTransfer.setData('source', currentPath);
    };
    li.ondragover = e => {
      if(item.type==='folder') e.preventDefault();
    };
    li.ondrop = e => {
      e.preventDefault();
      let name = e.dataTransfer.getData('text/plain');
      let src = e.dataTransfer.getData('source');
      let from = src? src + '/' + name : name;
      let to   = currentPath? currentPath + '/' + item.name : item.name;
      moveItem(from, to);
    };

    li.appendChild(span);
    ul.appendChild(li);
  });
  container.appendChild(ul);
}

function selectNode(li, item) {
  if(selected && selected.li) selected.li.classList.remove('selected');
  li.classList.add('selected');
  selected = { li, item };
}

const menu = document.getElementById('contextMenu');
function showContextMenu(x,y) {
  menu.style.left = x+'px';
  menu.style.top  = y+'px';
  menu.style.display = 'block';
}
window.onclick = () => menu.style.display = 'none';

// 右键：下载
function doDownload() {
  if(!selected || selected.item.type!=='file') return showErr('只能下载文件');
  let fp = currentPath? currentPath + '/' + selected.item.name : selected.item.name;
  window.location.href = '/download/' + encodeURIComponent(fp);
}

// 右键：删除
function doDelete() {
  if(!selected) return;
  if(!confirm('确认删除？不可恢复！')) return;
  let p = currentPath? currentPath + '/' + selected.item.name : selected.item.name;
  fetch('/api/delete', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: p})
  })
  .then(r=>r.json()).then(r=>{
    if(r.success) { showMsg('删除成功'); fetchTree(currentPath); }
    else showErr(r.message);
  });
}

// 右键：重命名
function doRename() {
  if(!selected) return;
  let oldName = selected.item.name;
  let newName = prompt('新名称：', oldName);
  if(!newName || newName===oldName) return;
  let p = currentPath? currentPath + '/' + oldName : oldName;
  fetch('/api/rename', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: p, new_name: newName})
  })
  .then(r=>r.json()).then(r=>{
    if(r.success) { showMsg('重命名成功'); fetchTree(currentPath); }
    else showErr(r.message);
  });
}

// 上传
function uploadFiles() {
  const files = document.getElementById('fileInput').files;
  if(files.length===0) return showErr('请选择文件');
  let form = new FormData();
  form.append('path', currentPath);
  for(let f of files) form.append('files', f);
  fetch('/api/upload', {method:'POST', body: form})
    .then(r=>r.json()).then(r=>{
      if(r.success) { showMsg('上传成功'); fetchTree(currentPath); }
      else showErr(r.message);
    });
}

// 新建文件夹
function createFolder() {
  let name = document.getElementById('newFolderName').value.trim();
  if(!name) return showErr('请输入文件夹名称');
  fetch('/api/mkdir', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path: currentPath, name})
  })
  .then(r=>r.json()).then(r=>{
    if(r.success) { showMsg('创建成功'); fetchTree(currentPath); }
    else showErr(r.message);
  });
}

// 拖拽移动
function moveItem(src, dst) {
  fetch('/api/move', {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({src, dst})
  })
  .then(r=>r.json()).then(r=>{
    if(r.success) { showMsg('移动成功'); fetchTree(currentPath); }
    else showErr(r.message);
  });
}

// 首次加载
window.onload = ()=>fetchTree('');
</script>
</body>
</html>
    ''')

@app.route('/api/tree')
@auth.login_required
def api_tree():
    path = secure_path(request.args.get('path',''))
    abs_p = os.path.join(BASE_DIR, path)
    if not is_safe_path(BASE_DIR, abs_p) or not os.path.isdir(abs_p):
        return jsonify(tree=[], error='非法目录')
    return jsonify(tree=get_tree(path))

@app.route('/api/upload', methods=['POST'])
@auth.login_required
def api_upload():
    path = secure_path(request.form.get('path',''))
    abs_dir = os.path.join(BASE_DIR, path)
    if not is_safe_path(BASE_DIR, abs_dir) or not os.path.isdir(abs_dir):
        return jsonify(success=False, message='非法目录')
    files = request.files.getlist('files')
    if not files:
        return jsonify(success=False, message='没有文件')
    for f in files:
        fn = secure_filename(f.filename)
        if fn:
            f.save(os.path.join(abs_dir, fn))
    return jsonify(success=True, message='上传成功')

@app.route('/api/mkdir', methods=['POST'])
@auth.login_required
def api_mkdir():
    data = request.get_json()
    path = secure_path(data.get('path',''))
    name = data.get('name','').strip()
    if not name:
        return jsonify(success=False, message='名称不能为空')
    abs_dir = os.path.join(BASE_DIR, path)
    if not is_safe_path(BASE_DIR, abs_dir) or not os.path.isdir(abs_dir):
        return jsonify(success=False, message='非法目录')
    newp = os.path.join(abs_dir, secure_filename(name))
    if os.path.exists(newp):
        return jsonify(success=False, message='已存在同名条目')
    try:
        os.makedirs(newp)
        return jsonify(success=True, message='创建成功')
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/download/<path:filename>')
@auth.login_required
def download(filename):
    sp = secure_path(filename)
    abs_f = os.path.join(BASE_DIR, sp)
    if not is_safe_path(BASE_DIR, abs_f) or not os.path.isfile(abs_f):
        abort(404)
    d = os.path.dirname(abs_f)
    f = os.path.basename(abs_f)
    return send_from_directory(d, f, as_attachment=True)

@app.route('/api/rename', methods=['POST'])
@auth.login_required
def api_rename():
    data = request.get_json()
    path = secure_path(data.get('path',''))
    new_name = data.get('new_name','').strip()
    if not new_name:
        return jsonify(success=False, message='新名称不能为空')
    abs_old = os.path.join(BASE_DIR, path)
    if not is_safe_path(BASE_DIR, abs_old) or not os.path.exists(abs_old):
        return jsonify(success=False, message='源不存在')
    abs_new = os.path.join(os.path.dirname(abs_old), secure_filename(new_name))
    if os.path.exists(abs_new):
        return jsonify(success=False, message='目标已存在')
    try:
        os.rename(abs_old, abs_new)
        return jsonify(success=True, message='重命名成功')
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/api/delete', methods=['POST'])
@auth.login_required
def api_delete():
    data = request.get_json()
    path = secure_path(data.get('path',''))
    abs_p = os.path.join(BASE_DIR, path)
    if not is_safe_path(BASE_DIR, abs_p) or not os.path.exists(abs_p):
        return jsonify(success=False, message='不存在')
    try:
        if os.path.isfile(abs_p):
            os.remove(abs_p)
        else:
            shutil.rmtree(abs_p)
        return jsonify(success=True, message='删除成功')
    except Exception as e:
        return jsonify(success=False, message=str(e))

@app.route('/api/move', methods=['POST'])
@auth.login_required
def api_move():
    data = request.get_json()
    src = secure_path(data.get('src',''))
    dst = secure_path(data.get('dst',''))
    abs_src = os.path.join(BASE_DIR, src)
    abs_dst = os.path.join(BASE_DIR, dst)
    if not os.path.exists(abs_src):
        return jsonify(success=False, message='源不存在')
    if not os.path.isdir(abs_dst):
        return jsonify(success=False, message='目标不是文件夹')
    target = os.path.join(abs_dst, os.path.basename(abs_src))
    if os.path.exists(target):
        return jsonify(success=False, message='目标已存在同名条目')
    try:
        shutil.move(abs_src, target)
        return jsonify(success=True, message='移动成功')
    except Exception as e:
        return jsonify(success=False, message=str(e))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
