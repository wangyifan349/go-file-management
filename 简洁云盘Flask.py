from flask import Flask, request, jsonify, send_from_directory, render_template_string, redirect, url_for, flash, session  # 导入必要的模块
import os  # 操作系统相关
import sqlite3  # 数据库模块
from werkzeug.security import generate_password_hash, check_password_hash  # 用于密码哈希
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required  # 用户认证
from datetime import timedelta  # 时间管理

app = Flask(__name__)  # 创建 Flask 应用
app.secret_key = 'your_secret_key'  # 设置应用的密钥
app.permanent_session_lifetime = timedelta(days=7)  # 设置 session 过期时间

login_manager = LoginManager()  # 创建登录管理器
login_manager.init_app(app)  # 初始化应用
login_manager.login_view = 'login'  # 未登录时重定向到登录页面

ROOT_DIR = os.path.abspath('files')  # 设置根目录
os.makedirs(ROOT_DIR, exist_ok=True)  # 创建根目录

DATABASE = 'users.db'  # 数据库文件路径

def init_db():
    conn = sqlite3.connect(DATABASE)  # 连接数据库
    cursor = conn.cursor()  # 创建游标
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL
    )
    ''')  # 创建用户表
    conn.commit()  # 提交事务
    conn.close()  # 关闭连接

init_db()  # 初始化数据库

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id  # 用户 ID
        self.username = username  # 用户名

@login_manager.user_loader
def load_user(user_id):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('SELECT id, username FROM users WHERE id=?', (user_id,))
    user = cursor.fetchone()
    conn.close()
    if user:
        return User(user[0], user[1])  # 返回用户对象
    return None

def safe_path(req_path):
    full_path = os.path.abspath(os.path.join(ROOT_DIR, req_path))
    if not full_path.startswith(ROOT_DIR):
        raise Exception('非法路径访问')
    return full_path  # 返回安全的完整路径

# -----------------------------------------------------------------------------

LOGIN_HTML = """
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>登录</title></head>
<body style="background:#000;color:#f44;font-family:sans-serif;">
<h2>登录</h2>
<form action="{{ url_for('login') }}" method="post">
  <label>用户名: <input type="text" name="username" required></label><br><br>
  <label>密码: <input type="password" name="password" required></label><br><br>
  <button type="submit">登录</button>
</form>
<p>没有账号？<a href="{{ url_for('register') }}" style="color:#f66;">注册</a></p>
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <ul style="color:#f88;">
    {% for message in messages %}
      <li>{{ message }}</li>
    {% endfor %}
    </ul>
  {% endif %}
{% endwith %}
</body>
</html>
"""  # 登录页面模板

REGISTER_HTML = """
<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>注册</title></head>
<body style="background:#000;color:#f44;font-family:sans-serif;">
<h2>注册</h2>
<form action="{{ url_for('register') }}" method="post">
  <label>用户名: <input type="text" name="username" required></label><br><br>
  <label>密码: <input type="password" name="password" required></label><br><br>
  <label>确认密码: <input type="password" name="password2" required></label><br><br>
  <button type="submit">注册</button>
</form>
<p>已有账号？<a href="{{ url_for('login') }}" style="color:#f66;">登录</a></p>
{% with messages = get_flashed_messages() %}
  {% if messages %}
    <ul style="color:#f88;">
    {% for message in messages %}
      <li>{{ message }}</li>
    {% endfor %}
    </ul>
  {% endif %}
{% endwith %}
</body>
</html>
"""  # 注册页面模板

# -----------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))  # 如果已登录，重定向到首页
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT id, password_hash FROM users WHERE username=?', (username,))
        user = cursor.fetchone()
        conn.close()
        if user and check_password_hash(user[1], password):
            user_obj = User(user[0], username)
            login_user(user_obj)
            flash('登录成功！')
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误')
    return render_template_string(LOGIN_HTML)  # 渲染登录页面

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))  # 如果已登录，重定向到首页
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')
        if not username or not password:
            flash('用户名和密码不能为空')
        elif password != password2:
            flash('两次密码输入不一致')
        else:
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users WHERE username=?', (username,))
            exists = cursor.fetchone()
            if exists:
                flash('用户名已被注册')
            else:
                pw_hash = generate_password_hash(password)
                cursor.execute('INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, pw_hash))
                conn.commit()
                conn.close()
                flash('注册成功，请登录')
                return redirect(url_for('login'))
            conn.close()
    return render_template_string(REGISTER_HTML)  # 渲染注册页面

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已登出')
    return redirect(url_for('login'))  # 登出并重定向到登录页面

# -----------------------------------------------------------------------------

HTML = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>文件管理器（黑底红字版）</title>
  <!-- Bootstrap 5 CSS -->
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body {
      background-color: #000000;
      color: #ff4444;
      font-size: 1.25rem;
      min-height: 100vh;
      padding-top: 1rem;
      padding-bottom: 1rem;
      user-select: none;
    }
    ul {
      list-style: none;
      padding-left: 1.2rem;
      margin-bottom: 0;
    }
    li {
      cursor: pointer;
      padding: 0.1rem 0;
      user-select:none;
    }
    li.folder::before {
      content: "📁 ";
    }
    li.file::before {
      content: "📄 ";
    }

    #contextMenu {
      position: absolute;
      background: #000000;
      border: none;
      padding: 0.2rem 0;
      display: none;
      z-index: 1000;
      box-shadow: none;
      width: 160px;
      font-weight: 600;
      color: #ff4444;
      font-size: 1rem;
    }
    #contextMenu div {
      padding: 0.35rem 1rem;
      cursor: pointer;
      transition: background-color 0.15s ease-in-out;
    }
    #contextMenu div:hover {
      background-color: #330000;
    }

    #uploadFile {
      display: none;
    }

    #dropZone {
      border: none;
      padding: 1rem;
      margin-top: 0.75rem;
      text-align: center;
      color: #cc2222;
      background-color: #110000;
      font-size: 1.1rem;
      font-weight: 600;
      user-select:none;
      border-radius: 0.3rem;
      transition: background-color 0.3s ease;
    }
    #dropZone.dragover {
      background-color: #440000;
      color: #ff4444;
    }

    .btn-custom {
      background: none;
      border: none;
      color: #ff4444;
      font-weight: 700;
      font-size: 1.1rem;
      padding: 0.15rem 0.6rem;
      transition: color 0.2s ease;
    }
    .btn-custom:hover {
      color: #ff7777;
      text-decoration: underline;
      background: none;
      box-shadow: none;
    }

    #path {
      font-size: 1.2rem;
      font-weight: 700;
      margin-bottom: 0.5rem;
      user-select: text;
    }

    li.up {
      color: #ff6666;
      font-weight: 700;
    }
    li.up:hover {
      color: #ff9999;
    }

    .dragging {
      opacity: 0.5;
    }

    /* 搜索框样式 */
    #searchBar {
      margin-bottom: 1rem;
      display: flex;
    }
    #searchInput {
      flex: 1;
      padding: 0.5rem;
      font-size: 1rem;
      border: 1px solid #ff4444;
      border-radius: 0.25rem;
      background-color: #110000;
      color: #ff4444;
    }
    #searchButton {
      margin-left: 0.5rem;
      padding: 0.5rem 1rem;
      font-size: 1rem;
      border: 1px solid #ff4444;
      border-radius: 0.25rem;
      background-color: #110000;
      color: #ff4444;
    }
  </style>
</head>
<body>
<div class="container-fluid px-4">

  <h1 class="mb-3">📂 文件管理器（黑底红字版）</h1>

  <div class="mb-3" style="user-select:none;">
    <button class="btn-custom" onclick="showRootMenu()">菜单操作</button>
    <input type="file" id="uploadFile" multiple>
    <button class="btn-custom" onclick="logout()">退出登录</button>
  </div>

  <!-- 搜索框 -->
  <div id="searchBar">
    <input type="text" id="searchInput" placeholder="搜索文件...">
    <button id="searchButton" onclick="searchFiles()">搜索</button>
  </div>

  <div id="path" class="mb-2" title="当前文件夹路径"></div>

  <div id="dropZone" class="mb-3" title="将文件拖拽到这里上传">⬇ 拖拽文件到这里上传 ⬇</div>

  <div id="fileList" class="fs-5" style="word-break:break-word;"></div>

  <div id="contextMenu"></div>
</div>

<!-- Bootstrap 5 JS Bundle (Popper + Bootstrap) -->
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>

<script>
let currentPath = '';
let contextTarget = null;
let contextTargetName = '';
let contextTargetType = '';

const contextMenu = document.getElementById('contextMenu');
const dropZone = document.getElementById('dropZone');
const uploadInput = document.getElementById('uploadFile');

function listFiles(path='') {
    fetch('/list?path=' + encodeURIComponent(path))
    .then(function(res){ return res.json(); })
    .then(function(data){
        currentPath = path;
        document.getElementById('path').textContent = '当前路径：/' + path;
        let html = '<ul>';
        if(path){
          const upPath = path.split('/').slice(0,-1).join('/');
          html += `<li class="up" onclick="listFiles('${upPath}')">⬆ 上级目录</li>`;
        }
        for(let i=0; i<data.length; i++){
            let item = data[i];
            html += `<li class="${item.type}" draggable="true" ondragstart="drag(event, '${item.name}')" ondragover="allowDrop(event)" ondrop="drop(event, '${item.name}', '${item.type}')" oncontextmenu="showMenu(event, '${item.name}', '${item.type}')" ondblclick="openItem('${item.name}', '${item.type}')">${item.name}</li>`;
        }
        html += '</ul>';
        document.getElementById('fileList').innerHTML = html;
    }).catch(function(){
        alert('无法获取文件列表，请稍后重试');
    });
}

function openItem(name, type) {
    if(type === 'folder') {
        listFiles(currentPath ? currentPath + '/' + name : name);
    } else {
        let ext = name.split('.').pop().toLowerCase();
        if(['jpg','jpeg','png','gif','bmp','svg','webp'].includes(ext)){
            window.open('/preview?path=' + encodeURIComponent(currentPath ? currentPath + '/' + name : name), '_blank');
        } else if(['mp4','webm','ogg','mov'].includes(ext)){
            window.open('/video?path=' + encodeURIComponent(currentPath ? currentPath + '/' + name : name), '_blank');
        } else if(['mp3','wav','ogg','flac'].includes(ext)){
            window.open('/audio?path=' + encodeURIComponent(currentPath ? currentPath + '/' + name : name), '_blank');
        } else if(['txt','py','js','css','html','md','json','xml','csv','log','ini','conf','sh','bat'].includes(ext)){
            window.open('/edit?path=' + encodeURIComponent(currentPath ? currentPath + '/' + name : name), '_blank');
        } else {
            window.open('/download?path=' + encodeURIComponent(currentPath ? currentPath + '/' + name : name), '_blank');
        }
    }
}

function showRootMenu() {
    contextTarget = null;
    contextTargetName = null;
    contextTargetType = null;
    showCustomMenu([
        {text: '新建文件夹', action: createFolder},
        {text: '上传文件', action: function(){ uploadInput.click(); }}
    ], window.innerWidth/2, window.innerHeight/2);
}

function showMenu(event, name, type) {
    event.preventDefault();
    contextTarget = event.target;
    contextTargetName = name;
    contextTargetType = type;

    const menuItems = [];

    if(type === 'folder') {
        menuItems.push({text: '打开', action: function(){ openItem(name, type); }});
        menuItems.push({text: '重命名', action: renameItem});
        menuItems.push({text: '删除', action: deleteItem});
        menuItems.push({text: '上传文件', action: function(){ uploadInput.click(); closeMenu(); }});
        menuItems.push({text: '新建文件夹', action: createFolder});
    } else {
        menuItems.push({text: '打开', action: function(){ openItem(name, type); }});
        menuItems.push({text: '重命名', action: renameItem});
        menuItems.push({text: '删除', action: deleteItem});
    }
    showCustomMenu(menuItems, event.pageX, event.pageY);
}

function showCustomMenu(items, x, y) {
    contextMenu.innerHTML = '';
    for(let i=0; i<items.length; i++){
        const item = items[i];
        const div = document.createElement('div');
        div.textContent = item.text;
        div.onclick = function(){ item.action(); closeMenu(); };
        contextMenu.appendChild(div);
    }
    contextMenu.style.display = 'block';

    let maxX = window.innerWidth - contextMenu.offsetWidth;
    let maxY = window.innerHeight - contextMenu.offsetHeight;
    if(x > maxX) x = maxX;
    if(y > maxY) y = maxY;
    contextMenu.style.left = x + 'px';
    contextMenu.style.top = y + 'px';
}

function closeMenu() {
    contextMenu.style.display = 'none';
}

window.onclick = function(){ closeMenu(); };
window.oncontextmenu = function(){ /*closeMenu();*/ };

function deleteItem() {
    if(!contextTargetName) return;
    if(confirm('确定删除 "' + contextTargetName + '" ？')) {
        let fullPath = currentPath ? currentPath + '/' + contextTargetName : contextTargetName;
        fetch('/delete', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({path: fullPath})
        })
        .then(function(res){ return res.json(); })
        .then(function(data){
            alert(data.message);
            listFiles(currentPath);
        }).catch(function(){ alert('删除失败，网络异常'); });
    }
}

function renameItem() {
    if(!contextTargetName) return;
    let newName = prompt('输入 "' + contextTargetName + '" 的新名称：', contextTargetName);
    if(newName && newName.trim() && newName !== contextTargetName) {
        if(/[\\/]/.test(newName)) {
            alert('名称不能包含 / 或 \\ ');
            return;
        }
        let fullPath = currentPath ? currentPath + '/' + contextTargetName : contextTargetName;
        fetch('/rename', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({path: fullPath, new_name: newName.trim()})
        })
        .then(function(res){ return res.json(); })
        .then(function(data){
            alert(data.message);
            listFiles(currentPath);
        }).catch(function(){ alert('重命名失败，网络异常'); });
    }
}

function createFolder() {
    let folderName = prompt('请输入文件夹名称');
    if(folderName){
        folderName = folderName.trim();
        if(!folderName) return;
        if(/[\\/]/.test(folderName)) {
           alert('文件夹名称不能包含 / 或 \\ ');
           return;
        }
        fetch('/mkdir', {
            method: 'POST',
            headers: {'Content-Type':'application/json'},
            body: JSON.stringify({path: currentPath, folder: folderName})
        })
        .then(function(res){ return res.json(); })
        .then(function(data){
            alert(data.message);
            listFiles(currentPath);
        }).catch(function(){ alert('创建文件夹失败，网络异常'); });
    }
}

uploadInput.onchange = function(){
    if(uploadInput.files.length > 0){
        let formData = new FormData();
        for(let i=0; i<uploadInput.files.length; i++){
            formData.append('files', uploadInput.files[i]);
        }
        formData.append('path', currentPath);
        fetch('/upload', {method: 'POST', body: formData})
        .then(function(res){ return res.json(); })
        .then(function(data){
            alert(data.message);
            listFiles(currentPath);
            uploadInput.value = '';
        }).catch(function(){ alert('上传失败，网络异常'); });
    }
}

dropZone.ondragover = function(e){
    e.preventDefault();
    dropZone.classList.add('dragover');
}
dropZone.ondragleave = function(e){
    e.preventDefault();
    dropZone.classList.remove('dragover');
}
dropZone.ondrop = function(e){
    e.preventDefault();
    dropZone.classList.remove('dragover');
    let files = e.dataTransfer.files;
    if(files.length > 0){
        let formData = new FormData();
        for(let i=0; i<files.length; i++){
            formData.append('files', files[i]);
        }
        formData.append('path', currentPath);
        fetch('/upload', {method: 'POST', body: formData})
        .then(function(res){ return res.json(); })
        .then(function(data){
            alert(data.message);
            listFiles(currentPath);
        }).catch(function(){ alert('上传失败，网络异常'); });
    }
}

let dragSource = null;
function drag(event, name){
    dragSource = name;
    event.dataTransfer.setData("text/plain", name);
    event.target.classList.add('dragging');
}
function allowDrop(event){
    event.preventDefault();
}
function drop(event, targetName, targetType){
    event.preventDefault();
    let sourceName = dragSource;
    dragSource = null;
    let sourcePath = currentPath ? currentPath + '/' + sourceName : sourceName;
    let targetPath = currentPath ? currentPath + '/' + targetName : targetName;
    if(targetType !== 'folder'){
        targetPath = currentPath;
    }
    fetch('/move', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({source: sourcePath, target: targetPath})
    })
    .then(function(res){ return res.json(); })
    .then(function(data){
        alert(data.message);
        listFiles(currentPath);
    }).catch(function(){ alert('移动失败，网络异常'); });
    event.target.classList.remove('dragging');
}

function logout(){
    window.location.href = "/logout";
}

function searchFiles(){
    let query = document.getElementById('searchInput').value.trim();
    if(!query){
        alert('请输入搜索关键词');
        return;
    }
    fetch('/search?q=' + encodeURIComponent(query))
    .then(function(res){ return res.json(); })
    .then(function(data){
        document.getElementById('path').textContent = '搜索结果';
        let html = '<ul>';
        for(let i=0; i<data.length; i++){
            let item = data[i];
            html += `<li class="${item.type}" onclick="openItemFromSearch('${item.path}', '${item.type}')">${item.name}</li>`;
        }
        html += '</ul>';
        document.getElementById('fileList').innerHTML = html;
    }).catch(function(){
        alert('搜索失败，请稍后重试');
    });
}

function openItemFromSearch(fullPath, type){
    if(type === 'folder'){
        let pathArray = fullPath.split('/').filter(s => s);
        pathArray.shift(); // 移除根目录
        listFiles(pathArray.join('/'));
    } else {
        window.open('/download?path=' + encodeURIComponent(fullPath.slice(1)), '_blank');
    }
}

listFiles();
</script>
</body>
</html>
"""  # 主页面模板，添加了搜索框

# -----------------------------------------------------------------------------

@app.route('/')
@login_required
def index():
    return render_template_string(HTML)  # 渲染主页面

@app.route('/list')
@login_required
def list_files():
    req_path = request.args.get('path', '').strip('/')
    try:
        full_path = safe_path(req_path)
        if not os.path.exists(full_path):
            return jsonify([])
        items = []
        names = os.listdir(full_path)
        names.sort()
        for name in names:
            if name.startswith('.'):
                continue
            item_path = os.path.join(full_path, name)
            if os.path.isdir(item_path):
                item_type = 'folder'
            else:
                item_type = 'file'
            items.append({'name': name, 'type': item_type})
        return jsonify(items)
    except Exception:
        return jsonify([])

@app.route('/download')
@login_required
def download_file():
    req_path = request.args.get('path', '').strip('/')
    try:
        full_path = safe_path(req_path)
        if not os.path.isfile(full_path):
            return "文件未找到", 404
        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception:
        return "非法路径或文件不存在", 403

@app.route('/delete', methods=['POST'])
@login_required
def delete_file_or_dir():
    data = request.get_json()
    req_path = data.get('path', '').strip('/')
    if not req_path:
        return jsonify({'message': '路径不能为空'})
    try:
        full_path = safe_path(req_path)
        if not os.path.exists(full_path):
            return jsonify({'message': '文件或文件夹不存在'})
        if os.path.isdir(full_path):
            if os.listdir(full_path):
                return jsonify({'message': '文件夹不为空，无法删除'})
            os.rmdir(full_path)
        else:
            os.remove(full_path)
        return jsonify({'message': '删除成功'})
    except Exception as e:
        return jsonify({'message': f'删除失败: {e}'})

@app.route('/rename', methods=['POST'])
@login_required
def rename():
    data = request.get_json()
    req_path = data.get('path', '').strip('/')
    new_name = data.get('new_name', '').strip()
    if not new_name or '/' in new_name or '\\' in new_name:
        return jsonify({'message': '新名称不能为空，且不能包含 / 或 \\ '})
    try:
        old_full = safe_path(req_path)
        if not os.path.exists(old_full):
            return jsonify({'message': '源文件/文件夹不存在'})
        new_full = os.path.join(os.path.dirname(old_full), new_name)
        if os.path.exists(new_full):
            return jsonify({'message': '目标名称已存在'})
        os.rename(old_full, new_full)
        return jsonify({'message': '重命名成功'})
    except Exception as e:
        return jsonify({'message': f'重命名失败: {e}'})

@app.route('/mkdir', methods=['POST'])
@login_required
def mkdir():
    data = request.get_json()
    req_path = data.get('path', '').strip('/')
    folder_name = data.get('folder', '').strip()
    if not folder_name or '/' in folder_name or '\\' in folder_name:
        return jsonify({'message': '文件夹名称不能为空，且不能包含 / 或 \\ '})
    try:
        parent_path = safe_path(req_path)
        new_folder_path = os.path.join(parent_path, folder_name)
        if os.path.exists(new_folder_path):
            return jsonify({'message': '文件夹已存在'})
        os.makedirs(new_folder_path)
        return jsonify({'message': '新建文件夹成功'})
    except Exception as e:
        return jsonify({'message': f'创建失败: {e}'})

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    upload_files = request.files.getlist('files')
    req_path = request.form.get('path', '').strip('/')
    try:
        upload_dir = safe_path(req_path)
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)
        count = 0
        for file in upload_files:
            if file and file.filename:
                filename = os.path.basename(file.filename)
                if filename.startswith('.'):
                    continue
                save_path = os.path.join(upload_dir, filename)
                file.save(save_path)
                count += 1
        return jsonify({'message': f'成功上传 {count} 个文件'})
    except Exception as e:
        return jsonify({'message': f'上传失败: {e}'})

@app.route('/move', methods=['POST'])
@login_required
def move():
    data = request.get_json()
    source = data.get('source', '').strip('/')
    target = data.get('target', '').strip('/')
    try:
        source_full = safe_path(source)
        if os.path.isdir(target_full := safe_path(target)):
            target_full = os.path.join(target_full, os.path.basename(source_full))
        else:
            target_full = safe_path(target)
        if not os.path.exists(source_full):
            return jsonify({'message': '源文件/文件夹不存在'})
        if os.path.exists(target_full):
            return jsonify({'message': '目标位置已存在同名文件/文件夹'})
        os.rename(source_full, target_full)
        return jsonify({'message': '移动成功'})
    except Exception as e:
        return jsonify({'message': f'移动失败: {e}'})

@app.route('/preview')
@login_required
def preview():
    req_path = request.args.get('path', '').strip('/')
    try:
        full_path = safe_path(req_path)
        if not os.path.exists(full_path):
            return "文件未找到", 404
        return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path))
    except Exception:
        return "非法路径或文件不存在", 403

@app.route('/video')
@login_required
def video():
    req_path = request.args.get('path', '').strip('/')
    try:
        full_path = safe_path(req_path)
        if not os.path.exists(full_path):
            return "文件未找到", 404
        return render_template_string("""
        <!doctype html>
        <html lang="zh-CN">
        <head><meta charset="utf-8"><title>视频预览</title></head>
        <body style="background:#000;color:#fff;">
        <video src="/preview?path={{ path }}" controls autoplay style="width:100%;height:auto;"></video>
        </body>
        </html>
        """, path=req_path)
    except Exception:
        return "非法路径或文件不存在", 403

@app.route('/audio')
@login_required
def audio():
    req_path = request.args.get('path', '').strip('/')
    try:
        full_path = safe_path(req_path)
        if not os.path.exists(full_path):
            return "文件未找到", 404
        return render_template_string("""
        <!doctype html>
        <html lang="zh-CN">
        <head><meta charset="utf-8"><title>音频预览</title></head>
        <body style="background:#000;color:#fff;">
        <audio src="/preview?path={{ path }}" controls autoplay style="width:100%;"></audio>
        </body>
        </html>
        """, path=req_path)
    except Exception:
        return "非法路径或文件不存在", 403
@app.route('/edit', methods=['GET', 'POST'])
@login_required
def edit():
    req_path = request.args.get('path', '').strip('/')
    if request.method == 'GET':
        try:
            full_path = safe_path(req_path)
            if not os.path.isfile(full_path):
                return "文件未找到", 404
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return render_template_string("""
            <!doctype html>
            <html lang="zh-CN">
            <head><meta charset="utf-8"><title>编辑文件</title></head>
            <body style="background:#000;color:#f44;font-family:sans-serif;">
            <h2>编辑文件：{{ filename }}</h2>
            <form method="post">
            <textarea name="content" style="width:100%;height:80vh;background:#111;color:#fff;font-size:16px;border:none;outline:none;">{{ content }}</textarea><br>
            <button type="submit" style="padding:10px 20px;margin-top:10px;">保存</button>
            </form>
            </body>
            </html>
            """, filename=os.path.basename(full_path), content=content)
        except Exception:
            return "非法路径或文件不存在", 403
    else:
        new_content = request.form.get('content', '')
        try:
            full_path = safe_path(req_path)
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            flash('保存成功')
            return redirect(url_for('edit', path=req_path))
        except Exception:
            return "保存失败", 500
# -----------------------------------------------------------------------------
# 搜索文件功能
@app.route('/search')
@login_required
def search():
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])
    results = []
    for root, dirs, files in os.walk(ROOT_DIR):
        for name in dirs + files:
            full_path = os.path.join(root, name)
            if name.startswith('.'):
                continue
            lcs_length = longest_common_subsequence_length(query.lower(), name.lower())
            if lcs_length > 0:
                relative_path = os.path.relpath(full_path, ROOT_DIR)
                item_type = 'folder' if os.path.isdir(full_path) else 'file'
                results.append({'name': name, 'path': '/' + relative_path.replace('\\', '/'), 'type': item_type, 'score': lcs_length})
    results.sort(key=lambda x: x['score'], reverse=True)
    return jsonify(results)

def longest_common_subsequence_length(s1, s2):
    m = len(s1)
    n = len(s2)
    dp = [[0]*(n+1) for _ in range(m+1)]  # 初始化 DP 数组
    for i in range(m):
        for j in range(n):
            if s1[i] == s2[j]:
                dp[i+1][j+1] = dp[i][j]+1
            else:
                dp[i+1][j+1] = max(dp[i+1][j], dp[i][j+1])
    return dp[m][n]
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)  # 启动应用
