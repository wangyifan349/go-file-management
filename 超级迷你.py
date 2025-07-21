from flask import Flask, request, send_from_directory, \
                  render_template_string, jsonify
import os, shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# Configuration
STORAGE_ROOT = os.path.abspath('storage')
ALLOWED_EXTENSIONS = None  # None = allow all
os.makedirs(STORAGE_ROOT, exist_ok=True)


def is_allowed_file(filename):
    """Check file extension if a whitelist is defined."""
    if ALLOWED_EXTENSIONS is None:
        return True
    ext = filename.rsplit('.', 1)[-1].lower()
    return '.' in filename and ext in ALLOWED_EXTENSIONS


def safe_path(relative_path):
    """Prevent path traversal: ensure path stays under STORAGE_ROOT."""
    full_path = os.path.abspath(os.path.join(STORAGE_ROOT, relative_path))
    if not full_path.startswith(STORAGE_ROOT):
        raise ValueError("Illegal path")
    return full_path


def build_tree(current_path):
    """Recursively build a JSON-serializable tree of folders/files."""
    entries = []
    for name in sorted(os.listdir(current_path)):
        full = os.path.join(current_path, name)
        rel = os.path.relpath(full, STORAGE_ROOT).replace('\\', '/')
        if os.path.isdir(full):
            entries.append({
                'type': 'folder',
                'name': name,
                'path': rel,
                'children': build_tree(full)
            })
        else:
            entries.append({
                'type': 'file',
                'name': name,
                'path': rel
            })
    return entries


@app.route('/')
def index():
    """Render main page with embedded tree data."""
    tree = build_tree(STORAGE_ROOT)
    return render_template_string(PAGE_TEMPLATE, tree=tree)


@app.route('/download/<path:rel_path>')
def download(rel_path):
    """Download a single file."""
    full = safe_path(rel_path)
    if os.path.isdir(full):
        return "Cannot download a folder", 400
    directory, filename = os.path.split(full)
    return send_from_directory(directory, filename, as_attachment=True)


@app.route('/upload', methods=['POST'])
def upload():
    """
    Upload a file into a target folder.
    Expects form field 'file': file data
             form field 'target': relative folder path
    """
    target_folder = request.form.get('target', '')
    dest_folder = safe_path(target_folder)

    if 'file' not in request.files:
        return jsonify(error='No file part'), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify(error='No selected file'), 400
    if not is_allowed_file(file.filename):
        return jsonify(error='File type not allowed'), 400

    filename = secure_filename(file.filename)
    file.save(os.path.join(dest_folder, filename))
    return jsonify(ok=True)


@app.route('/mkdir', methods=['POST'])
def make_folder():
    """
    Create a subfolder under 'target'.
    JSON body: { "target": "path", "name": "new_folder_name" }
    """
    data = request.get_json()
    parent = data.get('target', '')
    name = data.get('name', '').strip()
    if not name:
        return jsonify(error='Folder name required'), 400

    parent_full = safe_path(parent)
    new_folder = os.path.join(parent_full, secure_filename(name))
    try:
        os.makedirs(new_folder, exist_ok=False)
    except FileExistsError:
        return jsonify(error='Name already exists'), 400
    return jsonify(ok=True)


@app.route('/rename', methods=['POST'])
def rename_item():
    """
    Rename file or folder.
    JSON body: { "path":"old_path", "newName":"new_name" }
    """
    data = request.get_json()
    old_path = data.get('path', '')
    new_name = data.get('newName', '').strip()
    if not new_name:
        return jsonify(error='New name required'), 400

    old_full = safe_path(old_path)
    parent_dir = os.path.dirname(old_full)
    new_full = os.path.join(parent_dir, secure_filename(new_name))
    if os.path.exists(new_full):
        return jsonify(error='Name already exists'), 400
    os.rename(old_full, new_full)
    return jsonify(ok=True)


@app.route('/delete', methods=['POST'])
def delete_item():
    """
    Delete file or folder recursively.
    JSON body: { "path":"item_path" }
    """
    data = request.get_json()
    rel_path = data.get('path', '')
    full_path = safe_path(rel_path)
    if not os.path.exists(full_path):
        return jsonify(error='Not found'), 404

    if os.path.isdir(full_path):
        shutil.rmtree(full_path)
    else:
        os.remove(full_path)
    return jsonify(ok=True)


@app.route('/move', methods=['POST'])
def move_item():
    """
    Move file or folder to a target folder.
    JSON body: { "src":"source_path", "dest":"dest_folder_path" }
    """
    data = request.get_json()
    src = data.get('src', '')
    dest = data.get('dest', '')
    src_full = safe_path(src)
    dest_full = safe_path(dest)
    if not os.path.exists(src_full) or not os.path.isdir(dest_full):
        return jsonify(error='Invalid source or destination'), 400

    name = os.path.basename(src_full)
    new_location = os.path.join(dest_full, name)
    if os.path.exists(new_location):
        return jsonify(error='Name conflict at destination'), 400

    shutil.move(src_full, new_location)
    return jsonify(ok=True)


if __name__ == '__main__':
    app.run(debug=True, port=5000)


# HTML + JS Template
PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>File Manager</title>
  <style>
    body { font-family: sans-serif; padding: 1rem; }
    ul, li { list-style: none; margin: 0; padding: 0; }
    .tree { margin-left: 1rem; }
    .item { padding: 0.2rem; cursor: pointer; }
    .item:hover { background: #f0f8ff; }
    .folder > .item::before { content: "📁 "; }
    .file > .item::before   { content: "📄 "; }
    .selected { background: #d0e4f5; }
    #toolbar { margin-bottom: 1rem; }
    button { margin-right: 0.5rem; }
  </style>
</head>
<body>
  <div id="toolbar">
    <button id="btn-refresh">Refresh</button>
    <button id="btn-new-folder">New Folder</button>
    <input type="file" id="file-upload">
  </div>
  <div id="tree-container"></div>

<script>
const treeData = {{ tree|tojson }};
let selectedPath = "";  // currently selected item

// Recursively render the folder/file tree
function renderTree(container, nodes) {
  container.innerHTML = "";
  const ul = document.createElement("ul");
  ul.className = "tree";
  nodes.forEach(node => {
    const li = document.createElement("li");
    li.className = node.type;
    const div = document.createElement("div");
    div.className = "item";
    div.textContent = node.name;
    div.dataset.path = node.path;

    // click to select
    div.onclick = e => {
      e.stopPropagation();
      document.querySelectorAll('.selected')
              .forEach(el=>el.classList.remove('selected'));
      div.classList.add('selected');
      selectedPath = node.path;
    };

    // right-click for delete/rename prompt
    div.oncontextmenu = e => {
      e.preventDefault();
      selectedPath = node.path;
      const action = prompt("d = delete, r = rename");
      if (action === 'd') deleteItem(node.path);
      if (action === 'r') renameItem(node.path);
    };

    // drag & drop to move
    div.draggable = true;
    div.ondragstart = e => {
      e.dataTransfer.setData("text/plain", node.path);
    };
    div.ondragover = e => e.preventDefault();
    div.ondrop = e => {
      e.preventDefault();
      const src = e.dataTransfer.getData("text/plain");
      const dest = node.type === 'folder'
                   ? node.path
                   : node.path.split('/').slice(0, -1).join('/');
      moveItem(src, dest);
    };

    li.appendChild(div);
    if (node.type === 'folder' && node.children.length) {
      renderTree(li, node.children);
    }
    ul.appendChild(li);
  });
  container.appendChild(ul);
}

// Generic API helper
function api(url, data, method='POST') {
  return fetch(url, {
    method, 
    headers: { 'Content-Type': 'application/json' },
    body: data ? JSON.stringify(data) : null
  }).then(r => r.json());
}

// Refresh page
function refresh() {
  location.reload();
}

// Create folder
function createFolder() {
  const name = prompt("New folder name:");
  if (!name) return;
  api('/mkdir', { target: selectedPath, name })
    .then(res => res.ok ? refresh() : alert(res.error));
}

// Delete item
function deleteItem(path) {
  if (!confirm("Delete " + path + " ?")) return;
  api('/delete', { path })
    .then(res => res.ok ? refresh() : alert(res.error));
}

// Rename item
function renameItem(path) {
  const newName = prompt("New name:");
  if (!newName) return;
  api('/rename', { path, newName })
    .then(res => res.ok ? refresh() : alert(res.error));
}

// Move item
function moveItem(src, dest) {
  if (!confirm(`Move "${src}" to "${dest}" ?`)) return;
  api('/move', { src, dest })
    .then(res => res.ok ? refresh() : alert(res.error));
}

// Upload file
document.getElementById('file-upload').onchange = function() {
  if (!selectedPath) {
    return alert("Select a target folder first");
  }
  const file = this.files[0];
  const form = new FormData();
  form.append('file', file);
  form.append('target', selectedPath);
  fetch('/upload', { method: 'POST', body: form })
    .then(res => res.json())
    .then(res => res.ok ? refresh() : alert(res.error));
};

// Event bindings
document.getElementById('btn-refresh').onclick = refresh;
document.getElementById('btn-new-folder').onclick = createFolder;

// Initial render
renderTree(document.getElementById('tree-container'), treeData);
</script>
</body>
</html>
"""
