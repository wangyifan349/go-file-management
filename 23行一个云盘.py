from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string  # 导入flask基础组件及模板渲染
from werkzeug.utils import secure_filename  # 文件名安全处理
from flask_httpauth import HTTPBasicAuth  # flask-httpauth 用于简易登录认证
from werkzeug.security import generate_password_hash, check_password_hash  # 生成和校验密码哈希
import os  # 操作系统路径相关
import shutil  # 高级文件操作（支持目录移动）

# 创建Flask应用
application = Flask(__name__)  # 主应用实例
auth = HTTPBasicAuth()  # HTTP基本认证实例

# 护眼主题 配色变量
THEME_BG_COLOR = '#fdecea'  # 淡红底色
THEME_BORDER_COLOR = '#f5c6c5'  # 红色边框
THEME_TEXT_COLOR = '#8b0000'  # 深红文本

# 根存储目录，所有操作均限制在此目录下，确保安全
ROOT_STORAGE = os.path.join(os.path.dirname(__file__), 'storage')  # 存储目录
if not os.path.exists(ROOT_STORAGE):
    os.makedirs(ROOT_STORAGE)  # 确保目录存在

# 简单内存用户表  生产环境请使用数据库或更安全存储
users = {
    "admin": generate_password_hash("password123")  # admin用户密码
}

@auth.verify_password  # 验证用户密码
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username  # 认证成功
    return None  # 认证失败

def resolve_full_path(relative_path):  # 解析安全绝对路径，避免路径穿越攻击
    """
    将相对路径解析为存储根目录下的绝对路径，防止路径穿越攻击
    :param relative_path: 传入的相对路径字符串
    :return: 解析后的绝对路径字符串
    """
    relative_path = relative_path.strip('/\\')  # 去除首尾斜杠
    absolute_path = os.path.normpath(os.path.join(ROOT_STORAGE, relative_path))  # 组合并规范路径
    root_abs = os.path.abspath(ROOT_STORAGE)
    abs_path = os.path.abspath(absolute_path)
    if not abs_path.startswith(root_abs):  # 确保解析后路径依然位于根目录内
        abort(400, 'Invalid path')
    return abs_path

@application.route('/')  # 首页路由，渲染单页应用
@auth.login_required  # 需要登录认证
def render_user_interface():
    # 此处用render_template_string直接内嵌HTML模板字符串
    return render_template_string("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask 文件管理器</title>
    <!-- 引入Bootstrap CSS -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body {
            background-color: {{ bg_color }};
            color: {{ text_color }};
            padding: 20px;
        }
        .container {
            border: 1px solid {{ border_color }};
            border-radius: 6px;
            background: #fff0f0;
            padding: 20px;
        }
        #fileTree ul {
            list-style: none;
            padding-left: 20px;
        }
        #fileTree li {
            margin: 2px 0;
            cursor: pointer;
            padding: 3px 6px;
            border-radius: 3px;
        }
        #fileTree li.directory {
            font-weight: 700;
        }
        #fileTree li.file {
            font-weight: 400;
        }
        #fileTree li.dragOver {
            background-color: {{ border_color }}88 !important;
        }
        .contextMenu {
            position: absolute;
            background: white;
            border: 1px solid {{ border_color }};
            box-shadow: 2px 2px 6px rgba(0,0,0,0.15);
            display: none;
            z-index: 1000;
            border-radius: 4px;
            min-width: 130px;
        }
        .contextMenu li {
            padding: 8px 12px;
            user-select: none;
            color: {{ text_color }};
        }
        .contextMenu li:hover {
            background-color: {{ border_color }};
            color: white;
        }
        .form-label, label {
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1 class="mb-4">Flask 文件管理器</h1>

        <form id="uploadForm" class="mb-3" enctype="multipart/form-data">
            <div class="row g-2 align-items-center">
                <div class="col-auto">
                    <label for="uploadFile" class="col-form-label">上传文件到当前目录：</label>
                </div>
                <div class="col-auto">
                    <input type="file" id="uploadFile" name="uploadFile" class="form-control" required>
                </div>
                <div class="col-auto">
                    <button type="submit" class="btn btn-danger">上传</button>
                </div>
            </div>
        </form>

        <div class="mb-3">
            <label>当前目录: <code id="currentDirectoryDisplay">/</code></label>
            <button id="upBtn" class="btn btn-sm btn-outline-danger ms-3">上一级</button>
            <button id="rootBtn" class="btn btn-sm btn-outline-danger ms-1">根目录</button>
        </div>

        <div id="fileTree" aria-label="文件和目录列表"></div>
    </div>

    <ul id="contextMenu" class="contextMenu list-unstyled shadow-sm">
        <li data-action="download" class="context-item">下载</li>
        <li data-action="delete" class="context-item">删除</li>
        <li data-action="rename" class="context-item">重命名</li>
    </ul>

<script>
    // 护眼主题配色变量来自Flask注入
    const borderColor = '{{ border_color }}';
    const textColor = '{{ text_color }}';

    let currentDirectory = ''; // 当前目录路径，根目录空字符串
    let contextMenuTarget = null;  // 右键菜单作用对象元素

    function ajaxGet(url) {  // 简单的GET请求
        return fetch(url, { credentials: 'include' });
    }

    function ajaxPostJson(url, data) {  // 发送POST JSON请求
        return fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            credentials: 'include'
        });
    }

    function refreshDirectory(path = '') {
        currentDirectory = path;
        document.getElementById('currentDirectoryDisplay').innerText = '/' + path;
        ajaxGet('/api/list?path=' + encodeURIComponent(path))
            .then(r => {
                if (!r.ok) throw new Error('读取目录失败');
                return r.json();
            }).then(data => buildFileTree(data.entries))
            .catch(e => {
                alert('读取目录失败：' + e.message);
                buildFileTree([]);
            });
    }

    function buildFileTree(entries) {
        let container = document.getElementById('fileTree');
        container.innerHTML = '';
        let ul = document.createElement('ul');
        for (let i = 0; i < entries.length; i++) {
            let entry = entries[i];
            let li = document.createElement('li');
            li.textContent = entry.name;
            li.dataset.name = entry.name;
            li.dataset.isDirectory = entry.isDirectory;
            li.className = entry.isDirectory ? 'directory' : 'file';
            li.tabIndex = 0;  // 可聚焦

            li.draggable = true;  // 支持拖拽

            li.onclick = (function(entry) {
                return function() {
                    if (entry.isDirectory) {
                        let newPath = currentDirectory ? currentDirectory + '/' + entry.name : entry.name;
                        refreshDirectory(newPath);
                    }
                };
            })(entry);

            li.ondragstart = function(e) {
                let sourcePath = currentDirectory ? currentDirectory + '/' + entry.name : entry.name;
                e.dataTransfer.setData('text/plain', sourcePath);
            };

            li.ondragover = function(e) {
                if (entry.isDirectory) {
                    e.preventDefault();
                    li.classList.add('dragOver');
                }
            };

            li.ondragleave = function(e) {
                li.classList.remove('dragOver');
            };

            li.ondrop = function(e) {
                e.preventDefault();
                li.classList.remove('dragOver');
                let source = e.dataTransfer.getData('text/plain');
                let destination = currentDirectory ? currentDirectory + '/' + entry.name : entry.name;
                ajaxPostJson('/api/move', { sourcePath: source, destinationDirectory: destination })
                    .then(r => {
                        if (!r.ok) throw new Error('移动失败');
                        refreshDirectory(currentDirectory);
                    }).catch(e => alert('移动失败：' + e.message));
            };

            li.oncontextmenu = function(e) {
                e.preventDefault();
                contextMenuTarget = li;
                let menu = document.getElementById('contextMenu');
                menu.style.top = e.pageY + 'px';
                menu.style.left = e.pageX + 'px';
                menu.style.display = 'block';
            };

            ul.appendChild(li);
        }
        container.appendChild(ul);
    }

    // 上传文件
    document.getElementById('uploadForm').addEventListener('submit', function(e) {
        e.preventDefault();
        let input = document.getElementById('uploadFile');
        if (!input.files.length) return alert('请选择上传文件。');
        let formData = new FormData();
        formData.append('uploadFile', input.files[0]);
        formData.append('path', currentDirectory);

        fetch('/api/upload', {
            method: 'POST',
            body: formData,
            credentials: 'include'
        }).then(r => {
            if (!r.ok) throw new Error('上传失败');
            input.value = '';
            refreshDirectory(currentDirectory);
        }).catch(e => alert('上传失败: ' + e.message));
    });

    // 上一级按钮
    document.getElementById('upBtn').addEventListener('click', function() {
        if (!currentDirectory) return;
        let parts = currentDirectory.split('/');
        parts.pop();
        refreshDirectory(parts.join('/'));
    });

    // 根目录按钮
    document.getElementById('rootBtn').addEventListener('click', function() {
        refreshDirectory('');
    });

    // 点击空白隐藏菜单
    document.addEventListener('click', () => {
        document.getElementById('contextMenu').style.display = 'none';
    });

    // 右键菜单操作处理
    let menuItems = document.querySelectorAll('.contextMenu li');
    for (let i = 0; i < menuItems.length; i++) {
        menuItems[i].addEventListener('click', function() {
            let action = this.dataset.action;
            if (!contextMenuTarget) return;
            let name = contextMenuTarget.dataset.name;
            let isDirectory = contextMenuTarget.dataset.isDirectory === 'true';
            let fullPath = currentDirectory ? currentDirectory + '/' + name : name;

            if (action === 'download') {
                if (isDirectory) {
                    alert('目录无法下载。');
                } else {
                    window.open('/api/download?path=' + encodeURIComponent(fullPath), '_blank');
                }
            }
            else if (action === 'delete') {
                if (confirm('确定删除 "' + name + '" 吗？')) {
                    ajaxPostJson('/api/delete', { path: fullPath })
                        .then(r => {
                            if (!r.ok) throw new Error('删除失败');
                            refreshDirectory(currentDirectory);
                        }).catch(e => alert('删除失败：' + e.message));
                }
            }
            else if (action === 'rename') {
                let newName = prompt('输入新的名称:', name);
                if (newName && newName !== name) {
                    ajaxPostJson('/api/rename', { oldPath: fullPath, newName: newName })
                        .then(r => {
                            if (!r.ok) throw new Error('重命名失败');
                            refreshDirectory(currentDirectory);
                        }).catch(e => alert('重命名失败：' + e.message));
                }
            }
            document.getElementById('contextMenu').style.display = 'none';
        });
    }

    // 页面初始化加载根目录
    refreshDirectory();
</script>

</body>
</html>
""", bg_color=THEME_BG_COLOR, border_color=THEME_BORDER_COLOR, text_color=THEME_TEXT_COLOR)  # 注入样式变量

@application.route('/api/list')  # 列出目录内容接口
@auth.login_required
def list_entries():
    path = request.args.get('path', '')
    full = resolve_full_path(path)  # 解析安全路径
    if not os.path.exists(full):
        abort(404, '目录不存在')
    if not os.path.isdir(full):
        abort(400, '请求路径不是目录')
    entries = []
    try:
        for entry in os.listdir(full):  # 遍历目录项
            entry_path = os.path.join(full, entry)
            entries.append({  # 封装条目字典
                'name': entry,
                'isDirectory': os.path.isdir(entry_path)
            })
    except Exception as e:
        abort(500, '读取目录异常')
    return jsonify(entries=entries)  # 返回json

@application.route('/api/upload', methods=['POST'])  # 文件上传接口
@auth.login_required
def upload_file():
    path = request.form.get('path', '')
    directory = resolve_full_path(path)
    if not os.path.exists(directory):
        abort(404, "上传目录不存在")
    upload = request.files.get('uploadFile')
    if not upload or upload.filename == '':
        abort(400, '未上传文件')
    filename = secure_filename(upload.filename)
    if not filename:
        abort(400, '无效文件名')
    save_path = os.path.join(directory, filename)
    try:
        upload.save(save_path)  # 保存文件
    except Exception as e:
        abort(500, '保存文件失败')
    return jsonify(success=True)

@application.route('/api/delete', methods=['POST'])  # 删除文件或空目录接口
@auth.login_required
def delete_entry():
    data = request.get_json()
    if not data or 'path' not in data:
        abort(400, '缺少path参数')
    path = data['path']
    target = resolve_full_path(path)
    if not os.path.exists(target):
        abort(404, '路径不存在')
    try:
        if os.path.isdir(target):
            os.rmdir(target)  # 只删除空目录
        else:
            os.remove(target)  # 删除文件
    except OSError as e:
        abort(400, '删除失败，目录非空或权限不足')
    return jsonify(success=True)

@application.route('/api/rename', methods=['POST'])  # 重命名接口
@auth.login_required
def rename_entry():
    data = request.get_json()
    if not data or 'oldPath' not in data or 'newName' not in data:
        abort(400, '缺少参数')
    old_path = data['oldPath']
    new_name = data['newName'].strip()
    if '/' in new_name or '\\' in new_name or new_name == '':
        abort(400, '新名称无效')
    old_full = resolve_full_path(old_path)
    if not os.path.exists(old_full):
        abort(404, '原路径不存在')
    parent_dir = os.path.dirname(old_full)
    new_full = os.path.join(parent_dir, secure_filename(new_name))
    if os.path.exists(new_full):
        abort(400, '新名称已存在')
    try:
        os.rename(old_full, new_full)
    except Exception as e:
        abort(400, '重命名失败')
    return jsonify(success=True)

@application.route('/api/move', methods=['POST'])  # 移动文件/目录接口
@auth.login_required
def move_entry():
    data = request.get_json()
    if not data or 'sourcePath' not in data or 'destinationDirectory' not in data:
        abort(400, '缺少参数')
    source = data['sourcePath']
    dest = data['destinationDirectory']
    source_full = resolve_full_path(source)
    dest_full = resolve_full_path(dest)
    if not os.path.exists(source_full):
        abort(404, '源路径不存在')
    if not os.path.isdir(dest_full):
        abort(400, '目标不是目录')
    new_full = os.path.join(dest_full, os.path.basename(source_full))
    if os.path.exists(new_full):
        abort(400, '目标目录已存在同名文件或目录')
    try:
        shutil.move(source_full, new_full)  # 支持跨设备移动
    except Exception as e:
        abort(400, '移动失败')
    return jsonify(success=True)

@application.route('/api/download')  # 文件下载接口
@auth.login_required
def download_entry():
    path = request.args.get('path', '')
    full = resolve_full_path(path)
    if not os.path.isfile(full):
        abort(404)
    directory = os.path.dirname(full)
    filename = os.path.basename(full)
    return send_from_directory(directory, filename, as_attachment=True)  # 发送文件

if __name__ == '__main__':
    application.run(debug=True, host='0.0.0.0', port=5000)  # 启动服务器，外网可访问
