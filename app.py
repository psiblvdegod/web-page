#!./venv/bin/python3
import os
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf import FlaskForm
from wtforms import TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length
from oauthlib.oauth2 import WebApplicationClient
import requests
from dotenv import load_dotenv

# Разрешаем http для OAuth локально
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Загрузка переменных окружения
load_dotenv()

# Получаем абсолютный путь к директории проекта
BASE_DIR = Path(__file__).parent.absolute()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'supersecretkey'

# Создаем папку instance, если её нет
instance_path = BASE_DIR / 'instance'
os.makedirs(instance_path, exist_ok=True)
print(f"Директория instance создана/проверена: {instance_path}")

# Настройка базы данных SQLite - ИСПРАВЛЕНО: используем абсолютный путь
database_path = instance_path / 'site.db'
database_uri = f"sqlite:///{database_path}"
app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

print(f"База данных будет создана по пути: {database_path}")
print(f"URI базы данных: {app.config['SQLALCHEMY_DATABASE_URI']}")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_yandex'

# Yandex OAuth настройки - ИСПРАВЛЕНО: убраны лишние пробелы в URL
YANDEX_CLIENT_ID = os.getenv('YANDEX_CLIENT_ID')
YANDEX_CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET')
YANDEX_REDIRECT_URI = os.getenv('YANDEX_REDIRECT_URI')  # например: http://127.0.0.1:5001/login_yandex/callback_yandex

if not YANDEX_CLIENT_ID or not YANDEX_CLIENT_SECRET or not YANDEX_REDIRECT_URI:
    print("WARNING: YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET или YANDEX_REDIRECT_URI не установлены — OAuth может не работать.")

YANDEX_AUTHORIZATION_URL = 'https://oauth.yandex.ru/authorize'
YANDEX_TOKEN_URL = 'https://oauth.yandex.ru/token'
YANDEX_USERINFO_URL = 'https://login.yandex.ru/info'

# Инициализация OAuth клиента только если есть необходимые данные
if YANDEX_CLIENT_ID:
    client = WebApplicationClient(YANDEX_CLIENT_ID)
else:
    client = None
    print("OAuth клиент не инициализирован из-за отсутствия YANDEX_CLIENT_ID")

# Модели
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    yandex_id = db.Column(db.String(255), unique=True)
    name = db.Column(db.String(255))
    email = db.Column(db.String(255), unique=True)
    comments = db.relationship('Comment', backref='user', lazy=True)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Форма комментария
class CommentForm(FlaskForm):
    body = TextAreaField('Комментарий', validators=[DataRequired(), Length(min=1, max=500)])
    submit = SubmitField('Отправить')

# Логин-менеджер
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Роуты
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/contacts')
def contacts():
    return render_template('contacts.html')

@app.route('/comments', methods=['GET', 'POST'])
def comments():
    form = CommentForm()
    comments_list = Comment.query.order_by(Comment.created_at.desc()).all()
    
    # Если пользователь авторизован — обработка отправки
    if current_user.is_authenticated and form.validate_on_submit():
        comment = Comment(body=form.body.data, user_id=current_user.id)
        db.session.add(comment)
        try:
            db.session.commit()
            flash('Комментарий добавлен!', 'success')
            return redirect(url_for('comments'))
        except Exception as e:
            db.session.rollback()
            flash(f'Ошибка при добавлении комментария: {str(e)}', 'danger')
    
    return render_template('comments.html', comments=comments_list, form=form)

@app.route('/delete_comment/<int:comment_id>', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if comment.user_id != current_user.id:
        flash('Вы можете удалять только свои комментарии.', 'danger')
        return redirect(url_for('comments'))
    
    db.session.delete(comment)
    try:
        db.session.commit()
        flash('Комментарий удалён.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка при удалении комментария: {str(e)}', 'danger')
    
    return redirect(url_for('comments'))

@app.route('/login_yandex')
def login_yandex():
    if not client:
        flash('OAuth не настроен — обратитесь к администратору.', 'danger')
        return redirect(url_for('index'))
    
    try:
        request_uri = client.prepare_request_uri(
            YANDEX_AUTHORIZATION_URL,
            redirect_uri=YANDEX_REDIRECT_URI,
            scope=['login:info', 'login:email'],
        )
        return redirect(request_uri)
    except Exception as e:
        flash(f'Ошибка при подготовке запроса к Yandex OAuth: {str(e)}', 'danger')
        return redirect(url_for('index'))

@app.route('/login_yandex/callback_yandex')
def callback_yandex():
    if not client:
        flash('OAuth не настроен — обратитесь к администратору.', 'danger')
        return redirect(url_for('index'))
    
    code = request.args.get('code')
    if not code:
        flash('Не получен код авторизации от Yandex.', 'danger')
        return redirect(url_for('index'))
    
    try:
        token_url, headers, body = client.prepare_token_request(
            YANDEX_TOKEN_URL,
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
        token_response.raise_for_status()
        
        client.parse_request_body_response(token_response.text)
        uri, headers, body = client.add_token(YANDEX_USERINFO_URL + '?format=json')
        userinfo_response = requests.get(uri, headers=headers, data=body)
        userinfo_response.raise_for_status()
        
        user_data = userinfo_response.json()
        
        unique_id = str(user_data.get('id'))
        users_email = user_data.get('default_email')
        users_name = user_data.get('real_name') or user_data.get('display_name') or user_data.get('login')
        
        if not unique_id:
            flash('Не удалось получить ID пользователя от Yandex.', 'danger')
            return redirect(url_for('index'))
        
        user = User.query.filter_by(yandex_id=unique_id).first()
        if not user:
            user = User(yandex_id=unique_id, name=users_name, email=users_email)
            db.session.add(user)
            db.session.commit()
        
        login_user(user)
        flash(f'Добро пожаловать, {users_name}!', 'success')
        return redirect(url_for('index'))
    
    except requests.exceptions.RequestException as e:
        flash(f'Ошибка при запросе к API Yandex: {str(e)}', 'danger')
    except Exception as e:
        flash(f'Ошибка авторизации: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы успешно вышли из системы.', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Создаем все таблицы в базе данных
    with app.app_context():
        try:
            # Проверяем, можем ли мы записать в директорию базы данных
            test_file = instance_path / '.write_test'
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print("Проверка прав на запись в директорию instance: УСПЕШНО")
            
            # Создаем таблицы
            db.create_all()
            print("Таблицы успешно созданы!")
            
            # Проверяем, что файл базы данных создан
            if database_path.exists():
                print(f"Файл базы данных создан: {database_path}")
                print(f"Размер файла: {database_path.stat().st_size} байт")
            else:
                print("ПРЕДУПРЕЖДЕНИЕ: Файл базы данных не найден после создания")
                
        except Exception as e:
            print(f"КРИТИЧЕСКАЯ ОШИБКА при создании таблиц: {e}")
            print(f"Детали ошибки: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            print("Проверьте:")
            print(f"1. Права на запись в директорию: {instance_path}")
            print(f"2. Существует ли родительская директория: {instance_path.parent}")
            print(f"3. Достаточно ли места на диске")
    
    app.run(debug=True, port=5001, host='0.0.0.0')
