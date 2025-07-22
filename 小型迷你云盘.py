# -*- coding: utf-8 -*-
"""
一个合并了Flask后端和Bootstrap5前端的简单文件管理系统示例。
运行前请确保已安装Flask： pip install flask
启动后，访问 http://127.0.0.1:5000/ 即可使用。
"""

import os
import shutil
from flask import (
    Flask, request, render_template_string, jsonify,
    send_file, redirect, url_for, session
)
from werkzeug.utils import secure_filename
from pathlib import Path

app = Flask(__name__)
app.secret_key = "change_this_secret_key"

# 根目录，所有文件夹和文件基于此（你可以修改成你想的目录）
BASE_DIR = Path(__file__).parent.resolve() / "storage"
BASE_DIR.mkdir(exist_ok=True)

# 模板（用render_template_string渲染）
TEMPLATE = '''
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>文件管理系统</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<style>
  body { background: #f8f9fa; }
  table td, table th { vertical-align: middle !important; }
</style>
</head>
<body>

<nav class="navbar navbar-expand-lg navbar-dark bg-primary mb-4">
  <div class="container-fluid">
    <a class="navbar-brand" href="{{ url_for('index') }}">文件管理</a>
    <div class="collapse navbar-collapse">
      <nav aria-label="breadcrumb" class="ms-3">
        <ol class="breadcrumb mb-0" id="breadcrumb-container"></ol>
      </nav>
    </div>
    <div>
      <button class="btn btn-light btn-sm me-2" data-bs-toggle="modal" data-bs-target="#uploadModal">上传文件</button>
      {% if 'user' in session %}
      <a href="{{ url_for('logout') }}" class="btn btn-danger btn-sm">退出登录</a>
      {% else %}
      <a href="{{ url_for('login') }}" class="btn btn-success btn-sm">登录</a>
      {% endif %}
    </div>
  </div>
</nav>

<div class="container">
  <div id="alert-container">{% with msgs = get_flashed_messages(with_categories=true) %}
    {% for category, msg in msgs %}
    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
      {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
    </div>
    {% endfor %}{% endwith %}
  </div>

  <div class="d-flex justify-content-between align-items-center mb-3">
    <h4>目录: <span id="current-path">{{ current_path }}</span></h4>
    {% if 'user' in session %}
    <button class="btn btn-success btn-sm" data-bs-toggle="modal" data-bs-target="#mkdirModal">新建文件夹</button>
    {% endif %}
  </div>

  <div class="row row-cols-1 row-cols-md-2 g-3">
    <div class="col">
      <h5>文件夹</h5>
      <table class="table table-striped table-hover">
        <thead><tr><th>名称</th>{% if session.get('user') %}<th style="width:160px;">操作</th>{% endif %}</tr></thead>
        <tbody>
          {% if folders %}
            {% for folder in folders %}
            <tr>
              <td><a href="{{ url_for('index', req_path=folder.relative_path) }}" class="text-decoration-none">{{ folder.name }}</a></td>
              {% if session.get('user') %}
              <td>
                <button class="btn btn-sm btn-secondary rename-btn" data-path="{{ folder.relative_path }}" data-type="folder">重命名</button>
                <button class="btn btn-sm btn-warning move-btn" data-path="{{ folder.relative_path }}" data-type="folder">移动</button>
                <button class="btn btn-sm btn-danger delete-btn" data-path="{{ folder.relative_path }}" data-type="folder">删除</button>
              </td>
              {% endif %}
            </tr>
            {% endfor %}
          {% else %}
            <tr><td colspan="{{ 2 if session.get('user') else 1 }}" class="text-center">没有文件夹</td></tr>
          {% endif %}
        </tbody>
      </table>
    </div>

    <div class="col">
      <h5>文件</h5>
      <table class="table table-striped table-hover">
        <thead><tr><th>名称</th>{% if session.get('user') %}<th style="width:180px;">操作</th>{% endif %}</tr></thead>
        <tbody>
          {% if files %}
            {% for file in files %}
            <tr>
              <td>{{ file.name }}</td>
              {% if session.get('user') %}
              <td>
                <a href="{{ url_for('download_file', file_path=file.relative_path) }}" class="btn btn-sm btn-primary" target="_blank" rel="noopener noreferrer">下载</a>
                <button class="btn btn-sm btn-secondary rename-btn" data-path="{{ file.relative_path }}" data-type="file">重命名</button>
                <button class="btn btn-sm btn-warning move-btn" data-path="{{ file.relative_path }}" data-type="file">移动</button>
                <button class="btn btn-sm btn-danger delete-btn" data-path="{{ file.relative_path }}" data-type="file">删除</button>
              </td>
              {% endif %}
            </tr>
            {% endfor %}
          {% else %}
            <tr><td colspan="{{ 2 if session.get('user') else 1 }}" class="text-center">没有文件</td></tr>
          {% endif %}
        </tbody>
      </table>
    </div>
  </div>
</div>

{% if session.get('user') %}
<!-- 上传文件模态框 -->
<div class="modal fade" id="uploadModal" tabindex="-1" aria-labelledby="uploadModalLabel" aria-hidden="true">
  <div class="modal-dialog">
    <form id="uploadForm" enctype="multipart/form-data" class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="uploadModalLabel">上传文件</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
      </div>
      <div class="modal-body">
        <input type="file" name="file" id="fileInput" class="form-control" required>
      </div>
      <div class="modal-footer">
        <button type="submit" class="btn btn-primary">上传</button>
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
      </div>
    </form>
  </div>
</div>

<!-- 新建文件夹模态框 -->
<div class="modal fade" id="mkdirModal" tabindex="-1" aria-labelledby="mkdirModalLabel" aria-hidden="true">
  <div class="modal-dialog">
    <form id="mkdirForm" class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="mkdirModalLabel">新建文件夹</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
      </div>
      <div class="modal-body">
        <input type="text" id="folderNameInput" class="form-control" placeholder="文件夹名称" required>
      </div>
      <div class="modal-footer">
        <button type="submit" class="btn btn-success">创建</button>
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">关闭</button>
      </div>
    </form>
  </div>
</div>

<!-- 重命名模态框 -->
<div class="modal fade" id="renameModal" tabindex="-1" aria-labelledby="renameModalLabel" aria-hidden="true">
  <div class="modal-dialog">
    <form id="renameForm" class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="renameModalLabel">重命名</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
      </div>
      <div class="modal-body">
        <input type="text" id="renameInput" class="form-control" placeholder="新名称" required>
        <input type="hidden" id="renamePath">
        <input type="hidden" id="renameType">
      </div>
      <div class="modal-footer">
        <button type="submit" class="btn btn-primary">确定</button>
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
      </div>
    </form>
  </div>
</div>

<!-- 移动模态框 -->
<div class="modal fade" id="moveModal" tabindex="-1" aria-labelledby="moveModalLabel" aria-hidden="true">
  <div class="modal-dialog">
    <form id="moveForm" class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title" id="moveModalLabel">移动</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
      </div>
      <div class="modal-body">
        <input type="text" id="moveTargetPath" class="form-control" placeholder="目标目录（相对根目录路径）" required>
        <input type="hidden" id="movePath">
        <input type="hidden" id="moveType">
      </div>
      <div class="modal-footer">
        <button type="submit" class="btn btn-warning">移动</button>
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
      </div>
    </form>
  </div>
</div>
{% endif %}

<script>
$(function(){
  // 生成路径面包屑导航
  function generateBreadcrumbs(path){
    const container = $('#breadcrumb-container');
    container.empty();
    const parts = path ? path.split('/').filter(Boolean) : [];
    let builtPath = '';
    container.append('<li class="breadcrumb-item"><a href="{{ url_for("index") }}">根目录</a></li>');
    parts.forEach((part, idx) => {
      builtPath += (builtPath ? '/' : '') + part;
      if(idx === parts.length - 1){
        container.append('<li class="breadcrumb-item active" aria-current="page">'+part+'</li>');
      } else {
        container.append('<li class="breadcrumb-item"><a href="{{ url_for("index") }}?req_path='+encodeURIComponent(builtPath)+'">'+part+'</a></li>');
      }
    });
  }
  generateBreadcrumbs("{{ current_path }}");

  // 显示提示信息
  function showAlert(msg, type='success'){
    $('#alert-container').html(
      `<div class="alert alert-${type} alert-dismissible fade show" role="alert">
        ${msg}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="关闭"></button>
      </div>`
    );
  }

  {% if session.get('user') %}
  // 上传文件
  $('#uploadForm').submit(function(e){
    e.preventDefault();
    var formData = new FormData(this);
    var uploadPath = encodeURIComponent("{{ current_path }}");
    $.ajax({
      url: '/upload/' + uploadPath,
      type: 'POST',
      data: formData,
      contentType: false, processData: false,
      success: function(){ location.reload(); },
      error: function(xhr){ showAlert('上传失败：'+xhr.responseText,'danger'); }
    });
  });

  // 新建文件夹
  $('#mkdirForm').submit(function(e){
    e.preventDefault();
    var folderName = $('#folderNameInput').val().trim();
    if(!folderName){ alert('请输入文件夹名称'); return; }
    $.post('/mkdir',{
      folder_path: "{{ current_path }}",
      folder_name: folderName
    }, function(res){
      if(res.code===0){ $('#mkdirModal').modal('hide'); location.reload(); }
      else showAlert(res.msg,'danger');
    }).fail(()=>showAlert('新建文件夹请求失败','danger'));
  });

  // 重命名弹窗打开
  $('.rename-btn').click(function(){
    $('#renameInput').val('');
    $('#renamePath').val($(this).data('path'));
    $('#renameType').val($(this).data('type'));
    $('#renameModal').modal('show');
  });

  // 重命名提交
  $('#renameForm').submit(function(e){
    e.preventDefault();
    var newName = $('#renameInput').val().trim();
    if(!newName){ alert('请输入新名称'); return; }
    $.post('/rename',{
      old_path: $('#renamePath').val(),
      new_name: newName,
      type: $('#renameType').val()
    }, function(res){
      if(res.code===0){ $('#renameModal').modal('hide'); location.reload(); }
      else showAlert(res.msg,'danger');
    }).fail(()=>showAlert('重命名请求失败','danger'));
  });

  // 删除操作确认
  $('.delete-btn').click(function(){
    if(!confirm('确认删除？此操作不可恢复！')) return;
    $.post('/delete', {
      path: $(this).data('path'),
      type: $(this).data('type')
    }, function(res){
      if(res.code===0) location.reload();
      else showAlert(res.msg,'danger');
    }).fail(()=>showAlert('删除请求失败','danger'));
  });

  // 移动弹窗打开
  $('.move-btn').click(function(){
    $('#moveTargetPath').val('');
    $('#movePath').val($(this).data('path'));
    $('#moveType').val($(this).data('type'));
    $('#moveModal').modal('show');
  });

  // 移动提交
  $('#moveForm').submit(function(e){
    e.preventDefault();
    var newPath = $('#moveTargetPath').val().trim();
    if(!newPath){ alert('请输入目标目录'); return; }
    $.post('/move',{
      old_path: $('#movePath').val(),
      new_path: newPath,
      type: $('#moveType').val()
    }, function(res){
      if(res.code===0){ $('#moveModal').modal('hide'); location.reload(); }
      else showAlert(res.msg,'danger');
    }).fail(()=>showAlert('移动请求失败','danger'));
  });
  {% endif %}
});
</script>
</body>
</html>
'''

# --------- 辅助函数 ---------

def secure_relative_path(path_str):
    """
    按安全标准处理相对路径，防止目录遍历攻击
    返回Path或None表示非法路径
    """
    if not path_str:
        return Path()
    p = Path(path_str)
    # 过滤绝对路径和父目录跳转
    if p.is_absolute():
        return None
    if '..' in p.parts:
        return None
    return p

def resolve_path(rel_path):
    """
    接收相对路径字符串，经过安全检查后解析为系统绝对路径，如果不安全返回None
    """
    rel_p = secure_relative_path(rel_path)
    if rel_p is None:
        return None
    abs_p = BASE_DIR / rel_p
    try:
        abs_p = abs_p.resolve(strict=False)
        if BASE_DIR in abs_p.parents or abs_p==BASE_DIR:
            return abs_p
        else:
            return None
    except Exception:
        return None

def list_dir(rel_path):
    """
    列出指定相对目录下的文件夹和文件
    返回两个列表，元素为dict：{name, relative_path}
    """
    abs_path = resolve_path(rel_path)
    if abs_path is None or not abs_path.is_dir():
        return [], []

    folders = []
    files = []
    try:
        for entry in abs_path.iterdir():
            rel_ent = entry.relative_to(BASE_DIR)
            info = {"name": entry.name, "relative_path": str(rel_ent).replace('\\', '/')}
            if entry.is_dir():
                folders.append(info)
            elif entry.is_file():
                files.append(info)
    except Exception:
        pass
    # 按名称排序
    folders.sort(key=lambda x: x['name'].lower())
    files.sort(key=lambda x: x['name'].lower())
    return folders, files

def is_user_logged_in():
    # 简单登录判断，实际可根据业务完善
    return session.get('user') == 'admin'

# --------- 路由定义 ---------

from flask import flash

@app.route("/login", methods=["GET", "POST"])
def login():
    # 简易登录页面，仅为示范，密码写死admin/123
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == "admin" and password == "123":
            session['user'] = 'admin'
            return redirect(url_for('index'))
        else:
            flash("用户名密码错误", "danger")
    return render_template_string('''
    <!doctype html>
    <html lang="zh-CN"><head><meta charset="utf-8"><title>登录</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body class="bg-light d-flex align-items-center" style="height:100vh;">
    <div class="container">
      <div class="row justify-content-center">
        <div class="col-md-4 col-10 bg-white p-4 rounded shadow">
          <h3 class="mb-3 text-center">登录</h3>
          {% with msgs = get_flashed_messages(with_categories=true) %}
            {% for category,msg in msgs %}
            <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
              {{ msg }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
            {% endfor %}
          {% endwith %}
          <form method="post">
            <div class="mb-3"><input type="text" name="username" required class="form-control" placeholder="用户名"></div>
            <div class="mb-3"><input type="password" name="password" required class="form-control" placeholder="密码"></div>
            <button type="submit" class="btn btn-primary w-100">登录</button>
          </form>
        </div>
      </div>
    </div>
    </body></html>
    ''')

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/", defaults={"req_path": ""})
@app.route("/<path:req_path>")
def index(req_path):
    # 首页展示目录文件列表
    if not is_user_logged_in():
        return redirect(url_for("login"))

    abs_path = resolve_path(req_path)
    if abs_path is None or not abs_path.exists():
        flash("路径不存在或非法", "danger")
        return redirect(url_for("index"))
    if abs_path.is_file():
        # 如果访问路径是文件，直接下载
        return redirect(url_for("download_file", file_path=req_path))

    folders, files = list_dir(req_path)

    return render_template_string(
        TEMPLATE,
        current_path=req_path.strip('/'),
        folders=folders,
        files=files
    )

@app.route("/download/<path:file_path>")
def download_file(file_path):
    p = resolve_path(file_path)
    if p is None or not p.is_file():
        return "文件不存在或非法路径", 404
    return send_file(p, as_attachment=True)

@app.route("/upload/<path:req_path>", methods=["POST"])
def upload_file(req_path):
    if not is_user_logged_in():
        return "未登录", 403
    abs_path = resolve_path(req_path)
    if abs_path is None or not abs_path.is_dir():
        return "上传目录不存在或非法", 400
    if 'file' not in request.files:
        return "未接收到文件", 400
    file = request.files['file']
    if file.filename == '':
        return "未选择文件", 400
    filename = secure_filename(file.filename)
    dest = abs_path / filename
    try:
        file.save(dest)
    except Exception as e:
        return f"保存文件失败: {e}", 500
    return '', 204

@app.route("/mkdir", methods=["POST"])
def mkdir():
    if not is_user_logged_in():
        return jsonify({"code":1, "msg":"未登录"})
    folder_path = request.form.get("folder_path", "")
    folder_name = request.form.get("folder_name", "").strip()
    if not folder_name:
        return jsonify({"code":1, "msg":"文件夹名称不能为空"})
    base_dir = resolve_path(folder_path)
    if base_dir is None or not base_dir.is_dir():
        return jsonify({"code":1, "msg":"目标路径无效"})
    name_safe = secure_filename(folder_name)
    new_dir = base_dir / name_safe
    try:
        new_dir.mkdir(exist_ok=False)
        return jsonify({"code":0, "msg":"创建成功"})
    except FileExistsError:
        return jsonify({"code":1, "msg":"文件夹已存在"})
    except Exception as e:
        return jsonify({"code":1, "msg":f"创建失败: {e}"})

@app.route("/rename", methods=["POST"])
def rename():
    if not is_user_logged_in():
        return jsonify({"code":1, "msg":"未登录"})
    old_path = request.form.get("old_path", "")
    new_name = request.form.get("new_name", "").strip()
    typ = request.form.get("type", "")
    if not new_name:
        return jsonify({"code":1, "msg":"新名称不能为空"})
    old_abs = resolve_path(old_path)
    if old_abs is None or not old_abs.exists():
        return jsonify({"code":1, "msg":"旧路径不存在"})
    parent_dir = old_abs.parent
    new_name_safe = secure_filename(new_name)
    if typ=="file" and '.' not in new_name_safe:
        # 保持原文件后缀
        suffix = old_abs.suffix
        if suffix:
            new_name_safe += suffix
    new_abs = parent_dir / new_name_safe
    if new_abs.exists():
        return jsonify({"code":1, "msg":"新名称已存在"})
    try:
        old_abs.rename(new_abs)
        return jsonify({"code":0, "msg":"重命名成功"})
    except Exception as e:
        return jsonify({"code":1, "msg":f"重命名失败: {e}"})

@app.route("/delete", methods=["POST"])
def delete():
    if not is_user_logged_in():
        return jsonify({"code":1, "msg":"未登录"})
    path = request.form.get("path", "")
    typ = request.form.get("type", "")
    p = resolve_path(path)
    if p is None or not p.exists():
        return jsonify({"code":1, "msg":"路径不存在"})
    try:
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return jsonify({"code":0, "msg":"删除成功"})
    except Exception as e:
        return jsonify({"code":1, "msg":f"删除失败: {e}"})

@app.route("/move", methods=["POST"])
def move():
    if not is_user_logged_in():
        return jsonify({"code":1, "msg":"未登录"})
    old_path = request.form.get("old_path", "")
    new_path = request.form.get("new_path", "").strip("/")
    typ = request.form.get("type", "")
    old_abs = resolve_path(old_path)
    if old_abs is None or not old_abs.exists():
        return jsonify({"code":1, "msg":"源路径不存在"})
    dest_dir = resolve_path(new_path)
    if dest_dir is None or not dest_dir.is_dir():
        return jsonify({"code":1, "msg":"目标目录不存在"})
    new_abs = dest_dir / old_abs.name
    if new_abs.exists():
        return jsonify({"code":1, "msg":"目标目录已存在重名文件或文件夹"})
    try:
        shutil.move(str(old_abs), str(new_abs))
        return jsonify({"code":0, "msg":"移动成功"})
    except Exception as e:
        return jsonify({"code":1, "msg":f"移动失败: {e}"})


if __name__ == "__main__":
    print("运行 Flask 文件管理系统，默认用户：admin 密码：123")
    app.run(debug=True, port=5000)
