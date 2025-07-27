import os
import uuid
from datetime import datetime
from flask import (
    Flask, request, redirect, url_for, flash,
    send_from_directory, abort, render_template
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from jinja2 import DictLoader


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
BASE_DIRECTORY = os.path.abspath(os.path.dirname(__file__))
UPLOAD_DIRECTORY = os.path.join(BASE_DIRECTORY, 'uploads')
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov'}

APPLICATION = Flask(__name__)
APPLICATION.config.update(
    SECRET_KEY='please-change-this-secret-key',
    SQLALCHEMY_DATABASE_URI='sqlite:///' + os.path.join(BASE_DIRECTORY, 'media_database.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    UPLOAD_FOLDER=UPLOAD_DIRECTORY,
    MAX_CONTENT_LENGTH=50 * 1024 * 1024,  # 50 MB max upload size
)

DATABASE = SQLAlchemy(APPLICATION)
AUTHENTICATION_MANAGER = LoginManager(APPLICATION)
AUTHENTICATION_MANAGER.login_view = 'login'


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------
class User(UserMixin, DATABASE.Model):
    identifier = DATABASE.Column(DATABASE.Integer, primary_key=True)
    user_name = DATABASE.Column(DATABASE.String(80), unique=True, nullable=False)
    password_hash = DATABASE.Column(DATABASE.String(128), nullable=False)
    photo_collections = DATABASE.relationship(
        'PhotoCollection', backref='owner', cascade='all,delete-orphan'
    )
    video_collections = DATABASE.relationship(
        'VideoCollection', backref='owner', cascade='all,delete-orphan'
    )

    def get_id(self):
        # Flask-Login 期望返回唯一字符串id，这里返回identifier字符串
        return str(self.identifier)

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class PhotoCollection(DATABASE.Model):
    identifier = DATABASE.Column(DATABASE.Integer, primary_key=True)
    title = DATABASE.Column(DATABASE.String(120), nullable=False)
    owner_identifier = DATABASE.Column(
        DATABASE.Integer,
        DATABASE.ForeignKey('user.identifier'),
        nullable=False
    )
    photos = DATABASE.relationship(
        'Photo', backref='collection', cascade='all,delete-orphan'
    )


class VideoCollection(DATABASE.Model):
    identifier = DATABASE.Column(DATABASE.Integer, primary_key=True)
    title = DATABASE.Column(DATABASE.String(120), nullable=False)
    owner_identifier = DATABASE.Column(
        DATABASE.Integer,
        DATABASE.ForeignKey('user.identifier'),
        nullable=False
    )
    videos = DATABASE.relationship(
        'Video', backref='collection', cascade='all,delete-orphan'
    )


class Photo(DATABASE.Model):
    identifier = DATABASE.Column(DATABASE.Integer, primary_key=True)
    filename = DATABASE.Column(DATABASE.String(200), nullable=False)
    collection_identifier = DATABASE.Column(
        DATABASE.Integer,
        DATABASE.ForeignKey('photo_collection.identifier'),
        nullable=False
    )


class Video(DATABASE.Model):
    identifier = DATABASE.Column(DATABASE.Integer, primary_key=True)
    filename = DATABASE.Column(DATABASE.String(200), nullable=False)
    mime_type = DATABASE.Column(DATABASE.String(64), nullable=False)
    collection_identifier = DATABASE.Column(
        DATABASE.Integer,
        DATABASE.ForeignKey('video_collection.identifier'),
        nullable=False
    )


DATABASE.create_all()


# -----------------------------------------------------------------------------
# Authentication Loader
# -----------------------------------------------------------------------------
@AUTHENTICATION_MANAGER.user_loader
def load_user_by_identifier(user_identifier):
    return User.query.get(int(user_identifier))


# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------
def is_extension_allowed(filename, allowed_extensions):
    if '.' in filename:
        extension = filename.rsplit('.', 1)[1].lower()
        return extension in allowed_extensions
    return False


def get_unique_filename(filename):
    # 通过 UUID + 时间戳生成避免文件覆盖
    ext = filename.rsplit('.', 1)[1].lower()
    unique_str = uuid.uuid4().hex + datetime.utcnow().strftime('%Y%m%d%H%M%S')
    return f"{unique_str}.{ext}"


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@APPLICATION.route('/')
def homepage():
    search_query = request.args.get('search', '').strip()
    user_search = request.args.get('username', '').strip()
    if user_search:
        matched_users = User.query.filter(User.user_name.contains(user_search)).all()
    else:
        matched_users = []

    if search_query:
        photo_collections = PhotoCollection.query.filter(PhotoCollection.title.contains(search_query)).all()
        video_collections = VideoCollection.query.filter(VideoCollection.title.contains(search_query)).all()
    else:
        photo_collections = PhotoCollection.query.all()
        video_collections = VideoCollection.query.all()

    return render_template('home.html',
                           photo_collections=photo_collections,
                           video_collections=video_collections,
                           matched_users=matched_users,
                           search_query=search_query,
                           user_search=user_search)


@APPLICATION.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        chosen_name = request.form['user_name'].strip()
        chosen_password = request.form['password']
        if not chosen_name or not chosen_password:
            flash('Username and password cannot be empty', 'warning')
        elif User.query.filter_by(user_name=chosen_name).first():
            flash('Username already exists', 'danger')
        else:
            new_user = User(user_name=chosen_name)
            new_user.set_password(chosen_password)
            DATABASE.session.add(new_user)
            DATABASE.session.commit()
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@APPLICATION.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        input_name = request.form['user_name']
        input_password = request.form['password']
        user_record = User.query.filter_by(user_name=input_name).first()
        if user_record and user_record.check_password(input_password):
            login_user(user_record)
            flash('Login successful', 'success')
            return redirect(url_for('homepage'))
        else:
            flash('Invalid username or password', 'danger')
    return render_template('login.html')


@APPLICATION.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('homepage'))


@APPLICATION.route('/uploads/<path:filename>')
def serve_uploaded_file(filename):
    return send_from_directory(APPLICATION.config['UPLOAD_FOLDER'], filename)


# -----------------------------------------------------------------------------
# Photo Collection Management
# -----------------------------------------------------------------------------
@APPLICATION.route('/collections/photos/create', methods=['GET', 'POST'])
@login_required
def create_photo_collection():
    if request.method == 'POST':
        collection_title = request.form['title'].strip()
        if not collection_title:
            flash('Collection title cannot be empty', 'warning')
        else:
            new_collection = PhotoCollection(title=collection_title, owner=current_user)
            DATABASE.session.add(new_collection)
            DATABASE.session.commit()
            flash('Photo collection created', 'success')
            return redirect(url_for('view_photo_collection', collection_id=new_collection.identifier))
    return render_template('create_collection.html', media_type='photo')


@APPLICATION.route('/collections/photos/<int:collection_id>/delete', methods=['POST'])
@login_required
def delete_photo_collection(collection_id):
    collection_record = PhotoCollection.query.get_or_404(collection_id)
    if collection_record.owner != current_user:
        abort(403)
    DATABASE.session.delete(collection_record)
    DATABASE.session.commit()
    flash('Photo collection deleted', 'info')
    return redirect(url_for('homepage'))


@APPLICATION.route('/collections/photos/<int:collection_id>', methods=['GET', 'POST'])
def view_photo_collection(collection_id):
    collection_record = PhotoCollection.query.get_or_404(collection_id)
    if request.method == 'POST':
        if not current_user.is_authenticated or collection_record.owner != current_user:
            abort(403)
        uploaded_file = request.files.get('file')
        if not uploaded_file or uploaded_file.filename == '':
            flash('Please select a file', 'warning')
        elif not is_extension_allowed(uploaded_file.filename, ALLOWED_IMAGE_EXTENSIONS):
            flash('Allowed extensions: ' + ', '.join(ALLOWED_IMAGE_EXTENSIONS), 'warning')
        else:
            secure_name = secure_filename(uploaded_file.filename)
            unique_name = get_unique_filename(secure_name)
            file_path = os.path.join(APPLICATION.config['UPLOAD_FOLDER'], unique_name)
            uploaded_file.save(file_path)
            new_photo = Photo(filename=unique_name, collection=collection_record)
            DATABASE.session.add(new_photo)
            DATABASE.session.commit()
            flash('Photo uploaded successfully', 'success')
        return redirect(url_for('view_photo_collection', collection_id=collection_id))
    return render_template('view_photo_collection.html', collection=collection_record)


@APPLICATION.route('/photos/<int:photo_id>/delete', methods=['POST'])
@login_required
def delete_photo(photo_id):
    photo_record = Photo.query.get_or_404(photo_id)
    if photo_record.collection.owner != current_user:
        abort(403)
    try:
        os.remove(os.path.join(APPLICATION.config['UPLOAD_FOLDER'], photo_record.filename))
    except OSError:
        pass
    DATABASE.session.delete(photo_record)
    DATABASE.session.commit()
    flash('Photo deleted', 'info')
    return redirect(url_for('view_photo_collection', collection_id=photo_record.collection_identifier))


# -----------------------------------------------------------------------------
# Video Collection Management
# -----------------------------------------------------------------------------
@APPLICATION.route('/collections/videos/create', methods=['GET', 'POST'])
@login_required
def create_video_collection():
    if request.method == 'POST':
        collection_title = request.form['title'].strip()
        if not collection_title:
            flash('Collection title cannot be empty', 'warning')
        else:
            new_collection = VideoCollection(title=collection_title, owner=current_user)
            DATABASE.session.add(new_collection)
            DATABASE.session.commit()
            flash('Video collection created', 'success')
            return redirect(url_for('view_video_collection', collection_id=new_collection.identifier))
    return render_template('create_collection.html', media_type='video')


@APPLICATION.route('/collections/videos/<int:collection_id>/delete', methods=['POST'])
@login_required
def delete_video_collection(collection_id):
    collection_record = VideoCollection.query.get_or_404(collection_id)
    if collection_record.owner != current_user:
        abort(403)
    DATABASE.session.delete(collection_record)
    DATABASE.session.commit()
    flash('Video collection deleted', 'info')
    return redirect(url_for('homepage'))


@APPLICATION.route('/collections/videos/<int:collection_id>', methods=['GET', 'POST'])
def view_video_collection(collection_id):
    collection_record = VideoCollection.query.get_or_404(collection_id)
    if request.method == 'POST':
        if not current_user.is_authenticated or collection_record.owner != current_user:
            abort(403)
        uploaded_file = request.files.get('file')
        if not uploaded_file or uploaded_file.filename == '':
            flash('Please select a file', 'warning')
        elif not is_extension_allowed(uploaded_file.filename, ALLOWED_VIDEO_EXTENSIONS):
            flash('Allowed extensions: ' + ', '.join(ALLOWED_VIDEO_EXTENSIONS), 'warning')
        else:
            secure_name = secure_filename(uploaded_file.filename)
            unique_name = get_unique_filename(secure_name)
            file_path = os.path.join(APPLICATION.config['UPLOAD_FOLDER'], unique_name)
            uploaded_file.save(file_path)
            new_video = Video(
                filename=unique_name,
                mime_type=uploaded_file.mimetype,
                collection=collection_record
            )
            DATABASE.session.add(new_video)
            DATABASE.session.commit()
            flash('Video uploaded successfully', 'success')
        return redirect(url_for('view_video_collection', collection_id=collection_id))
    return render_template('view_video_collection.html', collection=collection_record)


@APPLICATION.route('/videos/<int:video_id>/delete', methods=['POST'])
@login_required
def delete_video(video_id):
    video_record = Video.query.get_or_404(video_id)
    if video_record.collection.owner != current_user:
        abort(403)
    try:
        os.remove(os.path.join(APPLICATION.config['UPLOAD_FOLDER'], video_record.filename))
    except OSError:
        pass
    DATABASE.session.delete(video_record)
    DATABASE.session.commit()
    flash('Video deleted', 'info')
    return redirect(url_for('view_video_collection', collection_id=video_record.collection_identifier))


# -----------------------------------------------------------------------------
# Templates (inline)
# -----------------------------------------------------------------------------
TEMPLATE_BASE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Flask Media Library</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">
</head>
<body>
<nav class="navbar navbar-expand-lg navbar-light bg-light mb-3">
  <a class="navbar-brand" href="{{ url_for('homepage') }}">MediaLibrary</a>
  <div class="collapse navbar-collapse">
    <ul class="navbar-nav mr-auto">
      {% if current_user.is_authenticated %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('create_photo_collection') }}">New Photo Collection</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('create_video_collection') }}">New Video Collection</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('logout') }}">Logout</a></li>
      {% else %}
        <li class="nav-item"><a class="nav-link" href="{{ url_for('login') }}">Login</a></li>
        <li class="nav-item"><a class="nav-link" href="{{ url_for('register') }}">Register</a></li>
      {% endif %}
    </ul>
    <form class="form-inline" method="get" action="{{ url_for('homepage') }}">
      <input class="form-control mr-2" name="search" placeholder="Search collections" value="{{ search_query or '' }}">
      <input class="form-control mr-2" name="username" placeholder="Search users" value="{{ user_search or '' }}">
      <button class="btn btn-outline-success">Search</button>
    </form>
  </div>
</nav>
<div class="container">
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }}">{{ message }}</div>
    {% endfor %}
  {% endwith %}
  {% block content %}{% endblock %}
</div>
</body>
</html>
"""


TEMPLATE_HOME = """
{% extends 'base.html' %}
{% block content %}
<h4>Matched Users</h4>
<ul>
  {% for user in matched_users %}
    <li>{{ user.user_name }}</li>
  {% else %}
    {% if user_search %}<li>No users found.</li>{% endif %}
  {% endfor %}
</ul>
<hr>
<h4>Photo Collections</h4>
<div class="row">
  {% for collection in photo_collections %}
  <div class="col-md-3 mb-3">
    <div class="card p-2">
      <h5>{{ collection.title }}</h5>
      <p>by {{ collection.owner.user_name }}</p>
      <a class="btn btn-sm btn-primary" href="{{ url_for('view_photo_collection', collection_id=collection.identifier) }}">View</a>
    </div>
  </div>
  {% else %}
    <p>No photo collections.</p>
  {% endfor %}
</div>
<hr>
<h4>Video Collections</h4>
<div class="row">
  {% for collection in video_collections %}
  <div class="col-md-3 mb-3">
    <div class="card p-2">
      <h5>{{ collection.title }}</h5>
      <p>by {{ collection.owner.user_name }}</p>
      <a class="btn btn-sm btn-primary" href="{{ url_for('view_video_collection', collection_id=collection.identifier) }}">View</a>
    </div>
  </div>
  {% else %}
    <p>No video collections.</p>
  {% endfor %}
</div>
{% endblock %}
"""


TEMPLATE_REGISTER = """
{% extends 'base.html' %}
{% block content %}
<h4>User Registration</h4>
<form method="post">
  <div class="form-group">
    <label>Username</label>
    <input class="form-control" name="user_name" required>
  </div>
  <div class="form-group">
    <label>Password</label>
    <input class="form-control" name="password" type="password" required>
  </div>
  <button class="btn btn-primary">Register</button>
</form>
{% endblock %}
"""


TEMPLATE_LOGIN = """
{% extends 'base.html' %}
{% block content %}
<h4>User Login</h4>
<form method="post">
  <div class="form-group">
    <label>Username</label>
    <input class="form-control" name="user_name" required>
  </div>
  <div class="form-group">
    <label>Password</label>
    <input class="form-control" name="password" type="password" required>
  </div>
  <button class="btn btn-primary">Login</button>
</form>
{% endblock %}
"""


TEMPLATE_CREATE_COLLECTION = """
{% extends 'base.html' %}
{% block content %}
<h4>New {{ 'Photo' if media_type=='photo' else 'Video' }} Collection</h4>
<form method="post">
  <div class="form-group">
    <label>Title</label>
    <input class="form-control" name="title" required>
  </div>
  <button class="btn btn-success">Create</button>
</form>
{% endblock %}
"""


TEMPLATE_VIEW_PHOTO_COLLECTION = """
{% extends 'base.html' %}
{% block content %}
<div class="d-flex justify-content-between">
  <h4>Photo Collection: {{ collection.title }}</h4>
  {% if current_user.is_authenticated and collection.owner == current_user %}
    <form method="post" action="{{ url_for('delete_photo_collection', collection_id=collection.identifier) }}">
      <button class="btn btn-danger btn-sm">Delete Collection</button>
    </form>
  {% endif %}
</div>
<hr>
{% if current_user.is_authenticated and collection.owner == current_user %}
<form method="post" enctype="multipart/form-data">
  <div class="form-group">
    <label>Upload Photo</label>
    <input type="file" class="form-control-file" name="file" accept="image/*" required>
  </div>
  <button class="btn btn-primary btn-sm">Upload</button>
</form>
<hr>
{% endif %}
<div class="row">
  {% for photo in collection.photos %}
  <div class="col-md-3 mb-3">
    <div class="card">
      <img src="{{ url_for('serve_uploaded_file', filename=photo.filename) }}" class="card-img-top" alt="Photo">
      {% if current_user.is_authenticated and collection.owner == current_user %}
      <form method="post" action="{{ url_for('delete_photo', photo_id=photo.identifier) }}">
        <button class="btn btn-danger btn-sm mt-1">Delete Photo</button>
      </form>
      {% endif %}
    </div>
  </div>
  {% else %}
    <p>No photos in this collection.</p>
  {% endfor %}
</div>
{% endblock %}
"""


TEMPLATE_VIEW_VIDEO_COLLECTION = """
{% extends 'base.html' %}
{% block content %}
<div class="d-flex justify-content-between">
  <h4>Video Collection: {{ collection.title }}</h4>
  {% if current_user.is_authenticated and collection.owner == current_user %}
    <form method="post" action="{{ url_for('delete_video_collection', collection_id=collection.identifier) }}">
      <button class="btn btn-danger btn-sm">Delete Collection</button>
    </form>
  {% endif %}
</div>
<hr>
{% if current_user.is_authenticated and collection.owner == current_user %}
<form method="post" enctype="multipart/form-data">
  <div class="form-group">
    <label>Upload Video</label>
    <input type="file" class="form-control-file" name="file" accept="video/*" required>
  </div>
  <button class="btn btn-primary btn-sm">Upload</button>
</form>
<hr>
{% endif %}
<div class="row">
  {% for video in collection.videos %}
  <div class="col-md-4 mb-3">
    <div class="card">
      <video controls class="w-100">
        <source src="{{ url_for('serve_uploaded_file', filename=video.filename) }}" type="{{ video.mime_type }}">
        Your browser does not support video.
      </video>
      {% if current_user.is_authenticated and collection.owner == current_user %}
      <form method="post" action="{{ url_for('delete_video', video_id=video.identifier) }}">
        <button class="btn btn-danger btn-sm mt-1">Delete Video</button>
      </form>
      {% endif %}
    </div>
  </div>
  {% else %}
    <p>No videos in this collection.</p>
  {% endfor %}
</div>
{% endblock %}
"""

# 建立模板映射
APPLICATION.jinja_loader = DictLoader({
    'base.html': TEMPLATE_BASE,
    'home.html': TEMPLATE_HOME,
    'register.html': TEMPLATE_REGISTER,
    'login.html': TEMPLATE_LOGIN,
    'create_collection.html': TEMPLATE_CREATE_COLLECTION,
    'view_photo_collection.html': TEMPLATE_VIEW_PHOTO_COLLECTION,
    'view_video_collection.html': TEMPLATE_VIEW_VIDEO_COLLECTION,
})

if __name__ == '__main__':
    APPLICATION.run(debug=True)
