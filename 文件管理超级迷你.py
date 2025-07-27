import os
import shutil
from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string
from werkzeug.utils import secure_filename
from flask_httpauth import HTTPBasicAuth

app = Flask(__name__)
auth = HTTPBasicAuth()

# 简单用户名密码，建议生产环境换成安全方案
USER_DATA = {
    "admin": "123456"
}

BASE_DIR = 'uploads'
if not os.path.exists(BASE_DIR):
    os.makedirs(BASE_DIR)

@auth.verify_password
def verify(username, password):
    if not username or not password:
        return False
    if USER_DATA.get(username) == password:
        return True
    return False

def is_safe_path(basedir, path, follow_symlinks=True):
    if follow_symlinks:
        return os.path.realpath(path).startswith(os.path.realpath(basedir))
    return os.path.abspath(path).startswith(os.path.abspath(basedir))

def secure_path(path):
    '''规范化路径，防止路径穿越'''
    if not path:
        return ''
    parts = []
    for part in path.split('/'):
        if part.strip() in ('', '.', '..'):
            continue
        parts.append(part)
    return os.path.join(*parts) if parts else ''

def get_tree(path):
    '''递归获取目录结构'''
    abs_path = os.path.join(BASE_DIR, path)
    if not os.path.isdir(abs_path):
        return []
    data = []
    try:
        for item in os.listdir(abs_path):
            abs_item = os.path.join(abs_path, item)
            node = {"name": item}
            if os.path.isdir(abs_item):
                node['type'] = 'folder'
                node['children'] = get_tree(os.path.join(path, item))
            else:
                node['type'] = 'file'
            data.append(node)
        return data
    except:
        return []

@app.route('/')
@auth.login_required
def index():
    '''前端简单页面'''
    # 前端HTML包含了最基本的文件管理功能演示
    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>文件管理后台</title>
    <style>
        body { font-family: Arial; margin: 20px; }
        ul { list-style-type:none; }
        li.folder > span { font-weight: bold; cursor: pointer; }
        li.file { margin-left: 20px; }
        #uploadForm { margin-top: 10px; }
        #message { margin-top: 10px; color: green; }
        #error { margin-top: 10px; color: red; }
    </style>
</head>
<body>
<h1>文件管理后台</h1>

<div>
    <strong>当前路径: </strong><span id="currentPath"></span>
</div>

<div id="tree"></div>

<div id="uploadForm">
    <input type="file" id="fileInput" multiple>
    <button onclick="uploadFiles()">上传</button>
</div>

<div style="margin-top:10px;">
    <input type="text" placeholder="新文件夹名称" id="newFolderName">
    <button onclick="createFolder()">创建文件夹</button>
</div>

<div style="margin-top:10px;">
    <input type="text" placeholder="重命名为" id="renameInput">
    <button onclick="rename()">重命名</button>
</div>

<div style="margin-top:10px;">
    <input type="text" placeholder="移动到 (目标文件夹路径)" id="moveInput">
    <button onclick="move()">移动</button>
</div>

<div style="margin-top:10px;">
    <button onclick="deleteItem()">删除选中文件/文件夹</button>
</div>

<p id="message"></p>
<p id="error"></p>

<script>
let currentPath = '';
let selectedItem = null;

function clearMessages() {
    document.getElementById('message').textContent = '';
    document.getElementById('error').textContent = '';
}

function showMessage(msg) {
    clearMessages();
    document.getElementById('message').textContent = msg;
}
function showError(msg) {
    clearMessages();
    document.getElementById('error').textContent = msg;
}

function fetchTree(path) {
    fetch('/api/tree?path=' + encodeURIComponent(path))
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                showError(data.error);
                return;
            }
            document.getElementById('currentPath').textContent = '/' + path;
            selectedItem = null;
            document.getElementById('renameInput').value = '';
            document.getElementById('moveInput').value = '';
            buildTree(data.tree, path);
        }).catch(() => showError('获取目录树失败'));
}

function buildTree(tree, basePath) {
    let container = document.getElementById('tree');
    container.innerHTML = '';
    let ul = document.createElement('ul');
    tree.forEach(item => {
        let li = document.createElement('li');
        let span = document.createElement('span');
        span.textContent = item.name;
        span.style.userSelect = 'none';
        if (item.type === 'folder') {
            li.className = 'folder';
            span.style.fontWeight = 'bold';
            span.style.cursor = 'pointer';

            span.onclick = () => {
                // 目录点击，切换路径
                currentPath = basePath ? basePath + '/' + item.name : item.name;
                fetchTree(currentPath);
            };
            li.appendChild(span);
            ul.appendChild(li);
        } else {
            li.className = 'file';
            li.textContent = item.name;
            ul.appendChild(li);
        }
        // 选中功能
        li.onclick = (e) => {
            e.stopPropagation();
            if(selectedItem) {
                selectedItem.style.backgroundColor = '';
            }
            selectedItem = li;
            selectedItem.style.backgroundColor = '#ddf';
            document.getElementById('renameInput').value = item.name;
        };
    });
    container.appendChild(ul);
}

function uploadFiles() {
    if (!currentPath) currentPath = '';
    let files = document.getElementById('fileInput').files;
    if (files.length === 0) {
        showError('请选择文件');
        return;
    }
    let form = new FormData();
    form.append('path', currentPath);
    for (let f of files) {
        form.append('files', f);
    }
    fetch('/api/upload', {method: 'POST', body: form})
    .then(r => r.json())
    .then(data => {
        if (data.success) {
            showMessage('上传成功');
            fetchTree(currentPath);
            document.getElementById('fileInput').value = '';
        } else {
            showError(data.message);
        }
    }).catch(() => showError('上传失败'));
}

function createFolder() {
    if (!currentPath) currentPath = '';
    let name = document.getElementById('newFolderName').value.trim();
    if (!name) {
        showError('请输入文件夹名称');
        return;
    }
    fetch('/api/mkdir', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({path: currentPath, name})
    })
    .then(r=>r.json())
    .then(data=>{
        if(data.success){
            showMessage('创建成功');
            fetchTree(currentPath);
            document.getElementById('newFolderName').value = '';
        } else {
            showError(data.message);
        }
    }).catch(() => showError('创建失败'));
}

function rename() {
    if (!selectedItem) {
        showError('请先选择文件或文件夹');
        return;
    }
    let newName = document.getElementById('renameInput').value.trim();
    if (!newName) {
        showError('请输入新的名称');
        return;
    }
    let oldName = selectedItem.textContent;
    let oldPath = currentPath ? (currentPath + '/' + oldName) : oldName;

    fetch('/api/rename', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({path: oldPath, new_name: newName})
    }).then(r=>r.json()).then(data=>{
        if(data.success){
            showMessage('重命名成功');
            fetchTree(currentPath);
        } else {
            showError(data.message);
        }
    }).catch(()=>showError('重命名失败'));
}

function deleteItem() {
    if(!selectedItem){
        showError('请先选择文件或文件夹');
        return;
    }
    if(!confirm('确定删除选中的项（文件或文件夹）吗？此操作不可撤销。')){
        return;
    }
    let name = selectedItem.textContent;
    let path = currentPath ? (currentPath + '/' + name) : name;
    fetch('/api/delete', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({path})
    }).then(r=>r.json()).then(data=>{
        if(data.success){
            showMessage('删除成功');
            selectedItem = null;
            fetchTree(currentPath);
        } else {
            showError(data.message);
        }
    }).catch(()=>showError('删除失败'));
}

function move() {
    if(!selectedItem){
        showError('请先选择文件或文件夹');
        return;
    }
    let dst = document.getElementById('moveInput').value.trim();
    if (!dst) {
        showError('请输入目标文件夹路径');
        return;
    }
    let name = selectedItem.textContent;
    let src = currentPath ? (currentPath + '/' + name) : name;

    fetch('/api/move', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({src, dst})
    }).then(r=>r.json()).then(data=>{
        if(data.success){
            showMessage('移动成功');
            selectedItem = null;
            document.getElementById('moveInput').value = '';
            fetchTree(currentPath);
        } else {
            showError(data.message);
        }
    }).catch(() => showError('移动失败'));
}

window.onload = () => {
    currentPath = '';
    fetchTree(currentPath);
};

</script>
</body>
</html>
''')

@app.route('/api/tree')
@auth.login_required
def api_tree():
    path = request.args.get('path', '')
    spath = secure_path(path)
    abs_path = os.path.join(BASE_DIR, spath)
    if not is_safe_path(BASE_DIR, abs_path) or not os.path.isdir(abs_path):
        return jsonify({'tree': [], 'error': '非法目录'})
    tree = get_tree(spath)
    return jsonify({'tree': tree})

@app.route('/api/upload', methods=['POST'])
@auth.login_required
def api_upload():
    path = request.form.get('path', '')
    spath = secure_path(path)
    abs_dir = os.path.join(BASE_DIR, spath)
    if not is_safe_path(BASE_DIR, abs_dir) or not os.path.isdir(abs_dir):
        return jsonify({'success': False, 'message': '非法目录'})
    files = request.files.getlist('files')
    if not files:
        return jsonify({'success': False, 'message': '没有文件'})
    for f in files:
        filename = secure_filename(f.filename)
        if not filename:
            continue
        f.save(os.path.join(abs_dir, filename))
    return jsonify({'success': True, 'message': '上传成功'})

@app.route('/api/mkdir', methods=['POST'])
@auth.login_required
def api_mkdir():
    data = request.get_json()
    path = data.get('path', '')
    name = data.get('name', '')
    if not name:
        return jsonify({'success': False, 'message': '名称不能为空'})
    spath = secure_path(path)
    abs_dir = os.path.join(BASE_DIR, spath)
    if not is_safe_path(BASE_DIR, abs_dir) or not os.path.isdir(abs_dir):
        return jsonify({'success': False, 'message': '非法目录'})
    new_dir = os.path.join(abs_dir, secure_filename(name))
    if os.path.exists(new_dir):
        return jsonify({'success': False, 'message': '文件夹已存在'})
    try:
        os.makedirs(new_dir)
        return jsonify({'success': True, 'message': '文件夹创建成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'创建失败：{str(e)}'})

@app.route('/download/<path:filename>')
@auth.login_required
def download(filename):
    spath = secure_path(filename)
    abs_f = os.path.join(BASE_DIR, spath)
    if not is_safe_path(BASE_DIR, abs_f) or not os.path.isfile(abs_f):
        abort(404)
    dirpath = os.path.dirname(abs_f)
    fname = os.path.basename(abs_f)
    return send_from_directory(dirpath, fname, as_attachment=True)

@app.route('/api/rename', methods=['POST'])
@auth.login_required
def api_rename():
    data = request.get_json()
    path = data.get('path', '')
    new_name = data.get('new_name', '')
    if not new_name:
        return jsonify({'success': False, 'message': '新名称不能为空'})
    spath = secure_path(path)
    abs_old = os.path.join(BASE_DIR, spath)
    if not is_safe_path(BASE_DIR, abs_old) or not os.path.exists(abs_old):
        return jsonify({'success': False, 'message': '文件/文件夹不存在'})
    new_name_safe = secure_filename(new_name)
    abs_new = os.path.join(os.path.dirname(abs_old), new_name_safe)
    if os.path.exists(abs_new):
        return jsonify({'success': False, 'message': '目标名称已存在'})
    try:
        os.rename(abs_old, abs_new)
        return jsonify({'success': True, 'message': '重命名成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'重命名失败：{str(e)}'})

@app.route('/api/delete', methods=['POST'])
@auth.login_required
def api_delete():
    data = request.get_json()
    path = data.get('path', '')
    spath = secure_path(path)
    abs_p = os.path.join(BASE_DIR, spath)
    if not is_safe_path(BASE_DIR, abs_p) or not os.path.exists(abs_p):
        return jsonify({'success': False, 'message': '文件/文件夹不存在'})
    try:
        if os.path.isfile(abs_p):
            os.remove(abs_p)
        else:
            shutil.rmtree(abs_p)
        return jsonify({'success': True, 'message': '删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'删除失败：{str(e)}'})

@app.route('/api/move', methods=['POST'])
@auth.login_required
def api_move():
    data = request.get_json()
    src = data.get('src', '')
    dst = data.get('dst', '')
    sp_src = secure_path(src)
    sp_dst = secure_path(dst)
    abs_src = os.path.join(BASE_DIR, sp_src)
    abs_dst_dir = os.path.join(BASE_DIR, sp_dst)
    if not is_safe_path(BASE_DIR, abs_src) or not os.path.exists(abs_src):
        return jsonify({'success': False, 'message': '源文件/文件夹不存在'})
    if not is_safe_path(BASE_DIR, abs_dst_dir) or not os.path.isdir(abs_dst_dir):
        return jsonify({'success': False, 'message': '目标文件夹不存在'})
    dst_name = os.path.basename(abs_src)
    abs_dst = os.path.join(abs_dst_dir, dst_name)
    if os.path.exists(abs_dst):
        return jsonify({'success': False, 'message': '目标位置已存在同名文件/文件夹'})
    try:
        shutil.move(abs_src, abs_dst)
        return jsonify({'success': True, 'message': '移动成功'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'移动失败：{str(e)}'})

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)
