import os
from flask import Flask, jsonify, render_template, request, redirect, url_for, session
import mysql.connector
from datetime import datetime
from dotenv import load_dotenv
from datetime import date 
# Завантажуємо приховані змінні з файлу .env
load_dotenv()

app = Flask(__name__)

# Тепер беремо секретний ключ із захищеного середовища
app.secret_key = os.getenv('SECRET_KEY')

# Налаштування бази даних також приховані
db_config = {
    'host': os.getenv('DB_HOST'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# ==========================================
# КЛІЄНТСЬКА ЧАСТИНА
# ==========================================

@app.route('/')
def index():
    """Головна сторінка: завантаження послуг для калькулятора"""
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT service_id, service_name, base_price FROM Services")
        services_data = cursor.fetchall()
        cursor.close()
        connection.close()
        return render_template('index.html', db_services=services_data)
    except Exception as e:
        print(f"Помилка калькулятора: {e}")
        return render_template('index.html', db_services=[])

@app.route('/services')
def services():
    return render_template('services.html')

# ==========================================
# 2. АВТЕНТИФІКАЦІЯ (Універсальна)
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
def login():
    # Якщо користувач вже залогінений, перенаправляємо його
    if 'user_role' in session:
        if session['user_role'] == 'admin':
            return redirect(url_for('admin_crm'))
        else:
            return redirect(url_for('cabinet'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # 1. Хардкод для Адміна (це нормально для MVP)
        if username == 'admin' and password == '123':
            session['user_role'] = 'admin'
            return redirect(url_for('admin_crm'))
            
        # 2. Динамічний пошук клієнта в Базі Даних
        else:
            try:
                conn = mysql.connector.connect(**db_config)
                cur = conn.cursor(dictionary=True)
                
                # Шукаємо клієнта за email 
                # У реальному житті тут також була б перевірка пароля
                cur.execute("SELECT customer_id, first_name FROM Customer WHERE email = %s", (username,))
                user = cur.fetchone()
                
                cur.close()
                conn.close()
                
                if user:
                    # Якщо знайшли в базі — записуємо його реальний ID в сесію
                    session['user_role'] = 'client'
                    session['customer_id'] = user['customer_id'] 
                    session['customer_name'] = user['first_name'] # Опціонально, щоб вітатися по імені
                    return redirect(url_for('cabinet'))
                else:
                    error = "Користувача з таким email не знайдено!"
                    
            except Exception as e:
                print("Помилка логіну:", e)
                error = "Помилка підключення до бази даних."

    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear() 
    return redirect(url_for('index'))

# ==========================================
# ОСОБИСТИЙ КАБІНЕТ КЛІЄНТА
# ==========================================

@app.route('/cabinet')
def cabinet():
    if session.get('user_role') != 'client':
        return redirect(url_for('login'))
        
    c_id = session.get('customer_id')
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        # 1. Активне замовлення
        cursor.execute("""
            SELECT o.order_id, o.total_amount, o.status, o.expected_delivery_date
            FROM Orders o
            WHERE o.customer_id = %s AND o.status NOT IN ('Delivered', 'Cancelled')
            ORDER BY o.order_date DESC LIMIT 1
        """, (c_id,))
        active = cursor.fetchone()
        
        # 2. Історія та мірки
        cursor.execute("SELECT * FROM Orders WHERE customer_id = %s ORDER BY order_date DESC", (c_id,))
        history = cursor.fetchall()
        
        cursor.execute("SELECT * FROM Measurement WHERE customer_id = %s", (c_id,))
        measurements = cursor.fetchone()
        
        cursor.close()
        connection.close()
        return render_template('cabinet.html', active_order=active, history_orders=history, measurements=measurements)
    except:
        return render_template('cabinet.html', active_order=None, history_orders=[], measurements=None)

# ==========================================
# АДМІНІСТРАТИВНА ПАНЕЛЬ (CRM)
# ==========================================

@app.route('/admin')
def admin_crm():
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
        
    try:
        connection = mysql.connector.connect(**db_config)
        cursor = connection.cursor(dictionary=True)
        
        # --- 1. KPI КАРТКИ ---
        cursor.execute("SELECT SUM(amount) as total FROM Payments")
        rev = cursor.fetchone()['total'] or 0
        
        cursor.execute("SELECT AVG(total_amount) as avg_chk FROM Orders")
        chk = cursor.fetchone()['avg_chk'] or 0
        
        cursor.execute("SELECT COUNT(*) as cnt FROM Orders WHERE status != 'Delivered'")
        act_cnt = cursor.fetchone()['cnt']
        
        cursor.execute("SELECT COUNT(*) as cnt FROM Inventory WHERE stock_quantity < 5")
        low_stk = cursor.fetchone()['cnt']

        # --- 2. СПИСОК ЗАМОВЛЕНЬ ---
        cursor.execute("""
            SELECT o.order_id, c.first_name, c.last_name, o.expected_delivery_date, o.status 
            FROM Orders o JOIN Customer c ON o.customer_id = c.customer_id 
            ORDER BY o.order_id DESC LIMIT 10
        """)
        orders = cursor.fetchall()

        # --- 3. ДАНІ ДЛЯ ГРАФІКА (Динамічна агрегація) ---
        cursor.execute("""
            SELECT DATE_FORMAT(transaction_moment, '%m') AS m_num, SUM(amount) AS m_rev
            FROM Payments WHERE transaction_moment >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
            GROUP BY m_num ORDER BY MIN(transaction_moment) ASC
        """)
        db_chart = cursor.fetchall()
        
        ua_months = {'01':'Січ', '02':'Лют', '03':'Бер', '04':'Квіт', '05':'Трав', '06':'Черв',
                     '07':'Лип', '08':'Серп', '09':'Вер', '10':'Жовт', '11':'Лист', '12':'Груд'}
        
        c_labels = [ua_months.get(r['m_num'], r['m_num']) for r in db_chart]
        c_values = [float(r['m_rev']) for r in db_chart]

        # --- 4. ДАНІ ДЛЯ МОДАЛЬНОГО ВІКНА ---
        cursor.execute("SELECT customer_id, first_name, last_name FROM Customer")
        custs = cursor.fetchall()
        cursor.execute("SELECT employee_id, first_name, last_name FROM Employees")
        emps = cursor.fetchall()

        cursor.close()
        connection.close()

        stats = {
            "revenue": "{:,.0f}".format(rev).replace(',', ' '),
            "avg_check": "{:,.0f}".format(chk).replace(',', ' '),
            "active_orders": act_cnt,
            "low_stock": low_stk
        }
        
        return render_template('crm.html', orders=orders, stats=stats, 
                               customers=custs, employees=emps,
                               chart_labels=c_labels, chart_values=c_values)
    except Exception as e:
        return f"Помилка CRM: {e}"
# ==========================================
# АНАЛІТИЧНІ ЗВІТИ (розділ 2.5 ТЗ)
# ==========================================
 
@app.route('/admin/reports')
def admin_reports():
    """Сторінка аналітичних звітів з SQL-запитами з розділу 2.5."""
    if session.get('user_role') != 'admin':
        return redirect(url_for('login'))
 
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
 
        # Запит 1: Рейтинг популярності та рентабельності послуг (ABC-аналіз)
        cursor.execute("""
            SELECT s.service_name,
                   SUM(oi.quantity)                       AS total_orders,
                   SUM(oi.quantity * s.base_price)        AS total_revenue,
                   ROUND(AVG(s.base_price), 2)            AS avg_price
            FROM Order_Items oi
            JOIN Services s ON oi.service_id = s.service_id
            JOIN Orders o   ON oi.order_id   = o.order_id
            WHERE o.status = 'Delivered'
            GROUP BY s.service_id, s.service_name
            ORDER BY total_revenue DESC
        """)
        services_report = cursor.fetchall()
 
        # Запит 2: Статистика продуктивності персоналу (KPI)
        cursor.execute("""
            SELECT e.first_name, e.last_name, e.position,
                   COUNT(o.order_id)          AS closed_orders,
                   SUM(o.total_amount)        AS total_sum,
                   ROUND(e.rate * COUNT(o.order_id), 2) AS calculated_salary
            FROM Employees e
            LEFT JOIN Orders o ON e.employee_id = o.employee_id
                               AND o.status = 'Delivered'
            WHERE e.is_active = TRUE
            GROUP BY e.employee_id, e.first_name, e.last_name, e.position, e.rate
            ORDER BY closed_orders DESC
        """)
        staff_report = cursor.fetchall()
 
        # Запит 3: Контроль заборгованостей клієнтів
        cursor.execute("""
            SELECT c.first_name, c.last_name, c.phone_number,
                   o.order_id,
                   o.total_amount,
                   COALESCE(SUM(p.amount), 0)                       AS paid,
                   o.total_amount - COALESCE(SUM(p.amount), 0)      AS debt
            FROM Orders o
            JOIN Customer c  ON o.customer_id  = c.customer_id
            LEFT JOIN Payments p ON o.order_id = p.order_id
            GROUP BY o.order_id, c.first_name, c.last_name,
                     c.phone_number, o.total_amount
            HAVING debt > 0
            ORDER BY debt DESC
        """)
        debts_report = cursor.fetchall()
 
        # Запит 4: VIP-клієнти (витрати вище середнього чека)
        cursor.execute("""
            WITH avg_check AS (
                SELECT AVG(total_amount) AS avg_val FROM Orders WHERE status = 'Delivered'
            )
            SELECT c.first_name, c.last_name, c.phone_number,
                   COUNT(o.order_id)   AS total_orders,
                   SUM(o.total_amount) AS total_spent
            FROM Customer c
            JOIN Orders o ON c.customer_id = o.customer_id
            WHERE o.status = 'Delivered'
            GROUP BY c.customer_id, c.first_name, c.last_name, c.phone_number
            HAVING total_spent > (SELECT avg_val FROM avg_check)
            ORDER BY total_spent DESC
        """)
        vip_report = cursor.fetchall()
 
        # Запит 5: Управління складом (залишок після списань)
        cursor.execute("""
            SELECT i.material_name, i.sku, i.unit,
                   i.stock_quantity                                         AS current_stock,
                   COALESCE(SUM(om.used_quantity), 0)                      AS total_used,
                   i.stock_quantity - COALESCE(SUM(om.used_quantity), 0)   AS available
            FROM Inventory i
            LEFT JOIN Order_Materials om ON i.material_id = om.material_id
            GROUP BY i.material_id, i.material_name, i.sku, i.unit, i.stock_quantity
            ORDER BY available ASC
        """)
        inventory_report = cursor.fetchall()
 
        cursor.close()
        conn.close()
 
        return render_template(
            'reports.html',
            services_report=services_report,
            staff_report=staff_report,
            debts_report=debts_report,
            vip_report=vip_report,
            inventory_report=inventory_report
        )
    except Exception as e:
        return f"Помилка звітів: {e}", 500
 
# ==========================================
# API ДЛЯ CRM
# ==========================================

@app.route('/add_order', methods=['POST'])
def add_order():
    if session.get('user_role') != 'admin': return redirect(url_for('login'))
    
    data = (request.form.get('customer_id'), request.form.get('employee_id'), 
            request.form.get('deadline'), request.form.get('amount'))
    
    try:
        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute("INSERT INTO Orders (customer_id, employee_id, expected_delivery_date, total_amount, status) VALUES (%s, %s, %s, %s, 'New')", data)
        conn.commit()
        cur.close()
        conn.close()
    except: pass
    return redirect(url_for('admin_crm'))

@app.route('/update_status', methods=['POST'])
def update_status():
    if session.get('user_role') != 'admin': return jsonify({"success": False}), 403
    
    data = request.get_json()
    try:
        conn = mysql.connector.connect(**db_config)
        cur = conn.cursor()
        cur.execute("UPDATE Orders SET status = %s WHERE order_id = %s", (data.get('status'), data.get('order_id')))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except: return jsonify({"success": False})

@app.route('/api/add_customer', methods=['POST'])
def api_add_customer():
    data = request.get_json()
    
    first_name = data.get('first_name')
    last_name = data.get('last_name', '') 
    phone = data.get('phone_number')
    reg_date = datetime.now().strftime('%Y-%m-%d')
    
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        sql = """INSERT INTO Customer (first_name, last_name, phone_number, registration_date) 
                 VALUES (%s, %s, %s, %s)"""
        cursor.execute(sql, (first_name, last_name, phone, reg_date))
        conn.commit()
        
        new_id = cursor.lastrowid
        full_name = f"{first_name} {last_name}".strip()
        
        return jsonify({"status": "success", "customer_id": new_id, "full_name": full_name})
    except Exception as e:
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
        return jsonify({"status": "error", "message": str(e)})
    finally:
        if 'cursor' in locals(): cursor.close()
        if 'conn' in locals() and conn.is_connected(): conn.close()
@app.route('/submit_form', methods=['POST'])
def submit_form():
    name = request.form.get('first_name')
    phone = request.form.get('phone_number')
    comment = request.form.get('comment')
    current_date = date.today()

    # Створюємо підключення за твоїм стандартом
    connection = mysql.connector.connect(**db_config)
    cursor = connection.cursor(dictionary=True)

    # 1. Перевіряємо, чи є клієнт за номером телефону
    cursor.execute("SELECT customer_id FROM customer WHERE phone_number = %s", (phone,))
    existing_customer = cursor.fetchone()

    if existing_customer:
        customer_id = existing_customer['customer_id']
    else:
        # Створюємо нового клієнта
        cursor.execute("""
            INSERT INTO customer (first_name, last_name, phone_number, registration_date)
            VALUES (%s, '', %s, %s)
        """, (name, phone, current_date))
        customer_id = cursor.lastrowid

    # 2. Створюємо замовлення (без деталей, лише шапка)
    cursor.execute("""
        INSERT INTO orders (customer_id, order_date, status)
        VALUES (%s, %s, 'New')
    """, (customer_id, current_date))
    
    # Отримуємо ID щойно створеного замовлення, щоб прив'язати до нього деталі
    order_id = cursor.lastrowid

    default_service_id = 8 
    
    cursor.execute("""
        INSERT INTO order_items (order_id, service_id, quantity, comments)
        VALUES (%s, %s, 1, %s)
    """, (order_id, default_service_id, comment))

    # ЗБЕРІГАЄМО ЗМІНИ через connection, а не db!
    connection.commit()
    
    # Закриваємо курсор і обов'язково саме з'єднання
    cursor.close()
    connection.close()

    # Повертаємо користувача на головну сторінку
    return redirect('/?status=success')
        
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000)