from flask import Flask, request, jsonify, send_from_directory, abort, render_template_string
import os, shutil
from werkzeug.utils import secure_filename
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

auth = HTTPBasicAuth()

# 用户名和密码哈希，密码是 "mypassword"
users = {
    "admin": generate_password_hash("mypassword")
}

@auth.verify_password
def verify_password(username, password):
    if username in users and check_password_hash(users.get(username), password):
        return username
    return None

def is_safe_path(base_dir, path):
    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(path)
    return abs_path.startswith(abs_base)

def secure_path(path):
    parts = path.strip('/').split('/')
    safe_parts = [secure_filename(p) for p in parts if p and p != '..']
    return os.path.join(*safe_parts) if safe_parts else ''

def get_tree(base_path, rel_path=''):
    abs_path = os.path.join(base_path, rel_path)
    tree = []
    try:
        for entry in sorted(os.listdir(abs_path)):
            entry_abs = os.path.join(abs_path, entry)
            entry_rel = os.path.join(rel_path, entry).replace("\\", "/")
            if os.path.isdir(entry_abs):
                tree.append({'name': entry,'path': entry_rel,'type': 'folder','children': get_tree(base_path, entry_rel)})
            else:
                tree.append({'name': entry,'path': entry_rel,'type': 'file'})
    except Exception: pass
    return tree

@app.route('/')
@auth.login_required
def index():
    return render_template_string('''
<!DOCTYPE html><html><head><meta charset="utf-8"><title>文件管理器</title>
<style>
body{font-family:sans-serif;margin:20px;}
ul{list-style:none;padding-left:20px;}
.folder > span::before{content:"▶ ";cursor:pointer;display:inline-block;width:1em;}
.folder.expanded > span::before{content:"▼ ";}
.file,.folder > span{cursor:pointer;}
button{margin-left:6px;font-size:0.9em;}
</style>
</head><body>
<h2>文件管理器</h2><div id="tree"></div>
<script>
function createNode(item){
    let li=document.createElement('li');
    li.className = item.type;
    let span=document.createElement('span');
    span.textContent = item.name;
    li.appendChild(span);
    if(item.type==='folder'){
        li.classList.add('folder');
        span.onclick=()=>{li.classList.toggle('expanded');};
        let ul=document.createElement('ul');
        item.children.forEach(c=>ul.appendChild(createNode(c)));
        ul.style.display='none';
        li.appendChild(ul);
        span.addEventListener('click', e=>{
            e.stopPropagation();
            if(ul.style.display==='none'){ul.style.display='block';li.classList.add('expanded');}
            else{ul.style.display='none';li.classList.remove('expanded');}
        });
    }else{
        span.style.color='blue';
        span.onclick=()=>{window.open('/download/'+encodeURIComponent(item.path));};
    }
    // 操作按钮区域
    let btnRename=document.createElement('button'); btnRename.textContent='重命名';
    btnRename.onclick=async e=>{
        e.stopPropagation();
        let newName=prompt("输入新名称（无路径，仅文件/文件夹名）", item.name);
        if(!newName)return;
        let res=await fetch('/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({src:item.path,new_name:newName})});
        let data=await res.json();
        alert(data.message);
        if(data.success) loadTree();
    };
    let btnDelete=document.createElement('button'); btnDelete.textContent='删除';
    btnDelete.onclick=async e=>{
        e.stopPropagation();
        if(!confirm(`确定删除 "${item.name}"？此操作不可撤销！`))return;
        let res=await fetch('/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path:item.path})});
        let data=await res.json();
        alert(data.message);
        if(data.success) loadTree();
    };
    li.appendChild(btnRename);
    li.appendChild(btnDelete);
    return li;
}
async function loadTree(){
    let res=await fetch('/tree');
    let data=await res.json();
    let container=document.getElementById('tree');
    container.innerHTML='';
    let ul=document.createElement('ul');
    data.tree.forEach(item=>ul.appendChild(createNode(item)));
    container.appendChild(ul);
}
loadTree();
</script>
</body></html>
''')

@app.route('/tree')
@auth.login_required
def list_files():
    return jsonify(tree=get_tree(UPLOAD_FOLDER))

@app.route('/download/<path:filepath>')
@auth.login_required
def download_file(filepath):
    safe_fp = secure_path(filepath)
    abs_fp = os.path.join(UPLOAD_FOLDER, safe_fp)
    if not is_safe_path(UPLOAD_FOLDER, abs_fp) or not os.path.isfile(abs_fp):
        abort(404)
    return send_from_directory(os.path.dirname(abs_fp), os.path.basename(abs_fp), as_attachment=True)

@app.route('/rename', methods=['POST'])
@auth.login_required
def rename_item():
    data = request.get_json()
    if not data or 'src' not in data or 'new_name' not in data:
        return jsonify(success=False,message="参数错误"),400
    src = secure_path(data['src'])
    new_name = secure_filename(data['new_name'])
    if not new_name:
        return jsonify(success=False,message="新名称非法"),400
    src_abs = os.path.join(UPLOAD_FOLDER, src)
    if not is_safe_path(UPLOAD_FOLDER, src_abs) or not os.path.exists(src_abs):
        return jsonify(success=False,message="源路径不存在或非法"),400
    dest_abs = os.path.join(os.path.dirname(src_abs), new_name)
    if os.path.exists(dest_abs):
        return jsonify(success=False,message="目标名称已存在"),400
    try:
        os.rename(src_abs, dest_abs)
        return jsonify(success=True,message="重命名成功")
    except Exception as e:
        return jsonify(success=False,message=f"重命名失败：{e}"),500

@app.route('/delete', methods=['POST'])
@auth.login_required
def delete_item():
    data = request.get_json()
    if not data or 'path' not in data:
        return jsonify(success=False,message="参数错误"),400
    path = secure_path(data['path'])
    abs_path = os.path.join(UPLOAD_FOLDER, path)
    if not is_safe_path(UPLOAD_FOLDER, abs_path) or not os.path.exists(abs_path):
        return jsonify(success=False,message="目标不存在或非法"),400
    try:
        if os.path.isfile(abs_path):
            os.remove(abs_path)
        elif os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            return jsonify(success=False,message="无法删除，未知类型"),400
        return jsonify(success=True,message="删除成功")
    except Exception as e:
        return jsonify(success=False,message=f"删除失败：{e}"),500

if __name__ == '__main__':
    app.run(debug=True)
