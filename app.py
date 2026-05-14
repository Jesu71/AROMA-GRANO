
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from user_agents import parse
import os
import random
from functools import wraps
from datetime import datetime, timedelta
from flask_cors import CORS
from dotenv import load_dotenv

# ===================== CONFIG =====================

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY", "super-secret-key")
CORS(app)

# ===================== SUPABASE =====================

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise Exception("Faltan SUPABASE_URL o SUPABASE_KEY en el archivo .env")

supabase: Client = create_client(url, key)

# ===================== CONSTANTES =====================

MESES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

# ===================== HELPERS =====================

def format_order_date(date_str):
    if not date_str:
        return ''

    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        dt_co = dt - timedelta(hours=5)
        return f"{dt_co.day} de {MESES_ES[dt_co.month]}"
    except:
        return str(date_str)[:10]


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin', False):
            flash('No tienes permisos para acceder a esta área', 'error')
            return redirect(url_for('login'))

        return f(*args, **kwargs)

    return decorated_function


def create_notification(notification_type, message, details=None):
    try:
        supabase.table("notifications").insert({
            "type": notification_type,
            "message": message,
            "details": details,
            "is_read": False
        }).execute()

    except Exception as e:
        print(f"Error creando notificación: {e}")


def get_cart_count(user_id):
    try:
        cart_data = (
            supabase
            .table("cart_items")
            .select("id")
            .eq("user_id", user_id)
            .execute()
        )

        return len(cart_data.data) if cart_data.data else 0

    except:
        return 0


def clean_orphan_cart_items(user_id):
    try:
        cart_data = (
            supabase
            .table("cart_items")
            .select("product_id, id")
            .eq("user_id", user_id)
            .execute()
        )

        if not cart_data.data:
            return []

        products_data = supabase.table("products").select("id").execute()

        existing_ids = (
            set(p['id'] for p in products_data.data)
            if products_data.data else set()
        )

        orphan_ids = []
        orphan_product_ids = []

        for item in cart_data.data:
            if item['product_id'] not in existing_ids:
                orphan_ids.append(item['id'])
                orphan_product_ids.append(item['product_id'])

        if orphan_ids:
            for orphan_id in orphan_ids:
                (
                    supabase
                    .table("cart_items")
                    .delete()
                    .eq("id", orphan_id)
                    .execute()
                )

        return orphan_product_ids

    except Exception as e:
        print(f"Error limpiando carrito: {e}")
        return []


def get_active_products():
    try:
        products_data = supabase.table("products").select("*").execute()

        if not products_data.data:
            return []

        active = [
            p for p in products_data.data
            if p.get('status', 'active') == 'active'
        ]

        return active if active else products_data.data

    except Exception as e:
        print(f"Error obteniendo productos: {e}")
        return []


def get_cheapest_product():
    active = get_active_products()

    if not active:
        return None

    return min(active, key=lambda p: p.get('price', 999999))


def get_random_product():
    active = get_active_products()

    if not active:
        return None

    return random.choice(active)


def init_db():
    try:
        user = (
            supabase
            .table("users")
            .select("*")
            .eq("email", "admin@correo.com")
            .execute()
        )

        if not user.data:
            supabase.table("users").insert({
                "full_name": "Administrador",
                "email": "admin@correo.com",
                "password": "admin",
                "is_admin": True,
                "loyalty_points": 0
            }).execute()

        supabase.table("products").select("*").limit(1).execute()

    except Exception as e:
        print(f"Error en init_db: {e}")

# ===================== AUTH =====================

@app.route('/', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()

        try:
            user = (
                supabase
                .table("users")
                .select("*")
                .eq("email", email)
                .eq("password", password)
                .execute()
            )

            if user.data:

                user_data = user.data[0]

                session['user_id'] = user_data['id']
                session['email'] = user_data['email']
                session['full_name'] = user_data['full_name']
                session['is_admin'] = user_data.get('is_admin', False)

                if session['is_admin']:
                    return redirect(url_for('admin_dashboard'))

                return redirect(url_for('dashboard'))

            flash('Correo o contraseña incorrectos', 'error')

        except Exception as e:
            print(e)
            flash('Error iniciando sesión', 'error')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        confirm_password = request.form.get('confirm_password', '').strip()

        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'error')
            return redirect(url_for('register'))

        existing_user = (
            supabase
            .table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        if existing_user.data:
            flash('El correo ya está registrado', 'error')
            return redirect(url_for('register'))

        try:
            supabase.table("users").insert({
                "full_name": full_name,
                "email": email,
                "password": password,
                "is_admin": False,
                "loyalty_points": 0
            }).execute()

            create_notification(
                'user_registered',
                f'Nuevo usuario registrado: {full_name}',
                email
            )

            flash('¡Registro exitoso!', 'success')

            return redirect(url_for('login'))

        except Exception as e:
            print(e)
            flash('Error registrando usuario', 'error')

    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ===================== DASHBOARD =====================

@app.route('/dashboard')
def dashboard():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_agent = request.headers.get('User-Agent')
    agent = parse(user_agent)

    category = request.args.get('category', 'all')
    origin = request.args.get('origin', 'all')

    query = supabase.table("products").select("*")

    if category != 'all':
        query = query.eq("category", category)

    result = query.execute()

    products = result.data if result.data else []

    if origin != 'all':

        filtered_products = []

        for product in products:

            name = product.get('name', '')

            if origin == 'Etiopía - Sidamo' and (
                'Espresso' in name or 'Sidamo' in name
            ):
                filtered_products.append(product)

            elif origin == 'Colombia - Huila' and (
                'Colombia' in name or 'Huila' in name
            ):
                filtered_products.append(product)

            elif origin == 'Costa Rica - Tarrazú' and (
                'Costa Rica' in name or 'Tarrazú' in name
            ):
                filtered_products.append(product)

        products = filtered_products

    cart_count = get_cart_count(session['user_id'])

    if agent.is_mobile:
        return render_template(
            'dashboard_mobile.html',
            products=products,
            category=category,
            origin=origin,
            cart_count=cart_count
        )

    return render_template(
        'dashboard_pc.html',
        products=products,
        category=category,
        origin=origin,
        cart_count=cart_count
    )

# ===================== CARRITO =====================

@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():

    if 'user_id' not in session:
        return jsonify({
            "success": False,
            "message": "No autenticado"
        }), 401

    try:

        user_id = session['user_id']
        product_id = request.form.get('product_id')

        product_check = (
            supabase
            .table("products")
            .select("id, name")
            .eq("id", product_id)
            .execute()
        )

        if not product_check.data:
            flash('Producto no disponible', 'error')
            return redirect(url_for('dashboard'))

        product_name = request.form.get('product_name')
        product_image_url = request.form.get('product_image_url', '')
        origin = request.form.get('origin', 'Etiopía')
        milk_type = request.form.get('milk_type', 'Entera')
        temperature = request.form.get('temperature', 'Caliente')

        sweetness = int(request.form.get('sweetness', 50))
        quantity = int(request.form.get('quantity', 1))

        unit_price = int(request.form.get('unit_price', 0))
        milk_surcharge = int(request.form.get('milk_surcharge', 0))

        total_price = (unit_price + milk_surcharge) * quantity

        supabase.table("cart_items").insert({
            "user_id": user_id,
            "product_id": product_id,
            "product_name": product_name,
            "product_image_url": product_image_url,
            "origin": origin,
            "milk_type": milk_type,
            "temperature": temperature,
            "sweetness": sweetness,
            "quantity": quantity,
            "unit_price": unit_price,
            "milk_surcharge": milk_surcharge,
            "total_price": total_price
        }).execute()

        flash('Producto añadido al carrito', 'success')

        return redirect(url_for('orders'))

    except Exception as e:
        print(e)
        flash('Error añadiendo producto', 'error')
        return redirect(url_for('dashboard'))


@app.route('/orders')
def orders():

    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    clean_orphan_cart_items(user_id)

    cart_data = (
        supabase
        .table("cart_items")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )

    cart_items = cart_data.data if cart_data.data else []

    total = sum(item['total_price'] for item in cart_items)

    cart_count = len(cart_items)

    user_agent = request.headers.get('User-Agent')
    agent = parse(user_agent)

    if agent.is_mobile:
        return render_template(
            'orders_mobile.html',
            cart_items=cart_items,
            total=total,
            cart_count=cart_count
        )

    return render_template(
        'orders_pc.html',
        cart_items=cart_items,
        total=total,
        cart_count=cart_count
    )

# ===================== ADMIN =====================

@app.route('/admin')
@admin_required
def admin_dashboard():

    products_data = supabase.table("products").select("*").execute()

    products = products_data.data if products_data.data else []

    categories = list(set([
        p['category']
        for p in products
        if 'category' in p
    ]))

    active_count = sum(
        1 for p in products
        if p.get('status', 'active') == 'active'
    )

    availability = (
        round((active_count / len(products)) * 100)
        if products else 0
    )

    return render_template(
        'admin/dashboard.html',
        products=products,
        categories=categories,
        availability=availability
    )

# ===================== START =====================

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)