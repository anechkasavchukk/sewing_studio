from flask import Flask, jsonify, render_template, request, redirect, url_for, session
import mysql.connector

# Створюємо наш веб-сервер
app = Flask(__name__)

# СЕКРЕТНИЙ КЛЮЧ 
app.secret_key = 'super_secret_key_eleniko_2026'

# Налаштування підключення до Бази Даних
db_config = {
    'host': '127.0.0.1',
    'user': 'root',          # логін у Workbench 
    'password': 'Ann_savchuk13!',  # пароль від бази 
    'database': 'sewing_studio' 
}

ADMIN_LOGIN = "admin"
ADMIN_PASSWORD = "123"

# Головна сторінка 
@app.route('/')
def index():
    return render_template('index.html')

# --- МАРШРУТ ДЛЯ КАБІНЕТУ ---
@app.route('/cabinet')
def cabinet():
    return render_template('cabinet.html')
   
# --- МАРШРУТ ДЛЯ ПОСЛУГ ---
@app.route('/services')
def services():
    return render_template('services.html')

# ==========================================
#        СИСТЕМА ВХОДУ (АВТОРИЗАЦІЯ)
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        # Беремо дані, які користувач ввів у форму
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Перевіряємо, чи співпадають вони з нашими
        if username == ADMIN_LOGIN and password == ADMIN_PASSWORD:
            session['admin_logged_in'] = True 
            return redirect(url_for('admin_crm')) 
        else:
            error = "Невірний логін або пароль!"
            
    # Якщо це звичайний перехід на сторінку (GET) або помилка:
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():

    session.pop('admin_logged_in', None)
    return redirect(url_for('index'))

# --- АДМІНІСТРАТИВНА ЧАСТИНА (CRM) ---
@app.route('/admin')
def admin_crm():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login')) # Якщо ні - женемо на сторінку входу
    return render_template('crm.html') # Змінив на crm.html, як ми робили в дизайні

# --- Тестовий маршрут БД ---
@app.route('/api/test-db')
def test_db():
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Customer;") # Змінив Employees на Customer (бо в базі у нас Customer)
        data = cursor.fetchall()
        cursor.close()
        connection.close()
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Помилка підключення: {str(e)}"})

# ==========================================
# ЗАПУСК СЕРВЕРА 
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)