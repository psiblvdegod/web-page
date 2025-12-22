#!/usr/bin/env python3
import os
import secrets
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, redirect, url_for, request, flash, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from oauthlib.oauth2 import WebApplicationClient
import requests
from dotenv import load_dotenv
import sys

# Разрешаем http для OAuth локально
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Загрузка переменных окружения
load_dotenv()

# Получаем абсолютный путь к директории проекта
BASE_DIR = Path(__file__).parent.absolute()

# ============================
# ОПРЕДЕЛЕНИЕ РЕДИРЕКТОВ В ЗАВИСИМОСТИ ОТ TARGET
# ============================
TARGET = os.getenv('TARGET', '').upper().strip()
REMOTE_ADDRESS = os.getenv('REMOTE_ADDRESS', '').strip()

# Проверяем корректность переменной TARGET
if TARGET not in ['LOCAL', 'REMOTE']:
    print("❌ ERROR: TARGET environment variable is not set correctly")
    print("   TARGET should be either 'LOCAL' or 'REMOTE'")
    print("   - LOCAL: for development on localhost")
    print("   - REMOTE: for deployment on a remote server")
    sys.exit(1)

# Определяем URI в зависимости от TARGET
if TARGET == 'LOCAL':
    DEFAULT_YANDEX_REDIRECT_URI = 'http://127.0.0.1:5001/login/yandex/authorized'
    DEFAULT_GOOGLE_REDIRECT_URI = 'http://127.0.0.1:5001/login/google/authorized'
elif TARGET == 'REMOTE':
    if not REMOTE_ADDRESS:
        print("❌ ERROR: TARGET is set to REMOTE but REMOTE_ADDRESS is not defined in .env")
        print("   Please set REMOTE_ADDRESS to your server's IP or domain name")
        print("   Example: REMOTE_ADDRESS=yourdomain.com or REMOTE_ADDRESS=192.168.1.100")
        sys.exit(1)

    # Убираем протокол если он указан и завершающий слеш
    REMOTE_ADDRESS = REMOTE_ADDRESS.replace('http://', '').replace('https://', '').rstrip('/')
    DEFAULT_YANDEX_REDIRECT_URI = f'http://{REMOTE_ADDRESS}/login/yandex/authorized'
    DEFAULT_GOOGLE_REDIRECT_URI = f'http://{REMOTE_ADDRESS}/login/google/authorized'

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or secrets.token_hex(32)

# Создаем папку instance, если её нет
instance_path = BASE_DIR / 'instance'
os.makedirs(instance_path, exist_ok=True)

# Настройка базы данных SQLite (старая схема с yandex_id)
database_path = instance_path / 'site.db'
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

print(f"База данных будет создана по пути: {database_path}")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'index'

# ============================
# НАСТРОЙКИ OAuth (Яндекс + Google)
# ============================
YANDEX_CLIENT_ID = os.getenv('YANDEX_CLIENT_ID')
YANDEX_CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET')
YANDEX_REDIRECT_URI = os.getenv('YANDEX_REDIRECT_URI') or DEFAULT_YANDEX_REDIRECT_URI

GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI') or DEFAULT_GOOGLE_REDIRECT_URI

# Проверка настроек
if not YANDEX_CLIENT_ID or not YANDEX_CLIENT_SECRET:
    print("⚠️  YANDEX_CLIENT_ID / YANDEX_CLIENT_SECRET не установлены — Yandex OAuth отключен.")

if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    print("⚠️  GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET не установлены — Google OAuth отключен.")

# Клиенты OAuth
yandex_client = WebApplicationClient(YANDEX_CLIENT_ID) if YANDEX_CLIENT_ID else None
google_client = WebApplicationClient(GOOGLE_CLIENT_ID) if GOOGLE_CLIENT_ID else None

# ============================
# МОДЕЛИ БАЗЫ ДАННЫХ (СТАРАЯ СХЕМА)
# ============================
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    yandex_id = db.Column(db.String(255), unique=True)  # Оставляем как есть
    google_id = db.Column(db.String(255), unique=True)  # Добавляем новое поле
    name = db.Column(db.String(255))
    email = db.Column(db.String(255), unique=True)
    comments = db.relationship('Comment', backref='user', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# ============================
# ФОРМЫ
# ============================
class CommentForm(FlaskForm):
    body = TextAreaField('Комментарий', validators=[DataRequired(), Length(min=1, max=500)])
    submit = SubmitField('Отправить')

# ============================
# LOGIN MANAGER
# ============================
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ============================
# ДАННЫЕ ДЛЯ GTM
# ============================
@app.before_request
def before_request():
    """Подготовка данных для Google Tag Manager перед каждым запросом"""
    g.gtm_data = {
        'page_path': request.path,
        'page_url': request.url,
        'user_agent': request.user_agent.string if request.user_agent else None,
        'user_ip': request.remote_addr,
        'user_authenticated': current_user.is_authenticated,
        'user_id': current_user.id if current_user.is_authenticated else None,
        'user_email': current_user.email if current_user.is_authenticated else None,
        'auth_method': None,
        'gtm_events': []  # Список событий для отправки в GTM
    }
    
    if current_user.is_authenticated:
        if current_user.yandex_id:
            g.gtm_data['auth_method'] = 'yandex'
        elif current_user.google_id:
            g.gtm_data['auth_method'] = 'google'

# ============================
# ОСНОВНЫЕ МАРШРУТЫ
# ============================
@app.route('/')
def index():
    g.gtm_data['gtm_events'].append('page_view_home')
    return render_template('index.html')

@app.route('/about')
def about():
    g.gtm_data['gtm_events'].append('page_view_about')
    return render_template('about.html')

@app.route('/contacts')
def contacts():
    g.gtm_data['gtm_events'].append('page_view_contacts')
    return render_template('contacts.html')

@app.route('/comments', methods=['GET', 'POST'])
def comments():
    g.gtm_data['gtm_events'].append('page_view_comments')
    
    form = CommentForm()
    comments_list = Comment.query.order_by(Comment.created_at.desc()).all()

    if current_user.is_authenticated and form.validate_on_submit():
        comment = Comment(body=form.body.data, user_id=current_user.id)
        db.session.add(comment)
        db.session.commit()
        flash('Комментарий добавлен!', 'success')
        
        # Добавляем событие для GTM
        g.gtm_data['gtm_events'].append('comment_added')
        g.gtm_data['comment_length'] = len(form.body.data)
        
        return redirect(url_for('comments'))

    return render_template('comments.html', comments=comments_list, form=form)

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        flash('Вы можете удалять только свои комментарии.', 'danger')
        return redirect(url_for('comments'))

    db.session.delete(comment)
    db.session.commit()
    flash('Комментарий удалён.', 'success')
    
    # Добавляем событие для GTM
    g.gtm_data['gtm_events'].append('comment_deleted')
    
    return redirect(url_for('comments'))

# ============================
# Яндекс OAuth (ИСПРАВЛЕННЫЙ КОД)
# ============================
@app.route('/login/yandex')
def login_yandex():
    if not yandex_client:
        flash('Yandex OAuth отключён — ключи не установлены.', 'danger')
        return redirect(url_for('comments'))

    request_uri = yandex_client.prepare_request_uri(
        'https://oauth.yandex.ru/authorize',
        redirect_uri=YANDEX_REDIRECT_URI,
        scope=['login:info', 'login:email', 'login:avatar'],
    )
    return redirect(request_uri)

@app.route('/login/yandex/authorized')
def callback_yandex():
    if not yandex_client:
        flash('Yandex OAuth отключён — ключи не установлены.', 'danger')
        return redirect(url_for('comments'))

    code = request.args.get('code')
    token_url, headers, body = yandex_client.prepare_token_request(
        'https://oauth.yandex.ru/token',
        authorization_response=request.url,
        redirect_url=YANDEX_REDIRECT_URI,
        code=code
    )

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET),
    )

    yandex_client.parse_request_body_response(token_response.text)
    uri, headers, body = yandex_client.add_token('https://login.yandex.ru/info?format=json')
    userinfo_response = requests.get(uri, headers=headers, data=body)
    user_data = userinfo_response.json()

    unique_id = user_data.get('id')
    users_email = user_data.get('default_email')
    users_name = user_data.get('real_name') or user_data.get('display_name')

    # Ищем пользователя по yandex_id
    user = User.query.filter_by(yandex_id=unique_id).first()
    if not user:
        # Проверяем, может email уже есть от Google
        existing_user = User.query.filter_by(email=users_email).first()
        if existing_user:
            # Обновляем yandex_id для существующего пользователя
            existing_user.yandex_id = unique_id
            db.session.commit()
            user = existing_user
        else:
            # Создаем нового пользователя
            user = User(yandex_id=unique_id, name=users_name, email=users_email)
            db.session.add(user)
            db.session.commit()

    login_user(user)
    flash(f'Вы успешно вошли через Yandex как {user.name or user.email}!', 'success')
    
    # Добавляем событие для GTM
    g.gtm_data['gtm_events'].append('yandex_login_success')
    g.gtm_data['user_email'] = user.email
    
    return redirect(url_for('comments'))

# ============================
# Google OAuth (ИСПРАВЛЕННЫЙ КОД)
# ============================
@app.route('/login/google')
def login_google():
    if not google_client:
        flash('Google OAuth отключён — ключи не установлены.', 'danger')
        return redirect(url_for('comments'))

    request_uri = google_client.prepare_request_uri(
        'https://accounts.google.com/o/oauth2/auth',
        redirect_uri=GOOGLE_REDIRECT_URI,
        scope=[
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile'
        ],
        access_type='offline',
        prompt='consent'
    )
    return redirect(request_uri)

@app.route('/login/google/authorized')
def callback_google():
    if not google_client:
        flash('Google OAuth отключён — ключи не установлены.', 'danger')
        return redirect(url_for('comments'))

    code = request.args.get('code')
    token_url, headers, body = google_client.prepare_token_request(
        'https://oauth2.googleapis.com/token',
        authorization_response=request.url,
        redirect_url=GOOGLE_REDIRECT_URI,
        code=code
    )

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    google_client.parse_request_body_response(token_response.text)
    uri, headers, body = google_client.add_token('https://www.googleapis.com/oauth2/v3/userinfo')
    userinfo_response = requests.get(uri, headers=headers, data=body)
    user_data = userinfo_response.json()

    unique_id = user_data.get('sub')
    users_email = user_data.get('email')
    users_name = user_data.get('name')

    # Ищем пользователя по google_id
    user = User.query.filter_by(google_id=unique_id).first()
    if not user:
        # Проверяем, может email уже есть от Yandex
        existing_user = User.query.filter_by(email=users_email).first()
        if existing_user:
            # Обновляем google_id для существующего пользователя
            existing_user.google_id = unique_id
            db.session.commit()
            user = existing_user
        else:
            # Создаем нового пользователя
            user = User(google_id=unique_id, name=users_name, email=users_email)
            db.session.add(user)
            db.session.commit()

    login_user(user)
    flash(f'Вы успешно вошли через Google как {user.name or user.email}!', 'success')
    
    # Добавляем событие для GTM
    g.gtm_data['gtm_events'].append('google_login_success')
    g.gtm_data['user_email'] = user.email
    
    return redirect(url_for('comments'))

# ============================
# Выход
# ============================
@app.route('/logout')
@login_required
def logout():
    # Добавляем событие для GTM перед выходом
    g.gtm_data['gtm_events'].append('user_logout')
    
    logout_user()
    flash('Вы вышли из системы.', 'info')
    return redirect(url_for('index'))

# ============================
# КОНТЕКСТНЫЙ ПРОЦЕССОР ДЛЯ GTM
# ============================
@app.context_processor
def inject_gtm_data():
    """Внедряет данные GTM во все шаблоны"""
    gtm_data = getattr(g, 'gtm_data', {})
    
    # Формируем JSON для передачи в JavaScript
    gtm_json = {
        'user_authenticated': gtm_data.get('user_authenticated', False),
        'user_id': gtm_data.get('user_id'),
        'user_email': gtm_data.get('user_email'),
        'auth_method': gtm_data.get('auth_method'),
        'page_path': gtm_data.get('page_path', ''),
        'gtm_events': gtm_data.get('gtm_events', [])
    }
    
    # Фильтруем None значения
    gtm_json = {k: v for k, v in gtm_json.items() if v is not None}
    
    return {
        'gtm_data': gtm_json,
        'gtm_events_json': gtm_data.get('gtm_events', [])
    }

# ============================
# ЗАПУСК ПРИЛОЖЕНИЯ
# ============================
if __name__ == '__main__':
    with app.app_context():
        try:
            # Просто создаем таблицы, если их нет
            db.create_all()
            print("✅ Таблицы базы данных готовы.")

            # Проверяем, есть ли новые колонки
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            if inspector.has_table('user'):
                columns = [col['name'] for col in inspector.get_columns('user')]
                if 'google_id' not in columns:
                    print("⚠️  Внимание: в таблице user нет колонки google_id.")
                    print("   При первом входе через Google будет создан новый пользователь.")

        except Exception as e:
            print(f"❌ Ошибка при инициализации базы данных: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 60)
    print(f"🎯 TARGET mode: {TARGET}")
    print(f"🏠 Yandex redirect URI: {YANDEX_REDIRECT_URI}")
    print(f"🔵 Google redirect URI: {GOOGLE_REDIRECT_URI}")
    print("📊 GTM настроен для сбора метрик")
    print("🚀 Приложение запускается на http://127.0.0.1:5001")
    print("=" * 60)

    app.run(host='0.0.0.0', port=5001, debug=(TARGET == 'LOCAL'))
    