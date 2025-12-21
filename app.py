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

# Загрузка переменных окружения
load_dotenv()

# Получаем абсолютный путь к директории проекта
BASE_DIR = Path(__file__).parent.absolute()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY') or 'dev-secret-key-change-me-in-production'

# Настройка базы данных - используем абсолютный путь
database_path = BASE_DIR / 'site.db'
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URI') or f'sqlite:///{database_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

print(f"База данных будет создана по пути: {database_path}")
print(f"URI базы данных: {app.config['SQLALCHEMY_DATABASE_URI']}")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login_yandex'

# Yandex OAuth настройки
YANDEX_CLIENT_ID = os.getenv('YANDEX_CLIENT_ID')
YANDEX_CLIENT_SECRET = os.getenv('YANDEX_CLIENT_SECRET')

if not YANDEX_CLIENT_ID or not YANDEX_CLIENT_SECRET:
    print("WARNING: YANDEX_CLIENT_ID / YANDEX_CLIENT_SECRET not set — OAuth disabled.")

YANDEX_AUTHORIZATION_URL = 'https://oauth.yandex.ru/authorize'
YANDEX_TOKEN_URL = 'https://oauth.yandex.ru/token'
YANDEX_USERINFO_URL = 'https://login.yandex.ru/info'

client = WebApplicationClient(YANDEX_CLIENT_ID)

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

@app.route('/profile')
def profile():
    return render_template('profile.html')

@app.route('/comments', methods=['GET', 'POST'])
@login_required
def comments():
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(body=form.body.data, user_id=current_user.id)
        db.session.add(comment)
        db.session.commit()
        flash('Комментарий добавлен!', 'success')
        return redirect(url_for('comments'))
    
    comments_list = Comment.query.order_by(Comment.created_at.desc()).all()
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
    return redirect(url_for('comments'))

@app.route('/login_yandex')
def login_yandex():
    if not YANDEX_CLIENT_ID or not YANDEX_CLIENT_SECRET:
        flash('OAuth отключён — ключи не установлены.', 'danger')
        return redirect(url_for('index'))
    
    request_uri = client.prepare_request_uri(
        YANDEX_AUTHORIZATION_URL,
        redirect_uri=request.base_url + '/callback_yandex',
        scope=['login:info', 'login:email', 'login:avatar'],
    )
    return redirect(request_uri)

@app.route('/login_yandex/callback_yandex')
def callback_yandex():
    code = request.args.get('code')
    token_url, headers, body = client.prepare_token_request(
        YANDEX_TOKEN_URL,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(YANDEX_CLIENT_ID, YANDEX_CLIENT_SECRET),
    )
    
    client.parse_request_body_response(token_response.text)
    uri, headers, body = client.add_token(YANDEX_USERINFO_URL + '?format=json')
    userinfo_response = requests.get(uri, headers=headers, data=body)
    user_data = userinfo_response.json()
    
    unique_id = user_data.get('id')
    users_email = user_data.get('default_email')
    users_name = user_data.get('real_name') or user_data.get('display_name')
    
    user = User.query.filter_by(yandex_id=unique_id).first()
    if not user:
        user = User(yandex_id=unique_id, name=users_name, email=users_email)
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    return redirect(url_for('index'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # Убедимся, что мы в контексте приложения
    with app.app_context():
        try:
            # Создаем все таблицы
            db.create_all()
            print("Таблицы успешно созданы!")
        except Exception as e:
            print(f"Ошибка при создании таблиц: {e}")
            print("Проверьте права доступа к файловой системе")
    
    # Запускаем приложение
    app.run(debug=True, port=5001)
