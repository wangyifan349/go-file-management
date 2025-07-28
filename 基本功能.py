from flask import Flask, render_template, request, jsonify, send_from_directory
import os
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

STORAGE_ROOT = os.path.abspath('storage')
if not os.path.exists(STORAGE_ROOT):
    os.makedirs(STORAGE_ROOT)

def safe_join(root, *paths):
    final_path = os.path.abspath(os.path.join(root, *paths))
    if not final_path.startswith(root):
        raise Exception("非法路径访问！")
    return final_path

def get_item_info(abs_path, rel_path):
    info = {
        "name": os.path.basename(abs_path),
        "path": rel_path.replace("\\", "/"),
        "is_dir": os.path.isdir(abs_path),
        "size": os.path.getsize(abs_path) if os.path.isfile(abs_path) else None,
    }
    return info

def list_directory_recursive(rel_path=""):
    abs_path = safe_join(STORAGE_ROOT, rel_path)
    if not os.path.isdir(abs_path):
        return []
    items = []
    for fname in sorted(os.listdir(abs_path), key=str.lower):
        f_rel = os.path.join(rel_path, fname).replace("\\", "/")
        f_abs = os.path.join(abs_path, fname)
        info = get_item_info(f_abs, f_rel)
        if info["is_dir"]:
            info["children"] = list_directory_recursive(f_rel)
        items.append(info)
    return items

@app.route('/')
def index():
    # 返回前端html由前端单独文件负责
    return render_template('index.html')


@app.route('/api/tree', methods=['GET'])
def api_tree():
    try:
        tree = list_directory_recursive("")
        return jsonify({"tree": tree})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/download', methods=['GET'])
def api_download():
    rel_path = request.args.get("path", "")
    if not rel_path:
        return jsonify({"error": "缺少文件路径参数"}), 400
    try:
        abs_path = safe_join(STORAGE_ROOT, rel_path)
        if not os.path.isfile(abs_path):
            return jsonify({"error": "文件不存在"}), 404
        dir_name = os.path.dirname(abs_path)
        file_name = os.path.basename(abs_path)
        return send_from_directory(dir_name, file_name, as_attachment=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/mkdir', methods=['POST'])
def api_mkdir():
    try:
        data = request.get_json(force=True)
        parent = data.get("path", "")
        name = data.get("name", "")
        if not name:
            return jsonify({"error": "缺少新文件夹名"}), 400

        if '/' in name or '\\' in name:
            return jsonify({"error": "文件夹名不能包含路径分隔符"}), 400

        abs_parent = safe_join(STORAGE_ROOT, parent)
        if not os.path.isdir(abs_parent):
            return jsonify({"error": "父目录不存在"}), 400

        new_dir = os.path.join(abs_parent, name)
        if os.path.exists(new_dir):
            return jsonify({"error": "目标文件夹已存在"}), 400

        os.mkdir(new_dir)
        return jsonify({"message": "文件夹创建成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/delete', methods=['POST'])
def api_delete():
    try:
        data = request.get_json(force=True)
        rel_path = data.get("path", "")
        if not rel_path:
            return jsonify({"error": "缺少路径参数"}), 400

        abs_path = safe_join(STORAGE_ROOT, rel_path)
        if not os.path.exists(abs_path):
            return jsonify({"error": "路径不存在"}), 404

        if os.path.isdir(abs_path):
            shutil.rmtree(abs_path)
        else:
            os.remove(abs_path)
        return jsonify({"message": "删除成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/rename', methods=['POST'])
def api_rename():
    try:
        data = request.get_json(force=True)
        old_path = data.get("old_path", "")
        new_name = data.get("new_name", "")
        if not old_path or not new_name:
            return jsonify({"error": "缺少参数"}), 400

        if '/' in new_name or '\\' in new_name:
            return jsonify({"error": "新名称不能包含路径分隔符"}), 400

        abs_old = safe_join(STORAGE_ROOT, old_path)
        if not os.path.exists(abs_old):
            return jsonify({"error": "原路径不存在"}), 404

        abs_new = os.path.join(os.path.dirname(abs_old), new_name)
        abs_new = os.path.abspath(abs_new)
        if not abs_new.startswith(STORAGE_ROOT):
            return jsonify({"error": "非法路径"}), 400

        if os.path.exists(abs_new):
            return jsonify({"error": "目标名称已存在"}), 400

        os.rename(abs_old, abs_new)
        return jsonify({"message": "重命名成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/move', methods=['POST'])
def api_move():
    try:
        data = request.get_json(force=True)
        source = data.get("source_path", "")
        target = data.get("target_path", "")
        if not source or not target:
            return jsonify({"error": "参数缺失"}), 400

        abs_source = safe_join(STORAGE_ROOT, source)
        abs_target_dir = safe_join(STORAGE_ROOT, target)
        if not os.path.exists(abs_source):
            return jsonify({"error": "源路径不存在"}), 404
        if not os.path.isdir(abs_target_dir):
            return jsonify({"error": "目标路径不是目录"}), 400

        base_name = os.path.basename(abs_source)
        abs_dst = os.path.join(abs_target_dir, base_name)
        if os.path.exists(abs_dst):
            return jsonify({"error": "目标位置已存在同名文件或文件夹"}), 400

        shutil.move(abs_source, abs_dst)
        return jsonify({"message": "移动成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


if __name__ == '__main__':
    print("请确保当前目录下有一个名为 'storage' 的文件夹作为存储根目录")
    app.run(debug=True)







<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>云盘目录树 搜索与拖拽移动</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
<style>
  body {
    user-select: none;
  }
  #search-box {
    margin-bottom: 1rem;
  }
  #tree {
    user-select: text;
    overflow-y: auto;
    height: 75vh;
    border: 1px solid #dee2e6;
    border-radius: 0.25rem;
    padding: 0.5rem;
  }
  .folder, .file {
    display: flex;
    align-items: center;
    padding: 0.15rem 0.35rem;
    border-radius: 0.25rem;
  }
  .folder:hover, .file:hover {
    background-color: #e9ecef;
    cursor: pointer;
  }
  .folder > .toggle-icon {
    cursor: pointer;
    user-select: none;
    margin-right: 0.5rem;
    width: 1.25em;
    font-weight: 700;
  }
  .folder.expanded > .toggle-icon::before {
    content: "▼";
    display: inline-block;
  }
  .folder > .toggle-icon::before {
    content: "▶";
    display: inline-block;
  }
  .folder > .folder-icon::before {
    content: "📁";
    margin-right: 0.5rem;
  }
  .folder.expanded > .folder-icon::before {
    content: "📂";
  }
  .file > .file-icon::before {
    content: "📄";
    margin-right: 0.75rem;
  }
  .children {
    margin-left: 1.5rem;
    border-left: 2px solid #dee2e6;
    padding-left: 0.5rem;
    display: none;
  }
  .folder.expanded > .children {
    display: block;
  }
  .highlight {
    background-color: yellow;
  }
  /* 拖拽高亮 */
  .drag-over {
    background-color: #cfe2ff !important;
  }
  /* 右键菜单样式 */
  #context-menu {
    position: absolute;
    display: none;
    background: white;
    border: 1px solid #ced4da;
    box-shadow: 0 4px 12px rgb(0 0 0 / 0.15);
    z-index: 1050;
    border-radius: 0.25rem;
    width: 180px;
  }
  #context-menu button {
    width: 100%;
    text-align: left;
  }
  /* 重命名输入框 */
  input.rename-input {
    border: none;
    background: transparent;
    font-size: 1rem;
    font-weight: 600;
    width: 60%;
    user-select: text;
  }
  input.rename-input:focus {
    outline: none;
    background-color: #e9ecef;
    border-radius: 0.2rem;
  }
</style>
</head>
<body class="p-3">
<div class="container">
  <h2 class="mb-3">云盘目录树（带搜索和拖拽移动）</h2>
  <input id="search-box" type="text" class="form-control" placeholder="搜索当前目录树，支持模糊匹配" autocomplete="off" spellcheck="false"/>

  <div id="tree" tabindex="0" aria-label="目录树"></div>

  <hr/>
  <div>
    <h5>操作说明</h5>
    <ul>
      <li>点击文件夹左侧▶可展开/收起</li>
      <li>文件夹、文件可拖拽移动</li>
      <li>右键文件或文件夹呼出菜单（新建文件夹、重命名、删除）</li>
      <li>双击文件下载</li>
      <li>搜索框输入名称，自动筛选匹配项并高亮</li>
    </ul>
  </div>
</div>

<!-- 右键菜单 -->
<div id="context-menu" class="shadow p-1 bg-white rounded">
  <button class="btn btn-sm" id="cm-create-folder">📂 新建文件夹</button>
  <button class="btn btn-sm" id="cm-rename">✏️ 重命名</button>
  <button class="btn btn-sm text-danger" id="cm-delete">🗑 删除</button>
</div>

<script>
const treeContainer = document.getElementById('tree');
const searchBox = document.getElementById('search-box');
const contextMenu = document.getElementById('context-menu');

let currentRightClickNode = null;
let renameInput = null;
let treeData = [];

function ajaxJson(url, method='GET', data=null){
  const headers = {};
  let body = null;
  if(data){
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(data);
  }
  return fetch(url, {method, headers, body}).then(res=>res.json());
}

async function fetchTree(){
  let ret = await ajaxJson('/api/tree');
  if(ret.error){
    alert('获取目录失败: ' + ret.error);
    return [];
  }
  return ret.tree || [];
}

function escapeHtml(text) {
  return text.replace(/[&<>"']/g, function(m) {
    return {'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[m];
  });
}

function createTreeNode(item) {
  let container = document.createElement('div');
  container.className = item.is_dir ? 'folder' : 'file';
  container.dataset.path = item.path;
  container.dataset.name = item.name.toLowerCase();

  if(item.is_dir){
    let toggleIcon = document.createElement('span');
    toggleIcon.className = 'toggle-icon';
    toggleIcon.title = '展开/收起文件夹';
    toggleIcon.addEventListener('click', e=>{
      e.stopPropagation();
      container.classList.toggle('expanded');
    });
    container.appendChild(toggleIcon);

    let folderIcon = document.createElement('span');
    folderIcon.className = 'folder-icon';
    container.appendChild(folderIcon);
  } else {
    let fileIcon = document.createElement('span');
    fileIcon.className = 'file-icon';
    container.appendChild(fileIcon);
  }

  // 名称文本，双击下载文件
  let nameSpan = document.createElement('span');
  nameSpan.style.flex = '1';
  nameSpan.style.userSelect = 'text';
  // 因为后面搜索要动态赋class，这里先塞纯文本
  nameSpan.textContent = item.name;

  // 双击下载文件
  if(!item.is_dir){
    nameSpan.addEventListener('dblclick', e=>{
      e.stopPropagation();
      window.open('/api/download?path='+encodeURIComponent(item.path), '_blank');
    });
  } else {
    // 点击文件夹名切换展开
    nameSpan.addEventListener('click', e=>{
      e.stopPropagation();
      container.classList.toggle('expanded');
    });
  }
  container.appendChild(nameSpan);

  container.setAttribute('draggable', 'true');

  // 拖拽事件
  container.addEventListener('dragstart', e=>{
    e.dataTransfer.setData('text/plain', item.path);
    e.dataTransfer.effectAllowed = 'move';
  });

  if(item.is_dir){
    container.addEventListener('dragover', e=>{
      e.preventDefault();
      container.classList.add('drag-over');
    });
    container.addEventListener('dragleave', e=>{
      container.classList.remove('drag-over');
    });
    container.addEventListener('drop', async e=>{
      e.preventDefault();
      container.classList.remove('drag-over');
      let sourcePath = e.dataTransfer.getData('text/plain');
      if(sourcePath){
        if(sourcePath === item.path){
          alert('不能把文件夹/文件移到自己里面');
          return;
        }
        // 防止移动到自身子目录可自己扩展判断（这里简单拦截）
        if(sourcePath.startsWith(item.path + '/')){
          alert('不能把文件夹移到其子目录');
          return;
        }
        let ret = await ajaxJson('/api/move', 'POST', {
          source_path: sourcePath,
          target_path: item.path
        });
        if(ret.error){
          alert('移动失败：' + ret.error);
        } else {
          alert('移动成功');
          loadTree();
          searchBox.value && doSearch(searchBox.value);
        }
      }
    });
  }

  // 右键菜单
  container.addEventListener('contextmenu', e=>{
    e.preventDefault();
    currentRightClickNode = container;
    showContextMenu(e.pageX, e.pageY, item.is_dir);
  });

  // 递归创建子节点
  if(item.is_dir && item.children && item.children.length > 0){
    let childrenDiv = document.createElement('div');
    childrenDiv.className = 'children';
    for(let i=0; i<item.children.length; i++){
      let childNode = createTreeNode(item.children[i]);
      childrenDiv.appendChild(childNode);
    }
    container.appendChild(childrenDiv);
  }

  return container;
}

async function loadTree(){
  treeContainer.innerHTML = '';
  treeData = await fetchTree();
  for(let i=0;i<treeData.length;i++){
    let node = createTreeNode(treeData[i]);
    treeContainer.appendChild(node);
  }
}

// 搜索实现，模糊匹配，匹配的先显示，不匹配的隐藏，匹配处高亮
function doSearch(keyword){
  keyword = keyword.trim().toLowerCase();
  if(!keyword){
    // 重置显示，无高亮，折叠所有文件夹（默认关闭）
    let allNodes = treeContainer.querySelectorAll('.folder, .file');
    allNodes.forEach(n=>{
      n.style.display = '';
      n.classList.remove('expanded');
      let nameSpan = n.querySelector('span:nth-child(3)');
      if(nameSpan){
        nameSpan.innerHTML = escapeHtml(nameSpan.textContent);
        nameSpan.classList.remove('highlight');
      }
    });
    return;
  }

  // 递归检查匹配，返回是否展示
  function checkNodeVisible(node){
    const nameSpan = node.querySelector('span:nth-child(3)');
    let nameText = nameSpan.textContent.toLowerCase();
    let childrenDiv = node.querySelector('.children');

    // 判断当前节点是否匹配
    let matched = nameText.includes(keyword);

    // 子节点匹配
    let childMatched = false;
    if(childrenDiv){
      let children = Array.from(childrenDiv.children);
      for(let c of children){
        let visible = checkNodeVisible(c);
        childMatched = childMatched || visible;
      }
    }

    // 当前节点显示条件：自身匹配或有子匹配
    let toShow = matched || childMatched;
    node.style.display = toShow ? '' : 'none';

    // 处理文件夹折叠情况
    if(node.classList.contains('folder')){
      if(childMatched){
        // 展开显示子节点
        node.classList.add('expanded');
      } else {
        // 没有子匹配就收起
        node.classList.remove('expanded');
      }
    }

    // 高亮匹配文本
    if(matched){
      // 直接给nameSpan innerHTML赋值，高亮关键词部分
      const escapedName = escapeHtml(nameSpan.textContent);
      const regex = new RegExp(`(${keyword.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')})`, "gi");
      nameSpan.innerHTML = escapedName.replace(regex, '<span class="highlight">$1</span>');
    } else {
      // 清除高亮
      nameSpan.innerHTML = escapeHtml(nameSpan.textContent);
      nameSpan.classList.remove('highlight');
    }

    return toShow;
  }

  // 从根开始检测
  let roots = Array.from(treeContainer.children);
  for(let r of roots){
    checkNodeVisible(r);
  }
}

function showContextMenu(x, y, isFolder){
  contextMenu.style.left = x + 'px';
  contextMenu.style.top = y + 'px';
  contextMenu.style.display = 'block';

  document.getElementById('cm-create-folder').style.display = isFolder ? 'block' : 'none';
  document.body.style.userSelect = 'none';
}

document.body.addEventListener('click', e=>{
  contextMenu.style.display = 'none';
  if(renameInput){
    finishRename(false);
  }
  document.body.style.userSelect = 'auto';
});


// 新建文件夹
document.getElementById('cm-create-folder').addEventListener('click', async e=>{
  contextMenu.style.display = 'none';
  if(!currentRightClickNode) return;
  let folderName = prompt('请输入新文件夹名称');
  if(!folderName) return;
  try {
    let parentPath = currentRightClickNode.dataset.path || "";
    let ret = await ajaxJson('/api/mkdir', 'POST', {path: parentPath, name: folderName});
    if(ret.error) alert('创建失败：' + ret.error);
    else {
      alert('创建成功');
      loadTree();
      searchBox.value && doSearch(searchBox.value);
    }
  } catch(e){
    alert('请求失败');
  }
});

// 删除
document.getElementById('cm-delete').addEventListener('click', async e=>{
  contextMenu.style.display = 'none';
  if(!currentRightClickNode) return;
  if(!confirm('确认删除此文件(夹)？删除后不可恢复！')) return;
  try {
    let path = currentRightClickNode.dataset.path;
    let ret = await ajaxJson('/api/delete', 'POST', {path});
    if(ret.error) alert('删除失败：' + ret.error);
    else {
      alert('删除成功');
      loadTree();
      searchBox.value && doSearch(searchBox.value);
    }
  } catch(e){
    alert('请求失败');
  }
});

// 重命名操作相关
function finishRename(save){
  if(!renameInput) return;
  let span = renameInput.parentElement.querySelector('span:nth-child(3)');
  if(save){
    let newName = renameInput.value.trim();
    if(!newName){
      alert('名称不能为空');
      renameInput.focus();
      return;
    }
    let oldPath = renameInput.parentElement.dataset.path;

    ajaxJson('/api/rename', 'POST', {old_path: oldPath, new_name: newName}).then(ret=>{
      if(ret.error) alert('重命名失败：' + ret.error);
      else {
        alert('重命名成功');
        loadTree();
        searchBox.value && doSearch(searchBox.value);
      }
    });
  }

  renameInput.remove();
  renameInput = null;
}

function startRename(targetNode){
  if(renameInput) finishRename(false);
  let nameSpan = targetNode.querySelector('span:nth-child(3)');
  if(!nameSpan) return;
  let oldName = nameSpan.textContent;
  renameInput = document.createElement('input');
  renameInput.type = 'text';
  renameInput.className = 'rename-input';
  renameInput.value = oldName;
  renameInput.autofocus = true;
  renameInput.style.flex = '1';
  nameSpan.textContent = '';
  nameSpan.appendChild(renameInput);
  renameInput.focus();

  renameInput.addEventListener('keydown', e=>{
    if(e.key === 'Enter'){
      finishRename(true);
    } else if(e.key === 'Escape'){
      finishRename(false);
    }
  });

  renameInput.addEventListener('blur', e=>{
    finishRename(true);
  });
}

// 重命名按钮
document.getElementById('cm-rename').addEventListener('click', e=>{
  contextMenu.style.display = 'none';
  if(!currentRightClickNode) return;
  startRename(currentRightClickNode);
});

// 搜索动作绑定，带节流简单处理
let searchTimeout = null;
searchBox.addEventListener('input', e=>{
  clearTimeout(searchTimeout);
  let val = e.target.value;
  searchTimeout = setTimeout(()=>{
    doSearch(val);
  }, 250);
});

window.onload = loadTree;

</script>
</body>
</html>




package main

import (
    "errors"
    "io"
    "net/http"
    "os"
    "path/filepath"
    "sort"
    "strings"

    "github.com/gin-gonic/gin"
)

const storageRoot = "./storage" // 根目录存储路径

// FileItem 表示单个文件或文件夹节点的结构体
type FileItem struct {
    Name     string     `json:"name"`               // 文件或文件夹名称
    Path     string     `json:"path"`               // 相对路径，统一使用 '/' 作为分隔符
    IsDir    bool       `json:"isDir"`              // 是否是文件夹
    Size     int64      `json:"size,omitempty"`     // 文件大小，文件夹无大小
    Children []FileItem `json:"children,omitempty"` // 子文件夹内文件列表
}

// safeJoin 安全拼接路径，防止目录遍历攻击
func safeJoin(root string, paths ...string) (string, error) {
    fullPath := filepath.Join(append([]string{root}, paths...)...)
    absRoot, err := filepath.Abs(root)
    if err != nil {
        return "", err
    }
    absPath, err := filepath.Abs(fullPath)
    if err != nil {
        return "", err
    }
    if !strings.HasPrefix(absPath, absRoot) {
        return "", errors.New("非法路径访问")
    }
    return absPath, nil
}

// getItemInfo 获取文件或文件夹基础信息，入参为绝对路径和相对路径
func getItemInfo(absPath, relPath string) (FileItem, error) {
    info, err := os.Stat(absPath)
    if err != nil {
        return FileItem{}, err
    }
    return FileItem{
        Name:  info.Name(),
        Path:  filepath.ToSlash(relPath),
        IsDir: info.IsDir(),
        Size:  func() int64 { if info.IsDir() { return 0 }; return info.Size() }(),
    }, nil
}

// listDirectoryRecursive 递归获取目录列表和文件，构建树形结构
func listDirectoryRecursive(relPath string) ([]FileItem, error) {
    absPath, err := safeJoin(storageRoot, relPath)
    if err != nil {
        return nil, err
    }
    entries, err := os.ReadDir(absPath)
    if err != nil {
        return nil, err
    }

    // 按字母排序
    sort.Slice(entries, func(i, j int) bool {
        return strings.ToLower(entries[i].Name()) < strings.ToLower(entries[j].Name())
    })

    var items []FileItem
    for _, entry := range entries {
        childRelPath := filepath.Join(relPath, entry.Name())
        childAbsPath := filepath.Join(absPath, entry.Name())

        item, err := getItemInfo(childAbsPath, childRelPath)
        if err != nil {
            continue // 忽略错误文件/目录
        }
        if item.IsDir {
            children, err := listDirectoryRecursive(childRelPath)
            if err == nil {
                item.Children = children
            }
        }
        items = append(items, item)
    }
    return items, nil
}

func main() {
    // 确保存储根目录存在
    if _, err := os.Stat(storageRoot); os.IsNotExist(err) {
        os.Mkdir(storageRoot, os.ModePerm)
    }

    router := gin.Default()
    router.LoadHTMLFiles("templates/index.html")
    router.Static("/static", "./static")

    // 首页：渲染主页模板
    router.GET("/", func(ctx *gin.Context) {
        ctx.HTML(http.StatusOK, "index.html", nil)
    })

    // API: 获取目录树结构
    router.GET("/api/tree", func(ctx *gin.Context) {
        tree, err := listDirectoryRecursive("")
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        ctx.JSON(http.StatusOK, gin.H{"tree": tree})
    })

    // API: 下载文件接口，根据路径参数提供文件下载
    router.GET("/api/download", func(ctx *gin.Context) {
        relFilePath := ctx.Query("path")
        if relFilePath == "" {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "缺少文件路径参数"})
            return
        }
        absFilePath, err := safeJoin(storageRoot, relFilePath)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        info, err := os.Stat(absFilePath)
        if err != nil || info.IsDir() {
            ctx.JSON(http.StatusNotFound, gin.H{"error": "文件不存在或者路径是文件夹"})
            return
        }
        ctx.FileAttachment(absFilePath, info.Name())
    })

    // API: 创建文件夹，传递JSON参数 { path: 父目录路径, name: 新文件夹名 }
    router.POST("/api/mkdir", func(ctx *gin.Context) {
        var req struct {
            DirPath string `json:"path"` // 父目录相对路径
            DirName string `json:"name"` // 新文件夹名
        }
        if err := ctx.ShouldBindJSON(&req); err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "参数解析失败"})
            return
        }
        if req.DirName == "" {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "缺少新文件夹名称"})
            return
        }
        if strings.ContainsAny(req.DirName, "/\\") {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "文件夹名称不能包含路径分隔符"})
            return
        }
        absParentPath, err := safeJoin(storageRoot, req.DirPath)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        info, err := os.Stat(absParentPath)
        if err != nil || !info.IsDir() {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "父目录不存在"})
            return
        }
        newDirPath := filepath.Join(absParentPath, req.DirName)
        if _, err := os.Stat(newDirPath); err == nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "目标文件夹已存在"})
            return
        }
        if err := os.Mkdir(newDirPath, 0755); err != nil {
            ctx.JSON(http.StatusInternalServerError, gin.H{"error": "创建文件夹失败"})
            return
        }
        ctx.JSON(http.StatusOK, gin.H{"message": "文件夹创建成功"})
    })

    // API: 删除文件或文件夹，传递JSON参数 { path: 需删除文件或文件夹相对路径 }
    router.POST("/api/delete", func(ctx *gin.Context) {
        var req struct {
            TargetPath string `json:"path"` // 目标相对路径
        }
        if err := ctx.ShouldBindJSON(&req); err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "参数解析失败"})
            return
        }
        if req.TargetPath == "" {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "缺少路径参数"})
            return
        }
        absTargetPath, err := safeJoin(storageRoot, req.TargetPath)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        if _, err := os.Stat(absTargetPath); err != nil {
            ctx.JSON(http.StatusNotFound, gin.H{"error": "路径不存在"})
            return
        }
        if err := os.RemoveAll(absTargetPath); err != nil {
            ctx.JSON(http.StatusInternalServerError, gin.H{"error": "删除失败"})
            return
        }
        ctx.JSON(http.StatusOK, gin.H{"message": "删除成功"})
    })

    // API: 重命名，传递JSON参数 { oldPath: 旧filepath, newName: 新名称 }
    router.POST("/api/rename", func(ctx *gin.Context) {
        var req struct {
            OldPath string `json:"oldPath"`
            NewName string `json:"newName"`
        }
        if err := ctx.ShouldBindJSON(&req); err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "参数解析失败"})
            return
        }
        if req.OldPath == "" || req.NewName == "" {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "缺少参数"})
            return
        }
        if strings.ContainsAny(req.NewName, "/\\") {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "新名称不能包含路径分隔符"})
            return
        }
        absOldPath, err := safeJoin(storageRoot, req.OldPath)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        if _, err := os.Stat(absOldPath); err != nil {
            ctx.JSON(http.StatusNotFound, gin.H{"error": "旧路径不存在"})
            return
        }
        absNewPath := filepath.Join(filepath.Dir(absOldPath), req.NewName)
        absNewPath, err = filepath.Abs(absNewPath)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        absRoot, _ := filepath.Abs(storageRoot)
        if !strings.HasPrefix(absNewPath, absRoot) {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "非法路径"})
            return
        }
        if _, err := os.Stat(absNewPath); err == nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "目标名称已存在"})
            return
        }
        if err := os.Rename(absOldPath, absNewPath); err != nil {
            ctx.JSON(http.StatusInternalServerError, gin.H{"error": "重命名失败"})
            return
        }
        ctx.JSON(http.StatusOK, gin.H{"message": "重命名成功"})
    })

    // API: 移动文件或文件夹, 参数 { sourcePath: 源相对路径, targetDir: 目标目录路径 }
    router.POST("/api/move", func(ctx *gin.Context) {
        var req struct {
            SourcePath string `json:"sourcePath"`
            TargetDir  string `json:"targetDir"`
        }
        if err := ctx.ShouldBindJSON(&req); err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "参数解析失败"})
            return
        }
        if req.SourcePath == "" || req.TargetDir == "" {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "参数缺失"})
            return
        }
        absSrcPath, err := safeJoin(storageRoot, req.SourcePath)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        absTargetDir, err := safeJoin(storageRoot, req.TargetDir)
        if err != nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
            return
        }
        srcInfo, err := os.Stat(absSrcPath)
        if err != nil {
            ctx.JSON(http.StatusNotFound, gin.H{"error": "源路径不存在"})
            return
        }
        targetInfo, err := os.Stat(absTargetDir)
        if err != nil || !targetInfo.IsDir() {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "目标路径不是目录"})
            return
        }
        baseName := filepath.Base(absSrcPath)
        absDestPath := filepath.Join(absTargetDir, baseName)

        if _, err := os.Stat(absDestPath); err == nil {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "目标位置已存在同名文件或文件夹"})
            return
        }
        if srcInfo.IsDir() && (absDestPath == absSrcPath || strings.HasPrefix(absDestPath, absSrcPath+string(os.PathSeparator))) {
            ctx.JSON(http.StatusBadRequest, gin.H{"error": "不能把文件夹移到其子目录或自身"})
            return
        }

        if err := os.Rename(absSrcPath, absDestPath); err != nil {
            if moveErr := moveCrossDevice(absSrcPath, absDestPath); moveErr != nil {
                ctx.JSON(http.StatusInternalServerError, gin.H{"error": "移动失败: " + moveErr.Error()})
                return
            }
        }
        ctx.JSON(http.StatusOK, gin.H{"message": "移动成功"})
    })

    router.Run(":8080")
}

// moveCrossDevice 跨设备移动，先复制文件/目录再删除源
func moveCrossDevice(srcPath, destPath string) error {
    info, err := os.Stat(srcPath)
    if err != nil {
        return err
    }
    if info.IsDir() {
        if err := copyDirectory(srcPath, destPath); err != nil {
            return err
        }
        return os.RemoveAll(srcPath)
    } else {
        if err := copyFile(srcPath, destPath); err != nil {
            return err
        }
        return os.Remove(srcPath)
    }
}

// copyDirectory 递归复制文件夹
func copyDirectory(srcDir, destDir string) error {
    entries, err := os.ReadDir(srcDir)
    if err != nil {
        return err
    }
    if err := os.MkdirAll(destDir, 0755); err != nil {
        return err
    }
    for _, entry := range entries {
        srcEntry := filepath.Join(srcDir, entry.Name())
        destEntry := filepath.Join(destDir, entry.Name())
        if entry.IsDir() {
            if err := copyDirectory(srcEntry, destEntry); err != nil {
                return err
            }
        } else {
            if err := copyFile(srcEntry, destEntry); err != nil {
                return err
            }
        }
    }
    return nil
}

// copyFile 复制单个文件内容
func copyFile(srcFile, destFile string) error {
    in, err := os.Open(srcFile)
    if err != nil {
        return err
    }
    defer in.Close()

    out, err := os.Create(destFile)
    if err != nil {
        return err
    }
    defer out.Close()

    _, err = io.Copy(out, in)
    return err
}



