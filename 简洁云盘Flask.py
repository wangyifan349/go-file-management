from flask import Flask, request, jsonify, send_from_directory, render_template_string, redirect, url_for, flash  # 导入Flask相关模块
import os  # 文件和路径操作
import sqlite3  # 数据库操作
from werkzeug.security import generate_password_hash, check_password_hash  # 密码加密验证
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required  # 登录管理相关
from datetime import timedelta  # 时间处理

app = Flask(__name__)  # 创建Flask实例
app.secret_key = 'your_secret_key'  # 设置session密钥
app.permanent_session_lifetime = timedelta(days=7)  # session过期时间
login_manager = LoginManager(app)  # 初始化登录管理器
login_manager.login_view = 'login'  # 登录页端点
ROOT_DIRECTORY = os.path.abspath('files')  # 文件根目录绝对路径
os.makedirs(ROOT_DIRECTORY, exist_ok=True)  # 确保根目录存在
DATABASE_PATH = 'users.db'  # SQLite数据库文件路径

def initialize_database():  # 初始化数据库
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            'CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL)'
        )  # 创建用户表（如果不存在）

initialize_database()  # 确保数据库和表存在

@login_manager.user_loader
def load_user(user_id):  # flask-login载入用户函数
    with sqlite3.connect(DATABASE_PATH) as connection:
        row = connection.execute('SELECT id, username FROM users WHERE id=?', (user_id,)).fetchone()  # 查询用户
    if row:
        user_id_value, username_value = row
        # 用字典模拟User对象，必须有id和is_authenticated属性
        user_object = {'id': str(user_id_value), 'username': username_value, 'is_authenticated': True}
        return user_object  # 返回用户字典
    return None

def safe_path(requested_path):  # 检查路径安全，防止目录穿越攻击
    absolute_path = os.path.abspath(os.path.join(ROOT_DIRECTORY, requested_path.strip('/')))  # 计算绝对路径
    if not absolute_path.startswith(ROOT_DIRECTORY):  # 路径必须在根目录内
        raise Exception('非法路径访问')  # 抛异常终止
    return absolute_path  # 返回绝对安全路径

LOGIN_PAGE_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>登录</title></head><body style="background:#000;color:#f44;font-family:sans-serif;">
<h2>登录</h2><form action="{{ url_for('login') }}" method="post">
<label>用户名: <input type="text" name="username" required></label><br><br>
<label>密码: <input type="password" name="password" required></label><br><br>
<button type="submit">登录</button></form>
<p>没有账号？<a href="{{ url_for('register') }}" style="color:#f66;">注册</a></p>
{% with messages = get_flashed_messages() %}{% if messages %}<ul style="color:#f88;">{% for message in messages %}<li>{{ message }}</li>{% endfor %}</ul>{% endif %}{% endwith %}
</body></html>"""  # 登录页面HTML，带表单和flash消息

REGISTER_PAGE_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>注册</title></head><body style="background:#000;color:#f44;font-family:sans-serif;">
<h2>注册</h2><form action="{{ url_for('register') }}" method="post">
<label>用户名: <input type="text" name="username" required></label><br><br>
<label>密码: <input type="password" name="password" required></label><br><br>
<label>确认密码: <input type="password" name="password2" required></label><br><br>
<button type="submit">注册</button></form>
<p>已有账号？<a href="{{ url_for('login') }}" style="color:#f66;">登录</a></p>
{% with messages = get_flashed_messages() %}{% if messages %}<ul style="color:#f88;">{% for message in messages %}<li>{{ message }}</li>{% endfor %}</ul>{% endif %}{% endwith %}
</body></html>"""  # 注册页面HTML

@app.route('/login', methods=['GET', 'POST'])
def login():  # 登录接口
    if current_user.is_authenticated:  # 已登陆重定向首页
        return redirect(url_for('index'))
    if request.method == 'POST':  # 提交登录表单
        username_value = request.form.get('username', '').strip()  # 获取用户名
        password_value = request.form.get('password', '')  # 获取密码
        with sqlite3.connect(DATABASE_PATH) as connection:
            row = connection.execute(
                'SELECT id, password_hash FROM users WHERE username=?', (username_value,)
            ).fetchone()  # 查询用户数据
        if row:
            user_identifier, password_hash_value = row
            if check_password_hash(password_hash_value, password_value):  # 验证密码
                user_instance = {'id': str(user_identifier), 'username': username_value, 'is_authenticated': True}  # 构造用户字典
                login_user(user_instance)  # 登录用户
                flash('登录成功！')  # 提示
                return redirect(url_for('index'))  # 跳转首页
        flash('用户名或密码错误')  # 认证失败提示
    return render_template_string(LOGIN_PAGE_HTML)  # 返回登录页面

@app.route('/register', methods=['GET', 'POST'])
def register():  # 注册接口
    if current_user.is_authenticated:  # 已登录重定向首页
        return redirect(url_for('index'))
    if request.method == 'POST':  # 提交表单
        username_value = request.form.get('username', '').strip()
        password_value = request.form.get('password', '')
        password_confirm_value = request.form.get('password2', '')
        if not username_value or not password_value:
            flash('用户名和密码不能为空')
        elif password_value != password_confirm_value:
            flash('两次密码输入不一致')
        else:
            with sqlite3.connect(DATABASE_PATH) as connection:
                exists = connection.execute(
                    'SELECT id FROM users WHERE username=?', (username_value,)
                ).fetchone()  # 查询是否已存在
                if exists:
                    flash('用户名已被注册')
                else:
                    hashed_password = generate_password_hash(password_value)  # 哈希密码
                    connection.execute(
                        'INSERT INTO users (username, password_hash) VALUES (?, ?)',
                        (username_value, hashed_password)
                    )  # 插入新用户
                    flash('注册成功，请登录')
                    return redirect(url_for('login'))
    return render_template_string(REGISTER_PAGE_HTML)  # 注册页面

@app.route('/logout')
@login_required
def logout():  # 登出接口
    logout_user()  # 登出当前用户
    flash('已登出')  # 提示
    return redirect(url_for('login'))  # 重定向登录页面

MAIN_PAGE_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>云盘文件管理</title>
<style>body{background:#000;color:#f44;font-family:sans-serif;user-select:none;padding:1rem;}ul{list-style:none;padding-left:1.2rem;margin:0;}li{padding:0.2rem 0;cursor:pointer;}li.folder::before{content:"📁 ";}li.file::before{content:"📄 ";}li.up{color:#f88;font-weight:700;}li.up:hover{color:#faa;}#path{font-weight:700;margin-bottom:0.5rem;user-select:text;}
#searchBar{margin-bottom:1rem;}#searchInput{width:80%;padding:0.4rem;border:none;border-radius:4px;background:#111;color:#f44;}
#searchButton{padding:0.4rem 0.8rem;margin-left:0.5rem;border:none;border-radius:4px;background:#f44;color:#000;cursor:pointer;}
</style></head><body><h1>云盘文件管理</h1>
<div id="userInfo">用户: {{ current_user.username }} <button onclick="logout()">退出登录</button></div>
<div id="searchBar"><input id="searchInput" placeholder="搜索文件夹或文件" autocomplete="off"><button id="searchButton">搜索</button></div>
<div id="path"></div>
<div id="fileList"></div>
<script>
let currentPath = '';
function ajax(url, options={}){return fetch(url, options).then(r=>r.json());}
function renderList(data){
    const pathElem = document.getElementById('path');
    pathElem.textContent = '路径：/' + currentPath;
    let html = '<ul>';
    if(currentPath){
        const up = currentPath.split('/').slice(0,-1).join('/');
        html += '<li class="up" onclick="navigateTo(\''+up+'\')">⬆ 上级目录</li>';
    }
    data.forEach(item => {
        html += `<li class="${item.type}" ondblclick="openItem('${item.name}', '${item.type}')">${item.name}</li>`;
    });
    html += '</ul>';
    document.getElementById('fileList').innerHTML = html;
}
function listFiles(path=''){
    ajax('/list?path='+encodeURIComponent(path)).then(data=>{currentPath=path;renderList(data);});
}
function openItem(name,type){
    if(type==='folder'){navigateTo(currentPath?currentPath+'/'+name:name);}
    else{
        const ext=name.split('.').pop().toLowerCase();
        const p=currentPath?currentPath+'/'+name:name;
        if(['jpg','jpeg','png','gif','bmp','svg','webp'].includes(ext)){window.open('/preview?path='+encodeURIComponent(p));}
        else if(['mp4','webm','ogg','mov'].includes(ext)){window.open('/video?path='+encodeURIComponent(p));}
        else if(['mp3','wav','flac'].includes(ext)){window.open('/audio?path='+encodeURIComponent(p));}
        else if(['txt','py','js','css','html','md','json','xml','csv','log','ini','conf','sh','bat'].includes(ext)){window.open('/edit?path='+encodeURIComponent(p));}
        else{window.open('/download?path='+encodeURIComponent(p));}
    }
}
function navigateTo(path){listFiles(path);}
function logout(){window.location='/logout';}
document.getElementById('searchButton').onclick = function(){
    let q=document.getElementById('searchInput').value.trim();
    if(!q){alert('请输入搜索关键词');return;}
    ajax('/search?q='+encodeURIComponent(q)).then(data=>{
        document.getElementById('path').textContent='搜索结果';
        let html='<ul>';
        data.forEach(item=>{html+=`<li class="${item.type}" ondblclick="openSearchItem('${item.path}', '${item.type}')">${item.name}</li>`;});
        html+='</ul>';
        document.getElementById('fileList').innerHTML=html;
    });
};
function openSearchItem(path,type){
    if(type==='folder'){
        let p=path.startsWith('/')?path.slice(1):path;
        listFiles(p);
    } else window.open('/download?path='+encodeURIComponent(path.startsWith('/')?path.slice(1):path));
}
listFiles();
</script></body></html>"""  # 主页面HTML和JS脚本，支持浏览、打开、搜索、播放、编辑等

@app.route('/')
@login_required
def index():  # 主页，显示文件管理界面
    return render_template_string(MAIN_PAGE_HTML)  # 渲染主页面HTML

@app.route('/list')
@login_required
def list_files():  # 列出指定目录文件夹和文件
    requested_path = request.args.get('path', '').strip('/')  # 获取请求路径参数，去除前后斜杠
    try:
        absolute_path = safe_path(requested_path)  # 获取安全的绝对路径
        if not os.path.isdir(absolute_path):
            return jsonify([])  # 不是目录返回空列表
        entries = []
        for entry_name in sorted(os.listdir(absolute_path)):  # 遍历目录项升序排序
            if entry_name.startswith('.'):
                continue  # 跳过隐藏文件夹和文件
            full_entry_path = os.path.join(absolute_path, entry_name)
            entry_type = 'folder' if os.path.isdir(full_entry_path) else 'file'  # 判断类型
            entries.append({'name': entry_name, 'type': entry_type})  # 添加到列表
        return jsonify(entries)  # 返回JSON数组
    except Exception:
        return jsonify([])  # 出错返回空

@app.route('/download')
@login_required
def download_file():  # 下载文件接口
    requested_path = request.args.get('path', '').strip('/')
    try:
        absolute_path = safe_path(requested_path)
        if not os.path.isfile(absolute_path):
            return "文件未找到", 404
        directory = os.path.dirname(absolute_path)
        filename = os.path.basename(absolute_path)
        return send_from_directory(directory, filename, as_attachment=True)  # 附件形式下载
    except Exception:
        return "非法路径", 403

@app.route('/preview')
@login_required
def preview_file():  # 直接预览图片等文件
    requested_path = request.args.get('path', '').strip('/')
    try:
        absolute_path = safe_path(requested_path)
        if not os.path.isfile(absolute_path):
            return "文件未找到", 404
        directory = os.path.dirname(absolute_path)
        filename = os.path.basename(absolute_path)
        return send_from_directory(directory, filename)  # 直接返回文件内容
    except Exception:
        return "非法路径", 403

@app.route('/video')
@login_required
def play_video():  # 视频播放页面
    requested_path = request.args.get('path', '').strip('/')
    try:
        absolute_path = safe_path(requested_path)
        if not os.path.isfile(absolute_path):
            return "文件未找到", 404
        return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>视频播放</title></head><body style="background:#000;color:#fff;margin:0">
<video src="/preview?path={requested_path}" controls autoplay style="width:100vw;height:100vh;"></video></body></html>"""  # 内嵌播放器
    except Exception:
        return "非法路径", 403

@app.route('/audio')
@login_required
def play_audio():  # 音频播放页面
    requested_path = request.args.get('path', '').strip('/')
    try:
        absolute_path = safe_path(requested_path)
        if not os.path.isfile(absolute_path):
            return "文件未找到", 404
        return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>音频播放</title></head><body style="background:#000;color:#fff;margin:0">
<audio src="/preview?path={requested_path}" controls autoplay style="width:100vw;"></audio></body></html>"""  # 音频播放器
    except Exception:
        return "非法路径", 403

@app.route('/edit', methods=['GET', 'POST'])
@login_required
def edit_file():  # 文本文件编辑接口（支持GET显示编辑，POST保存）
    requested_path = request.args.get('path', '').strip('/')
    absolute_path = safe_path(requested_path)
    if request.method == 'GET':
        if not os.path.isfile(absolute_path):
            return "文件未找到", 404
        try:
            with open(absolute_path, encoding='utf-8') as file:
                file_content = file.read()  # 读取文件内容
            return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>编辑</title></head><body style="background:#000;color:#f44;">
<h2>编辑：{os.path.basename(absolute_path)}</h2><form method="post"><textarea name="content" style="width:100%;height:80vh;background:#111;color:#fff;border:none;">{file_content}</textarea><br><button>保存</button></form></body></html>"""
        except Exception:
            return "打开文件失败", 500
    else:
        content = request.form.get('content', '')
        try:
            with open(absolute_path, 'w', encoding='utf-8') as file:
                file.write(content)  # 保存内容
            flash('保存成功')  # 提示
            return redirect(url_for('edit_file', path=requested_path))  # 重载编辑页
        except Exception:
            return "保存失败", 500

@app.route('/delete', methods=['POST'])
@login_required
def delete_file_or_folder():  # 删除文件或文件夹
    data = request.get_json()
    requested_path = data.get('path', '').strip('/')
    if not requested_path:
        return jsonify({'message': '路径不能为空'})
    absolute_path = safe_path(requested_path)
    if not os.path.exists(absolute_path):
        return jsonify({'message': '不存在'})
    try:
        if os.path.isdir(absolute_path):
            if os.listdir(absolute_path):
                return jsonify({'message': '文件夹不为空，无法删除'})  # 非空文件夹拒绝删除
            os.rmdir(absolute_path)  # 删除文件夹
        else:
            os.remove(absolute_path)  # 删除文件
        return jsonify({'message': '删除成功'})
    except Exception as exception:
        return jsonify({'message': '删除失败:' + str(exception)})

@app.route('/rename', methods=['POST'])
@login_required
def rename_file_or_folder():  # 重命名文件或文件夹
    data = request.get_json()
    requested_path = data.get('path', '').strip('/')
    new_name = data.get('new_name', '').strip()
    if not new_name or '/' in new_name or '\\' in new_name:
        return jsonify({'message': '非法新名称'})  # 名称非法
    old_absolute_path = safe_path(requested_path)
    if not os.path.exists(old_absolute_path):
        return jsonify({'message': '源不存在'})
    new_absolute_path = os.path.join(os.path.dirname(old_absolute_path), new_name)
    if os.path.exists(new_absolute_path):
        return jsonify({'message': '目标已存在'})
    try:
        os.rename(old_absolute_path, new_absolute_path)  # 改名
        return jsonify({'message': '重命名成功'})
    except Exception as exception:
        return jsonify({'message': '重命名失败:' + str(exception)})

@app.route('/mkdir', methods=['POST'])
@login_required
def create_folder():  # 新建文件夹
    data = request.get_json()
    requested_path = data.get('path', '').strip('/')
    folder_name = data.get('folder', '').strip()
    if not folder_name or '/' in folder_name or '\\' in folder_name:
        return jsonify({'message': '非法文件夹名'})  # 非法文件夹名
    base_absolute_path = safe_path(requested_path)
    new_folder_path = os.path.join(base_absolute_path, folder_name)
    if os.path.exists(new_folder_path):
        return jsonify({'message': '文件夹已存在'})
    try:
        os.makedirs(new_folder_path)  # 创建目录
        return jsonify({'message': '新建成功'})
    except Exception as exception:
        return jsonify({'message': '创建失败:' + str(exception)})

@app.route('/upload', methods=['POST'])
@login_required
def upload_files():  # 上传文件
    uploaded_files = request.files.getlist('files')
    requested_path = request.form.get('path', '').strip('/')
    base_absolute_path = safe_path(requested_path)
    if not os.path.exists(base_absolute_path):
        os.makedirs(base_absolute_path)  # 确保目录存在
    uploaded_count = 0
    for uploaded_file in uploaded_files:
        file_name = os.path.basename(uploaded_file.filename)
        if not file_name or file_name.startswith('.'):
            continue  # 忽略隐藏文件名或空名
        try:
            uploaded_file.save(os.path.join(base_absolute_path, file_name))  # 保存文件
            uploaded_count += 1
        except Exception:
            pass  # 保存失败忽略
    return jsonify({'message': f'上传{uploaded_count}个文件成功'})

@app.route('/move', methods=['POST'])
@login_required
def move_file_or_folder():  # 移动/剪切文件或文件夹
    data = request.get_json()
    source_path = data.get('source', '').strip('/')
    target_path = data.get('target', '').strip('/')
    source_absolute_path = safe_path(source_path)
    target_absolute_path = safe_path(target_path)
    if os.path.isdir(target_absolute_path):
        target_absolute_path = os.path.join(target_absolute_path, os.path.basename(source_absolute_path))  # 补全目标文件名
    if not os.path.exists(source_absolute_path):
        return jsonify({'message': '源不存在'})
    if os.path.exists(target_absolute_path):
        return jsonify({'message': '目标已存在同名对象'})
    try:
        os.rename(source_absolute_path, target_absolute_path)  # 移动
        return jsonify({'message': '移动成功'})
    except Exception as exception:
        return jsonify({'message': '移动失败:' + str(exception)})

@app.route('/search')
@login_required
def search_files():  # 搜索文件和文件夹(使用最长公共子序列匹配)
    keyword = request.args.get('q', '').lower()
    if not keyword:
        return jsonify([])
    result_list = []
    for root_directory, directory_names, file_names in os.walk(ROOT_DIRECTORY):
        for entry_name in directory_names + file_names:
            if entry_name.startswith('.'):
                continue
            lcs_length = longest_common_subsequence_length(keyword, entry_name.lower())
            if lcs_length > 0:
                full_entry_path = os.path.join(root_directory, entry_name)
                relative_path = '/' + os.path.relpath(full_entry_path, ROOT_DIRECTORY).replace('\\', '/')
                entry_type = 'folder' if os.path.isdir(full_entry_path) else 'file'
                result_list.append({'name': entry_name, 'path': relative_path, 'type': entry_type, 'score': lcs_length})
    result_list.sort(key=lambda item: item['score'], reverse=True)
    return jsonify(result_list)  # 返回排序后的搜索结果

def longest_common_subsequence_length(string_a, string_b):  # 计算两个字符串最长公共子序列长度
    length_a = len(string_a)
    length_b = len(string_b)
    dp_table = [[0] * (length_b + 1) for _ in range(length_a + 1)]  # 动态规划表
    for index_a in range(length_a):
        for index_b in range(length_b):
            if string_a[index_a] == string_b[index_b]:
                dp_table[index_a + 1][index_b + 1] = dp_table[index_a][index_b] + 1
            else:
                dp_table[index_a + 1][index_b + 1] = max(dp_table[index_a][index_b + 1], dp_table[index_a + 1][index_b])
    return dp_table[length_a][length_b]  # 返回LCS长度

if __name__ == '__main__':  # 启动服务
    app.run(host='0.0.0.0', port=5000, debug=True)
