from flask import Flask, request, send_from_directory, render_template_string, jsonify
import os, shutil
from functools import wraps
from werkzeug.utils import secure_filename

app = Flask(__name__)
STORAGE_ROOT = os.path.abspath('storage'); os.makedirs(STORAGE_ROOT, exist_ok=True)
ALLOWED_EXTENSIONS = None  # None = allow all

def error_response(message, status_code=400): return jsonify(error=message), status_code

def require_json(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try: body = request.get_json() or {}
        except: return error_response('Invalid JSON')
        return func(body, *args, **kwargs)
    return wrapper

def secure_path(relative_path):
    absolute_path = os.path.abspath(os.path.join(STORAGE_ROOT, relative_path or ''))
    if not absolute_path.startswith(STORAGE_ROOT): raise ValueError
    return absolute_path

def extension_allowed(filename):
    if ALLOWED_EXTENSIONS is None: return True
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS

def build_tree(current_directory):
    tree = []
    for entry in sorted(os.listdir(current_directory)):
        full_entry = os.path.join(current_directory, entry)
        relative_entry = os.path.relpath(full_entry, STORAGE_ROOT).replace('\\','/') or ''
        if os.path.isdir(full_entry):
            tree.append({
                'type':'folder',
                'name':entry,
                'path':relative_entry,
                'children':build_tree(full_entry)
            })
        else:
            tree.append({'type':'file','name':entry,'path':relative_entry})
    return tree

def longest_common_subsequence_length(a,b):
    length_a, length_b = len(a), len(b)
    dp = [[0]*(length_b+1) for _ in range(length_a+1)]
    for i in range(length_a-1,-1,-1):
        for j in range(length_b-1,-1,-1):
            if a[i]==b[j]:
                dp[i][j] = dp[i+1][j+1] + 1
            else:
                dp[i][j] = max(dp[i+1][j], dp[i][j+1])
    return dp[0][0]

@app.route('/')
def index():
    return render_template_string(PAGE, tree=build_tree(STORAGE_ROOT))

@app.route('/download/<path:relative_path>')
def download(relative_path):
    try: full_path = secure_path(relative_path)
    except: return error_response('Illegal path')
    if os.path.isdir(full_path): return error_response('Not a file')
    directory, filename = os.path.split(full_path)
    return send_from_directory(directory, filename, as_attachment=True)

@app.route('/upload', methods=['POST'])
def upload_file():
    target_folder = request.form.get('target','')
    try: destination = secure_path(target_folder)
    except: return error_response('Illegal path')
    uploaded_file = request.files.get('file')
    if not uploaded_file or not uploaded_file.filename: return error_response('No file')
    if not extension_allowed(uploaded_file.filename): return error_response('Type not allowed')
    safe_name = secure_filename(uploaded_file.filename)
    uploaded_file.save(os.path.join(destination, safe_name))
    return jsonify(ok=True)

@app.route('/mkdir', methods=['POST'])
@require_json
def make_folder(request_body):
    target_folder = request_body.get('target','')
    folder_name = (request_body.get('name') or '').strip()
    if not folder_name: return error_response('Name required')
    try: parent_directory = secure_path(target_folder)
    except: return error_response('Illegal path')
    new_directory = os.path.join(parent_directory, secure_filename(folder_name))
    try: os.makedirs(new_directory)
    except FileExistsError: return error_response('Exists')
    return jsonify(ok=True)

@app.route('/rename', methods=['POST'])
@require_json
def rename_item(request_body):
    original_path = request_body.get('path','')
    new_name = (request_body.get('newName') or '').strip()
    if not new_name: return error_response('NewName required')
    try: original_full = secure_path(original_path)
    except: return error_response('Illegal path')
    renamed_full = os.path.join(os.path.dirname(original_full), secure_filename(new_name))
    if os.path.exists(renamed_full): return error_response('Exists')
    os.rename(original_full, renamed_full)
    return jsonify(ok=True)

@app.route('/delete', methods=['POST'])
@require_json
def delete_item(request_body):
    relative_path = request_body.get('path','')
    try: full_path = secure_path(relative_path)
    except: return error_response('Illegal path')
    if not os.path.exists(full_path): return error_response('Not found',404)
    if os.path.isdir(full_path): shutil.rmtree(full_path)
    else: os.remove(full_path)
    return jsonify(ok=True)

@app.route('/move', methods=['POST'])
@require_json
def move_item(request_body):
    source_path = request_body.get('src','')
    destination_path = request_body.get('dest','')
    try: source_full = secure_path(source_path); destination_full = secure_path(destination_path)
    except: return error_response('Illegal path')
    if not os.path.exists(source_full) or not os.path.isdir(destination_full): return error_response('Bad')
    target_full = os.path.join(destination_full, os.path.basename(source_full))
    if os.path.exists(target_full): return error_response('Conflict')
    shutil.move(source_full, target_full)
    return jsonify(ok=True)

@app.route('/search', methods=['POST'])
@require_json
def search_items(request_body):
    query = (request_body.get('query') or '').strip().lower()
    if not query: return error_response('Query required')
    results = []; threshold = 0.5
    for directory, _, files in os.walk(STORAGE_ROOT):
        relative_directory = os.path.relpath(directory, STORAGE_ROOT).replace('\\','/') or ''
        folder_name = os.path.basename(directory).lower()
        if longest_common_subsequence_length(folder_name, query)/len(query) >= threshold:
            results.append({'type':'folder','name':os.path.basename(directory),'path':relative_directory})
        for filename in files:
            lower_filename = filename.lower()
            if longest_common_subsequence_length(lower_filename, query)/len(query) >= threshold:
                file_relative = (relative_directory+'/'+filename).lstrip('/')
                results.append({'type':'file','name':filename,'path':file_relative})
    return jsonify(results=results)

if __name__=='__main__':
    app.run(debug=True, port=5000)

PAGE = """
<!doctype html><html><head><meta charset="utf-8"><title>FileManager</title>
<style>body{font-family:sans-serif;padding:1rem}ul,li{list-style:none;margin:0;padding:0}.tree{margin-left:1rem}
.item{padding:.2rem;cursor:pointer}.item:hover{background:#f0f8ff}.folder>.item::before{content:"📁 "}
.file>.item::before{content:"📄 "}.selected{background:#d0e4f5}#toolbar{margin-bottom:1rem}
button{margin-right:.5rem}#search-results{border-top:1px solid #ddd;padding-top:1rem}</style>
</head><body>
<div id="toolbar">
  <button id="btn-refresh">Refresh</button><button id="btn-new-folder">New Folder</button>
  <input type="file" id="file-upload"><input type="text" id="search-input" placeholder="Search...">
  <button id="btn-search">Search</button>
</div>
<div id="tree-container"></div><div id="search-results"></div>
<script>
let selectedPath="";
function renderTree(container,nodes){
  container.innerHTML="";
  let list=document.createElement("ul");list.className="tree";
  nodes.forEach(node=>{
    let itemLi=document.createElement("li");itemLi.className=node.type;
    let itemDiv=document.createElement("div");itemDiv.className="item";
    itemDiv.textContent=node.name;itemDiv.dataset.path=node.path;
    itemDiv.onclick=e=>{e.stopPropagation();
      document.querySelectorAll(".selected").forEach(el=>el.classList.remove("selected"));
      itemDiv.classList.add("selected");selectedPath=node.path};
    itemDiv.oncontextmenu=e=>{e.preventDefault();selectedPath=node.path;
      let cmd=prompt("d Delete, r Rename");if(cmd=="d")deleteItem(node.path);
      if(cmd=="r")renameItem(node.path)};
    itemDiv.draggable=true;itemDiv.ondragstart=e=>e.dataTransfer.setData("text/plain",node.path);
    itemDiv.ondragover=e=>e.preventDefault();
    itemDiv.ondrop=e=>{e.preventDefault();
      let source=e.dataTransfer.getData("text/plain");
      let dest=node.type=="folder"?node.path:node.path.split("/").slice(0,-1).join("/");
      moveItem(source,dest)};
    itemLi.appendChild(itemDiv);
    if(node.type=="folder" && node.children) renderTree(itemLi,node.children);
    list.appendChild(itemLi);
  });
  container.appendChild(list);
}
function apiRequest(url,data,method="POST"){
  let options={method};
  if(data instanceof FormData) options.body=data;
  else if(data){options.headers={"Content-Type":"application/json"};options.body=JSON.stringify(data)}
  return fetch(url,options).then(response=>response.json());
}
function refreshPage(){location.reload()}
function createFolder(){
  let name=prompt("Folder name:");if(!name)return;
  apiRequest("/mkdir",{target:selectedPath,name}).then(r=>r.ok?refreshPage():alert(r.error));
}
function uploadFile(){
  if(selectedPath===null)return alert("Select folder");
  let fileInput=document.getElementById("file-upload");
  let file=fileInput.files[0];if(!file)return;
  let formData=new FormData();formData.append("file",file);formData.append("target",selectedPath);
  apiRequest("/upload",formData).then(r=>r.ok?refreshPage():alert(r.error));
}
function deleteItem(path){
  if(!confirm("Delete "+path+"?"))return;
  apiRequest("/delete",{path}).then(r=>r.ok?refreshPage():alert(r.error));
}
function renameItem(path){
  let newName=prompt("New name:");if(!newName)return;
  apiRequest("/rename",{path,newName}).then(r=>r.ok?refreshPage():alert(r.error));
}
function moveItem(source,destination){
  if(!confirm(`Move ${source} → ${destination}?`))return;
  apiRequest("/move",{src:source,dest:destination}).then(r=>r.ok?refreshPage():alert(r.error));
}
function renderSearchResults(results){
  let container=document.getElementById("search-results");
  container.innerHTML="<h4>Results:</h4>";
  if(!results.length){container.innerHTML+="<p>No matches.</p>";return}
  let list=document.createElement("ul");
  results.forEach(item=>{
    let entry=document.createElement("li");
    entry.textContent=(item.type=="folder"?"📁 ":"📄 ")+item.name+"("+item.path+")";
    entry.style.cursor="pointer";
    entry.onclick=()=>{
      if(item.type=="file") location="/download/"+encodeURIComponent(item.path);
      else{let el=document.querySelector(`.item[data-path="${item.path}"]`);
           if(el){el.click();el.scrollIntoView({behavior:"smooth",block:"center"})}}
    };
    list.appendChild(entry);
  });
  container.appendChild(list);
}
document.getElementById("btn-refresh").onclick=refreshPage;
document.getElementById("btn-new-folder").onclick=createFolder;
document.getElementById("file-upload").onchange=uploadFile;
document.getElementById("btn-search").onclick=()=>{
  let query=document.getElementById("search-input").value.trim();
  if(!query)return alert("Enter search query");
  apiRequest("/search",{query}).then(r=>r.error?alert(r.error):renderSearchResults(r.results));
};
renderTree(document.getElementById("tree-container"), {{ tree|tojson }});
</script>
</body></html>
"""
