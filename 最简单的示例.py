"""
flask-elfinder 是一个为 Flask 应用提供 elFinder “Connector” 的轻量级扩展库。它让你几乎无需动手写文件管理的后台逻辑，就能快速集成功能完备的浏览器端文件管理器（elFinder）。
"""






import os
from flask import Flask, send_from_directory, render_template_string
from flask_elfinder import Elfinder

# —————— 配置 ——————
app = Flask(__name__)
app.secret_key = '请替换为你自己的 secret_key'

# 你要管理的本地目录（会自动创建）
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_ROOT = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_ROOT, exist_ok=True)

# 使用 flask-elfinder 挂载 Connector
# 挂载到 /connector ，前端 elFinder AJAX 会访问它来 CRUD 文件
Elfinder(
    app,
    root=UPLOAD_ROOT,   # 本地磁盘上的文件根目录
    url='/uploads',     # 浏览器静态访问前缀，用于下载/预览
    plugins=['OpenEditor', 'Quicklook']  # 可选插件
)

# —————— 前端页面（内嵌 elFinder） ——————
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Flask + elFinder 文件管理器</title>
  <!-- jQuery & jQuery UI -->
  <script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
  <script src="https://code.jquery.com/ui/1.13.2/jquery-ui.min.js"></script>
  <link rel="stylesheet"
        href="https://code.jquery.com/ui/1.13.2/themes/smoothness/jquery-ui.css">

  <!-- elFinder 样式 & 脚本 -->
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/elfinder@2.1.59/css/elfinder.min.css">
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/elfinder@2.1.59/css/theme.css">
  <script src="https://cdn.jsdelivr.net/npm/elfinder@2.1.59/js/elfinder.min.js"></script>

  <style>
    html, body { height: 100%; margin: 0; }
    #elfinder { height: 100%; }
  </style>
</head>
<body>
  <div id="elfinder"></div>
  <script>
    $(function() {
      $('#elfinder').elfinder({
        url : '/connector',        // Connector 后端地址
        onlyMimes : [],            // 允许所有文件类型
        contextmenu : {
          files : [
            'open','download','getfile','rm','rename','mkdir',
            'upload','copy','cut','paste','duplicate','edit','quicklook'
          ]
        },
        resizable: false
      });
    });
  </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

# 提供 /uploads/<path> 静态文件下载/预览
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_ROOT, filename, as_attachment=True)

if __name__ == '__main__':
    # debug=True 下修改代码会自动重启，生产环境请用 gunicorn/uwsgi
    app.run(host='0.0.0.0', port=5000, debug=True)
