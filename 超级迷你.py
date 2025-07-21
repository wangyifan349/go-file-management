from flask import Flask, request, send_from_directory, render_template_string, jsonify
import os, shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# ——————— 配置 ———————
STORAGE_ROOT = os.path.abspath('storage')       # 文件存储根目录
ALLOWED_EXTENSIONS = None                       # None = 允许所有扩展名
os.makedirs(STORAGE_ROOT, exist_ok=True)

# ——————— 工具函数 ———————
def is_allowed_file(fn):
    if ALLOWED_EXTENSIONS is None: return True
    ext = fn.rsplit('.', 1)[-1].lower()
    return '.' in fn and ext in ALLOWED_EXTENSIONS

def safe_path(rel):
    """禁止路径穿越，确保最终路径仍在 STORAGE_ROOT 之下"""
    full = os.path.abspath(os.path.join(STORAGE_ROOT, rel))
    if not full.startswith(STORAGE_ROOT):
        raise ValueError('非法路径')
    return full

def build_tree(cur):
    """递归构建文件夹／文件树"""
    out = []
    for name in sorted(os.listdir(cur)):
        full = os.path.join(cur, name)
        rel = os.path.relpath(full, STORAGE_ROOT).replace('\\','/')
        if rel == '.': rel = ''
        if os.path.isdir(full):
            out.append({'type':'folder','name':name,'path':rel,'children':build_tree(full)})
        else:
            out.append({'type':'file','name':name,'path':rel})
    return out

def lcs_length(a, b):
    """计算最长公共子序列长度"""
    m, n = len(a), len(b)
    dp = [[0]*(n+1) for _ in range(m+1)]
    for i in range(m-1, -1, -1):
        for j in range(n-1, -1, -1):
            dp[i][j] = dp[i+1][j+1]+1 if a[i]==b[j] else max(dp[i+1][j], dp[i][j+1])
    return dp[0][0]

# ——————— 路由 ———————
@app.route('/')
def index():
    tree = build_tree(STORAGE_ROOT)
    return render_template_string(PAGE, tree=tree)

@app.route('/download/<path:rel>')
def download(rel):
    full = safe_path(rel)
    if os.path.isdir(full): return "Cannot download folder", 400
    d, fn = os.path.split(full)
    return send_from_directory(d, fn, as_attachment=True)

@app.route('/upload', methods=['POST'])
def upload():
    tgt = safe_path(request.form.get('target',''))
    f = request.files.get('file')
    if not f or f.filename=='': return jsonify(error='No file'), 400
    if not is_allowed_file(f.filename): return jsonify(error='Type not allowed'),400
    fn = secure_filename(f.filename)
    f.save(os.path.join(tgt, fn))
    return jsonify(ok=True)

@app.route('/mkdir', methods=['POST'])
def mkdir():
    data = request.get_json() or {}
    tgt = safe_path(data.get('target',''))
    name = data.get('name','').strip()
    if not name: return jsonify(error='Name required'),400
    newd = os.path.join(tgt, secure_filename(name))
    try: os.makedirs(newd, exist_ok=False)
    except FileExistsError: return jsonify(error='Exists'),400
    return jsonify(ok=True)

@app.route('/rename', methods=['POST'])
def rename():
    data = request.get_json() or {}
    old = safe_path(data.get('path',''))
    newn = data.get('newName','').strip()
    if not newn: return jsonify(error='New name?'),400
    dst = os.path.join(os.path.dirname(old), secure_filename(newn))
    if os.path.exists(dst): return jsonify(error='Exists'),400
    os.rename(old, dst); return jsonify(ok=True)

@app.route('/delete', methods=['POST'])
def delete():
    data = request.get_json() or {}
    p = safe_path(data.get('path',''))
    if not os.path.exists(p): return jsonify(error='Not found'),404
    shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    return jsonify(ok=True)

@app.route('/move', methods=['POST'])
def move():
    data = request.get_json() or {}
    src = safe_path(data.get('src','')); dst = safe_path(data.get('dest',''))
    if not os.path.exists(src) or not os.path.isdir(dst): return jsonify(error='Bad'),400
    trg = os.path.join(dst, os.path.basename(src))
    if os.path.exists(trg): return jsonify(error='Conflict'),400
    shutil.move(src, trg); return jsonify(ok=True)

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json() or {}
    q = data.get('query','').strip().lower()
    if not q: return jsonify(error='Query?'),400
    res=[]; thr=0.5
    for root, _, files in os.walk(STORAGE_ROOT):
        rel = os.path.relpath(root, STORAGE_ROOT).replace('\\','/')
        if rel=='.': rel=''
        fn = os.path.basename(root)
        if lcs_length(fn.lower(),q)/len(q)>=thr:
            res.append({'type':'folder','name':fn,'path':rel})
        for f in files:
            if lcs_length(f.lower(),q)/len(q)>=thr:
                p = (rel+'/'+f).lstrip('./')
                res.append({'type':'file','name':f,'path':p})
    return jsonify(results=res)

# ——————— 启动 ———————
if __name__=='__main__':
    app.run(debug=True, port=5000)

# ——————— 前端模板 ———————
PAGE = """
<!doctype html><html><head><meta charset="utf-8"><title>FileManager</title>
<style>body{font-family:sans-serif;padding:1rem}ul,li{list-style:none;margin:0;padding:0}
.tree{margin-left:1rem}.item{padding:.2rem;cursor:pointer}.item:hover{background:#f0f8ff}
.folder>.item::before{content:"📁 "}.file>.item::before{content:"📄 "}
.selected{background:#d0e4f5}#toolbar{margin-bottom:1rem}button{margin-right:.5rem}
#search-results{border-top:1px solid #ddd;padding-top:1rem}
</style></head><body>
<div id="toolbar">
  <button id="btn-refresh">Refresh</button>
  <button id="btn-new-folder">New Folder</button>
  <input type="file" id="file-upload">
  <input type="text" id="search-input" placeholder="Search...">
  <button id="btn-search">Search</button>
</div>
<div id="tree-container"></div>
<div id="search-results"></div>
<script>
let selectedPath="";
function renderTree(cont,nodes){
  cont.innerHTML="";const ul=document.createElement("ul");ul.className="tree";
  nodes.forEach(n=>{
    const li=document.createElement("li");li.className=n.type;
    const d=document.createElement("div");d.className="item";d.textContent=n.name;
    d.dataset.path=n.path;
    d.onclick=e=>{e.stopPropagation();document.querySelectorAll(".selected")
      .forEach(x=>x.classList.remove("selected"));d.classList.add("selected");
      selectedPath=n.path};
    d.oncontextmenu=e=>{e.preventDefault();selectedPath=n.path;
      const a=prompt("输入 d 删除，r 重命名");if(a==="d")deleteItem(n.path);
      if(a==="r")renameItem(n.path)};
    d.draggable=true;d.ondragstart=e=>e.dataTransfer.setData("text/plain",n.path);
    d.ondragover=e=>e.preventDefault();
    d.ondrop=e=>{e.preventDefault();
      const src=e.dataTransfer.getData("text/plain");
      const dst=n.type==="folder"?n.path:n.path.split("/").slice(0,-1).join("/");
      moveItem(src,dst)
    };
    li.appendChild(d);
    if(n.type==="folder"&&n.children.length>0) renderTree(li,n.children);
    ul.appendChild(li);
  });
  cont.appendChild(ul);
}
function api(u,d,m="POST"){return fetch(u,{
  method:m,headers:{"Content-Type":"application/json"},
  body:d?JSON.stringify(d):null
}).then(r=>r.json())}
function refresh(){location.reload()}
function createFolder(){
  const n=prompt("New folder:");if(!n)return;
  api("/mkdir",{target:selectedPath,name:n}).then(r=>r.ok?refresh():alert(r.error))
}
function deleteItem(p){
  if(!confirm("Del "+p+" ?"))return;
  api("/delete",{path:p}).then(r=>r.ok?refresh():alert(r.error))
}
function renameItem(p){
  const n=prompt("New name:");if(!n)return;
  api("/rename",{path:p,newName:n}).then(r=>r.ok?refresh():alert(r.error))
}
function moveItem(s,d){
  if(!confirm(`Move ${s} -> ${d}?`))return;
  api("/move",{src:s,dest:d}).then(r=>r.ok?refresh():alert(r.error))
}
document.getElementById("file-upload").onchange=function(){
  if(!selectedPath)return alert("Select folder first");
  const f=this.files[0],fd=new FormData();
  fd.append("file",f);fd.append("target",selectedPath);
  fetch("/upload",{method:"POST",body:fd})
    .then(r=>r.json()).then(r=>r.ok?refresh():alert(r.error))
}
function renderSearch(res){
  const c=document.getElementById("search-results");
  c.innerHTML="<h4>Results:</h4>";
  if(!res.length){c.innerHTML+="<p>No matches.</p>";return}
  const ul=document.createElement("ul");
  res.forEach(it=>{
    const li=document.createElement("li");
    li.textContent=(it.type==="folder"?"📁 ":"📄 ")+it.name+"("+it.path+")";
    li.style.cursor="pointer";li.onclick=()=>{
      if(it.type==="file")window.location="/download/"+encodeURIComponent(it.path);
      else{
        const e=document.querySelector(`.item[data-path="${it.path}"]`);
        if(e){e.click();e.scrollIntoView({behavior:"smooth",block:"center"})}
      }
    };
    ul.appendChild(li)
  });
  c.appendChild(ul)
}
document.getElementById("btn-search").onclick=()=>{
  const q=document.getElementById("search-input").value.trim();
  if(!q)return alert("请输入关键词");
  fetch("/search",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({query:q})})
    .then(r=>r.json()).then(d=>d.error?alert(d.error):renderSearch(d.results))
}
document.getElementById("btn-refresh").onclick=refresh;
document.getElementById("btn-new-folder").onclick=createFolder;
renderTree(document.getElementById("tree-container"), {{ tree|tojson }});
</script></body></html>
"""
