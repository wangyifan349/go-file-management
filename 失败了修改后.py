# -*- coding: utf-8 -*-
"""
基于 Flask 的简易文件管理系统，支持文件浏览、上传、下载、重命名、删除、移动文件夹操作。
访问需登录认证，保证安全。
"""

import os
import shutil
from flask import Flask, request, send_from_directory, jsonify, render_template_string, abort
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

# 配置部分
ROOT_DIR = os.path.abspath('./shared')  # 共享目录（相对于脚本目录）
if not os.path.exists(ROOT_DIR):
    os.makedirs(ROOT_DIR)

# 认证用户，示例密码使用哈希存储
USERS = {
    'admin': generate_password_hash('1234'),
}

app = Flask(__name__)
auth = HTTPBasicAuth()

@auth.verify_password
def verify_password(username, password):
    if username in USERS and check_password_hash(USERS.get(username), password):
        return username
    return None

def safe_path(rel_path):
    """
    根据相对路径计算绝对路径，防止目录穿越攻击，限制路径在 ROOT_DIR 之下
    """
    safe_abspath = os.path.abspath(os.path.join(ROOT_DIR, rel_path))
    if not safe_abspath.startswith(ROOT_DIR):
        # 非法越界路径
        raise ValueError("非法路径穿越")
    return safe_abspath

def build_tree(root=ROOT_DIR, base_path=''):
    """
    递归构造文件树，返回用于前端渲染的结构体
    :param root: 当前扫描目录绝对路径
    :param base_path: root 相对于 ROOT_DIR 的相对路径
    """
    tree = []
    try:
        entries = sorted(os.listdir(root))
    except Exception:
        return tree
    for entry in entries:
        # 过滤隐藏文件和隐藏文件夹
        if entry.startswith('.'):
            continue
        abs_entry_path = os.path.join(root, entry)
        rel_entry_path = os.path.join(base_path, entry)
        if os.path.isdir(abs_entry_path):
            tree.append({
                "name": entry,
                "path": rel_entry_path.replace("\\", "/"),
                "type": "folder",
                "children": build_tree(abs_entry_path, rel_entry_path),
            })
        else:
            tree.append({
                "name": entry,
                "path": rel_entry_path.replace("\\", "/"),
                "type": "file"
            })
    return tree

@app.route('/')
@auth.login_required
def index():
    """
    主页面，返回 HTML + JS 前端代码，前端通过 API 渲染文件树并进行操作。
    """
    return render_template_string('''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>简易文件管理系统</title>
<style>
  body { font-family: Arial, sans-serif; padding: 10px; }
  h1 { text-align: center; }
  #treeContainer ul { list-style: none; padding-left: 20px; }
  #treeContainer li.folder > span.tree-item::before { content: "📁 "; }
  #treeContainer li.file > span.tree-item::before { content: "📄 "; }
  #treeContainer li.collapsed > ul { display: none; }
  span.tree-item { cursor: pointer; }
  span.tree-item.selected { background-color: #007BFF; color: white; }
  span.tree-item.dragging { opacity: 0.4; }
  span.tree-item.dragover { outline: 2px dashed #007BFF; }
  button:disabled { opacity: 0.5; cursor: not-allowed; }
  #operations { margin-top: 20px; }
  label { display: inline-block; margin-right: 10px; }
  input[type=text] { width: 200px; }
</style>
</head>
<body>
<h1>简易文件管理系统</h1>

<div>
  <div>
    <strong>文件树：</strong>
    <div id="treeContainer"></div>
  </div>

  <div id="operations">
    <div>
      <label>新建文件夹名：
        <input type="text" id="newFolderInput" placeholder="文件夹名称" />
      </label>
      <button id="createFolderBtn">新建文件夹</button>
    </div>

    <div style="margin-top:10px;">
      <form id="uploadForm" enctype="multipart/form-data">
        <label>上传文件：
          <input type="file" name="file" required />
        </label>
        <label>到文件夹（相对路径，空表示根目录）：
          <input type="text" id="uploadFolderInput" name="folder" placeholder="例如: subfolder" />
        </label>
        <button type="submit">上传</button>
      </form>
    </div>

    <div style="margin-top:10px;">
      <button id="btnDownload" disabled>下载选中文件</button>
      <button id="btnDelete" disabled>删除选中文件/文件夹</button>
      <button id="btnRename" disabled>重命名选中文件/文件夹</button>
    </div>

    <div style="margin-top:10px;">
      <strong>当前选中路径：</strong>
      <span id="selectedPath">无</span>
    </div>
  </div>
</div>

<script>
const treeContainer = document.getElementById('treeContainer');
const createFolderBtn = document.getElementById('createFolderBtn');
const newFolderInput = document.getElementById('newFolderInput');
const uploadForm = document.getElementById('uploadForm');
const uploadFolderInput = document.getElementById('uploadFolderInput');
const btnDownload = document.getElementById('btnDownload');
const btnDelete = document.getElementById('btnDelete');
const btnRename = document.getElementById('btnRename');
const selectedPathElem = document.getElementById('selectedPath');

let treeData = [];
let selectedItem = null;

function clearSelected(){
  selectedItem = null;
  selectedPathElem.textContent = '无';
  btnDownload.disabled = true;
  btnDelete.disabled = true;
  btnRename.disabled = true;
  document.querySelectorAll('#treeContainer span.selected').forEach(el=>el.classList.remove('selected'));
}

function createTreeUl(items){
  const ul = document.createElement('ul');
  for(const item of items){
    const li = document.createElement('li');
    li.classList.add(item.type);
    const span = document.createElement('span');
    span.textContent = item.name;
    span.className = 'tree-item';
    span.dataset.path = item.path;

    li.appendChild(span);

    if(item.type === 'folder'){
      span.style.cursor = 'pointer';
      // 目录点击展开/折叠
      span.onclick = e=>{
        e.stopPropagation();
        li.classList.toggle('collapsed');
      };
      li.classList.add('collapsed'); // 默认折叠

      if(item.children && item.children.length){
        li.appendChild(createTreeUl(item.children));
      }
    }

    // 选中事件
    span.addEventListener('click', e=>{
      e.stopPropagation();
      clearSelected();
      span.classList.add('selected');
      selectedItem = item;
      selectedPathElem.textContent = item.path || '';
      btnDownload.disabled = (item.type !== 'file');
      btnDelete.disabled = false;
      btnRename.disabled = false;
    });

    // 拖拽支持
    span.draggable = true;
    span.addEventListener('dragstart', dragStart);
    span.addEventListener('dragover', dragOver);
    span.addEventListener('drop', dropItem);
    span.addEventListener('dragleave', dragLeave);
    span.addEventListener('dragend', dragEnd);

    ul.appendChild(li);
  }
  return ul;
}

// 拖拽相关变量
let dragSrcSpan = null;

function dragStart(e){
  dragSrcSpan = e.target;
  e.dataTransfer.effectAllowed = 'move';
  e.dataTransfer.setData('text/plain', dragSrcSpan.dataset.path);
  dragSrcSpan.classList.add('dragging');
}

function dragOver(e){
  e.preventDefault();
  const target = e.target;
  if(!target.classList.contains('tree-item')) return;

  const targetType = target.parentElement.classList.contains('folder') ? 'folder' : 'file';

  if(targetType !== 'folder'){
    e.dataTransfer.dropEffect = 'none';
    return;
  }

  // 不允许拖拽到自己或自己的子目录
  if(dragSrcSpan){
    const srcPath = dragSrcSpan.dataset.path;
    const dstPath = target.dataset.path;
    if(dstPath === srcPath || dstPath.startsWith(srcPath + '/')){
      e.dataTransfer.dropEffect = 'none';
      return;
    }
  }

  e.preventDefault();
  target.classList.add('dragover');
  e.dataTransfer.dropEffect = 'move';
}

function dragLeave(e){
  if(e.target.classList.contains('tree-item')){
    e.target.classList.remove('dragover');
  }
}

function dropItem(e){
  e.preventDefault();
  const target = e.target;
  if(!target.classList.contains('tree-item')) return;

  target.classList.remove('dragover');
  const srcPath = e.dataTransfer.getData('text/plain');
  const dstPath = target.dataset.path;

  if(srcPath === dstPath){
    return;
  }

  // 只能移到文件夹
  if(!target.parentElement.classList.contains('folder')){
    alert('只能将项目移动到文件夹');
    return;
  }

  fetch('/api/move', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({src: srcPath, dst: dstPath})
  }).then(r => r.json()).then(data => {
    if(data.success){
      fetchTree();
      clearSelected();
    } else {
      alert('移动失败：'+data.error);
    }
  }).catch(_ => alert('网络错误'));

  if(dragSrcSpan){
    dragSrcSpan.classList.remove('dragging');
    dragSrcSpan = null;
  }
}

function dragEnd(e){
  if(dragSrcSpan) {
    dragSrcSpan.classList.remove('dragging');
    dragSrcSpan = null;
  }
}

function fetchTree(){
  fetch('/api/tree')
    .then(r=>r.json())
    .then(data=>{
      treeData = data.tree || [];
      treeContainer.innerHTML = '';
      treeContainer.appendChild(createTreeUl(treeData));
      clearSelected();
    }).catch(()=>{
      alert('获取文件树失败');
    });
}

createFolderBtn.onclick = () => {
  const name = newFolderInput.value.trim();
  if(!name){
    alert('请输入文件夹名称');
    return;
  }
  fetch('/api/mkdir',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({path:'', name: name}),
  }).then(r=>r.json()).then(data=>{
    if(data.success){
      newFolderInput.value = '';
      fetchTree();
      clearSelected();
    } else {
      alert('创建失败：'+data.error);
    }
  });
};

uploadForm.onsubmit = e=>{
  e.preventDefault();
  const files = uploadForm.file.files;
  const folder = uploadFolderInput.value.trim();

  if(files.length === 0){
    alert('请选择上传文件');
    return;
  }
  const formData = new FormData();
  formData.append('file', files[0]);
  formData.append('folder', folder);

  fetch('/api/upload',{
    method:'POST',
    body: formData
  }).then(r=>r.json()).then(data=>{
    if(data.success){
      alert('上传成功');
      uploadForm.reset();
      fetchTree();
      clearSelected();
    } else {
      alert('上传失败：'+data.error);
    }
  }).catch(()=>{
    alert('上传失败，网络错误');
  });
};

btnDelete.onclick = () => {
  if(!selectedItem) return;
  if(!confirm('确定删除 "'+selectedItem.path+'" ? 删除后不可恢复！')){
    return;
  }
  fetch('/api/delete',{
    method:'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: selectedItem.path})
  }).then(r => r.json()).then(data=>{
    if(data.success){
      fetchTree();
      clearSelected();
    } else {
      alert('删除失败：'+data.error);
    }
  });
};

btnRename.onclick = () => {
  if(!selectedItem) return;
  const newName = prompt('请输入新名称（不能包含 / 或 \\）:', selectedItem.name);
  if(!newName) return;
  if(newName.includes('/') || newName.includes('\\')){
    alert('名称不能包含 / 或 \\ 字符');
    return;
  }
  fetch('/api/rename',{
    method:'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({path: selectedItem.path, newname: newName.trim()})
  }).then(r=>r.json()).then(data=>{
    if(data.success){
      fetchTree();
      clearSelected();
    } else {
      alert('重命名失败：'+data.error);
    }
  });
};

btnDownload.onclick = () => {
  if(!selectedItem || selectedItem.type !== 'file') return;
  window.open('/api/download?path=' + encodeURIComponent(selectedItem.path));
};

// 页面加载后请求文件树
window.onload = fetchTree;
</script>
</body>
</html>
''')

######################
# API 接口部分, JSON 格式传输
######################

@app.route('/api/tree')
@auth.login_required
def api_tree():
    """
    返回文件树JSON数据
    """
    tree = build_tree()
    return jsonify({'tree': tree})

@app.route('/api/mkdir', methods=['POST'])
@auth.login_required
def api_mkdir():
    """
    创建新文件夹，参数：
    - path: 目标目录相对路径(相对于 ROOT_DIR)，可为空表示根目录
    - name: 新建文件夹名称
    """
    data = request.json
    parent_rel = (data.get('path') or '').strip('/')
    name = (data.get('name') or '').strip()
    # 校验名称合法性，不能含有斜杠等
    if not name or '/' in name or '\\' in name:
        return jsonify({'success': False, 'error': '文件夹名称非法'})
    try:
        parent_abs = safe_path(parent_rel)
    except ValueError:
        return jsonify({'success': False, 'error': '非法路径穿越'})
    new_folder_abs = os.path.join(parent_abs, name)
    if os.path.exists(new_folder_abs):
        return jsonify({'success': False, 'error': '文件夹已存在'})
    try:
        os.mkdir(new_folder_abs)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/upload', methods=['POST'])
@auth.login_required
def api_upload():
    """
    上传文件，字段：
    - file: 上传文件
    - folder: 上传到的目标文件夹相对路径，空为根目录
    """
    folder_rel = (request.form.get('folder') or '').strip('/')
    try:
        folder_abs = safe_path(folder_rel)
    except ValueError:
        return jsonify({'success': False, 'error': '非法路径穿越'})
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '缺少文件'})
    f = request.files['file']
    filename = f.filename
    if not filename:
        return jsonify({'success': False, 'error': '文件名为空'})
    # 防止文件名带路径(如 ../../)，只取 basename
    filename = os.path.basename(filename)
    save_path = os.path.join(folder_abs, filename)
    # 确认保存路径仍在 ROOT_DIR
    if not save_path.startswith(ROOT_DIR):
        return jsonify({'success': False, 'error': '非法路径'})
    try:
        f.save(save_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/download')
@auth.login_required
def api_download():
    """
    文件下载
    参数:
    - path: 文件相对路径
    """
    rel_path = (request.args.get('path') or '').strip('/')
    try:
        abs_path = safe_path(rel_path)
    except ValueError:
        abort(400, "非法路径")
    if not os.path.isfile(abs_path):
        abort(404, "文件不存在")
    directory, filename = os.path.split(abs_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/api/delete', methods=['POST'])
@auth.login_required
def api_delete():
    """
    删除文件或文件夹，参数：
    - path: 相对路径
    """
    data = request.json
    rel_path = (data.get('path') or '').strip('/')
    try:
        abs_path = safe_path(rel_path)
    except ValueError:
        return jsonify({'success': False, 'error': '非法路径'})
    if not os.path.exists(abs_path):
        return jsonify({'success': False, 'error': '路径不存在'})
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        elif os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            return jsonify({'success': False, 'error': '目标不是文件或目录'})
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/rename', methods=['POST'])
@auth.login_required
def api_rename():
    """
    重命名文件或文件夹，参数：
    - path: 现有相对路径
    - newname: 新名称
    """
    data = request.json
    rel_path = (data.get('path') or '').strip('/')
    new_name = (data.get('newname') or '').strip()
    if not new_name or '/' in new_name or '\\' in new_name:
        return jsonify({'success': False, 'error': '非法的新名称'})
    try:
        abs_path = safe_path(rel_path)
    except ValueError:
        return jsonify({'success': False, 'error': '非法路径穿越'})
    if not os.path.exists(abs_path):
        return jsonify({'success': False, 'error': '目标路径不存在'})
    parent_dir = os.path.dirname(abs_path)
    new_path = os.path.join(parent_dir, new_name)
    if os.path.exists(new_path):
        return jsonify({'success': False, 'error': '目标名称已存在'})
    try:
        os.rename(abs_path, new_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/move', methods=['POST'])
@auth.login_required
def api_move():
    """
    移动文件或文件夹，参数：
    - src: 源相对路径
    - dst: 目标文件夹相对路径
    """
    data = request.json
    src_rel = (data.get('src') or '').strip('/')
    dst_rel = (data.get('dst') or '').strip('/')
    try:
        src_abs = safe_path(src_rel)
        dst_abs = safe_path(dst_rel)
    except ValueError:
        return jsonify({'success': False, 'error': '非法路径穿越'})
    if not os.path.exists(src_abs):
        return jsonify({'success': False, 'error': '源路径不存在'})
    if not os.path.isdir(dst_abs):
        return jsonify({'success': False, 'error': '目标路径不是文件夹'})
    src_name = os.path.basename(src_abs)
    new_path = os.path.join(dst_abs, src_name)
    # 防止移动到自身或子目录（防止无限递归）
    if src_abs == new_path:
        return jsonify({'success': False, 'error': '源和目标路径相同'})
    if new_path.startswith(src_abs + os.sep):
        return jsonify({'success': False, 'error': '不能移动到自身子目录'})
    if os.path.exists(new_path):
        return jsonify({'success': False, 'error': '目标路径已存在同名文件或文件夹'})
    try:
        shutil.move(src_abs, new_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
