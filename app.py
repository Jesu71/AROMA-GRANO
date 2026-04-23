from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from user_agents import parse
import os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuración de Supabase
url: str = "https://lmvulmiiuoknceifvrcy.supabase.co"
key: str = "sb_secret_-jqmUZ8z63E4ymW9UxHa3w_dkd0Xd9i"
supabase: Client = create_client(url, key)

# Decorador para verificar si el usuario es administrador
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin', False):
            flash('No tienes permisos para acceder a esta área', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper para crear notificaciones en la base de datos
def create_notification(notification_type, message, details=None):
    """Crea una notificación en la base de datos"""
    try:
        notification_data = {
            "type": notification_type,
            "message": message,
            "details": details,
            "is_read": False
        }
        supabase.table("notifications").insert(notification_data).execute()
    except Exception as e:
        print(f"Error creating notification: {e}")

def init_db():
    try:
        user = supabase.table("users").select("*").eq("email", "admin@correo.com").execute()
        if not user.data:
            supabase.table("users").insert({
                "full_name": "Administrador",
                "email": "admin@correo.com",
                "password": "admin",
                "is_admin": True
            }).execute()

        supabase.table("products").select("*").limit(1).execute()
    except Exception as e:
        print(f"Error en init_db: {e}")

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = supabase.table("users").select("*").eq("email", email).eq("password", password).execute()

        if user.data:
            user_data = user.data[0]
            session['user_id'] = user_data['id']
            session['email'] = user_data['email']
            session['full_name'] = user_data['full_name']
            session['is_admin'] = user_data.get('is_admin', False)

            if session['is_admin']:
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Correo o contraseña incorrectos', 'error')

    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Las contraseñas no coinciden', 'error')
            return redirect(url_for('register'))

        existing_user = supabase.table("users").select("*").eq("email", email).execute()
        if existing_user.data:
            flash('El correo ya está registrado', 'error')
            return redirect(url_for('register'))

        supabase.table("users").insert({
            "full_name": full_name,
            "email": email,
            "password": password
        }).execute()

        # Crear notificación de nuevo usuario registrado
        create_notification('user_registered', f'Nuevo usuario registrado: {full_name}', email)

        flash('¡Registro exitoso! Ahora puedes iniciar sesión.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')

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

    products = query.execute().data

    if origin != 'all':
        filtered_products = []
        for product in products:
            if origin == 'Etiopía - Sidamo' and ('Espresso' in product['name'] or 'Sidamo' in product['name']):
                filtered_products.append(product)
            elif origin == 'Colombia - Huila' and ('Colombia' in product['name'] or 'Huila' in product['name']):
                filtered_products.append(product)
            elif origin == 'Costa Rica - Tarrazú' and ('Costa Rica' in product['name'] or 'Tarrazú' in product['name']):
                filtered_products.append(product)
        products = filtered_products

    if agent.is_mobile:
        return render_template('dashboard_mobile.html', products=products, category=category, origin=origin)
    else:
        return render_template('dashboard_pc.html', products=products, category=category, origin=origin)

@app.route('/customize/<int:product_id>')
def customize(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product = supabase.table("products").select("*").eq("id", product_id).execute()

    if not product.data:
        flash('Producto no encontrado', 'error')
        return redirect(url_for('dashboard'))

    return f"Acceso a personalizar para el producto ID: {product_id}"

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return "Pasarela de pago - Aquí verás los productos en tu carrito y podrás pagar"

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('orders'))

@app.route('/subscription')
def subscription():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('profile'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return "Sección de Perfil - Aquí verás tu historial de pedidos y suscripciones"

# Ruta para el dashboard de administración
@app.route('/admin')
@admin_required
def admin_dashboard():
    products_data = supabase.table("products").select("*").execute()

    products = []
    if products_data.data:
        for product in products_data.data:
            if 'status' not in product:
                product['status'] = 'active'
            products.append(product)

    # Obtener categorías únicas
    categories = list(set([p['category'] for p in products if 'category' in p]))

    # Calcular disponibilidad (productos activos vs total)
    active_count = sum(1 for p in products if p.get('status') == 'active')
    availability = round((active_count / len(products)) * 100) if products else 0

    return render_template('admin/dashboard.html',
                         products=products,
                         categories=categories,
                         availability=availability)

# Ruta para la gestión de usuarios
@app.route('/admin/users')
@admin_required
def admin_users():
    users_data = supabase.table("users").select("*").execute()

    users = []
    if users_data.data:
        for user in users_data.data:
            if 'is_admin' not in user:
                user['is_admin'] = False
            users.append(user)

    return render_template('admin/users.html', users=users)

@app.route('/admin/products', methods=['GET', 'POST'])
@admin_required
def admin_products():
    if request.method == 'POST':
        product_data = {
            "name": request.form['name'],
            "description": request.form['description'],
            "price": int(request.form['price']),
            "category": request.form['category'],
            "status": request.form['status'],
            "image_url": request.form['image_url']
        }

        product_id = request.form.get('id')

        try:
            if product_id:  # Actualizar producto existente
                supabase.table("products").update(product_data).eq("id", product_id).execute()
                create_notification('product_updated', f'Producto actualizado: {product_data["name"]}')
                flash('Producto actualizado con éxito', 'success')
            else:  # Crear nuevo producto
                supabase.table("products").insert(product_data).execute()
                create_notification('product_created', f'Nuevo producto creado: {product_data["name"]}')
                flash('Producto creado con éxito', 'success')
        except Exception as e:
            flash(f'Error al guardar el producto: {str(e)}', 'error')

        return redirect(url_for('admin_dashboard'))

    return redirect(url_for('admin_dashboard'))

@app.route('/admin/products/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    try:
        # Obtener nombre del producto antes de eliminarlo
        product = supabase.table("products").select("name").eq("id", product_id).single().execute()
        product_name = product.data['name'] if product.data else 'Producto desconocido'

        supabase.table("products").delete().eq("id", product_id).execute()

        create_notification('product_deleted', f'Producto eliminado: {product_name}')

        return jsonify({"success": True, "message": "Producto eliminado"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/products/<int:product_id>')
@admin_required
def get_product(product_id):
    try:
        product = supabase.table("products").select("*").eq("id", product_id).single().execute()
        if product.data and 'status' not in product.data:
            product.data['status'] = 'active'
        return jsonify(product.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# --- Rutas para gestión de usuarios ---
@app.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
@admin_required
def toggle_user_role(user_id):
    try:
        # No permitir que un admin se quite el rol a sí mismo
        if user_id == session.get('user_id'):
            return jsonify({"success": False, "message": "No puedes cambiar tu propio rol"}), 400

        # Obtener el usuario actual
        user = supabase.table("users").select("*").eq("id", user_id).single().execute()
        if not user.data:
            return jsonify({"success": False, "message": "Usuario no encontrado"}), 404

        new_role = not user.data.get('is_admin', False)
        supabase.table("users").update({"is_admin": new_role}).eq("id", user_id).execute()

        # Crear notificación
        role_name = "Administrador" if new_role else "Cliente"
        create_notification('user_role_changed', f'Rol cambiado: {user.data["full_name"]} ahora es {role_name}')

        return jsonify({
            "success": True,
            "message": f"Rol cambiado a {role_name}",
            "is_admin": new_role
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    try:
        # No permitir que un admin se elimine a sí mismo
        if user_id == session.get('user_id'):
            return jsonify({"success": False, "message": "No puedes eliminar tu propia cuenta"}), 400

        # Obtener nombre del usuario antes de eliminarlo
        user = supabase.table("users").select("full_name").eq("id", user_id).single().execute()
        user_name = user.data['full_name'] if user.data else 'Usuario desconocido'

        supabase.table("users").delete().eq("id", user_id).execute()

        # Crear notificación
        create_notification('user_deleted', f'Usuario eliminado: {user_name}')

        return jsonify({"success": True, "message": "Usuario eliminado"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/users/<int:user_id>')
@admin_required
def get_user(user_id):
    try:
        user = supabase.table("users").select("*").eq("id", user_id).single().execute()
        if user.data and 'is_admin' not in user.data:
            user.data['is_admin'] = False
        return jsonify(user.data)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# --- API de Notificaciones ---
@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    try:
        notifications_data = supabase.table("notifications").select("*").order("created_at", desc=True).limit(20).execute()
        unread_data = supabase.table("notifications").select("id").eq("is_read", False).execute()

        notifications = notifications_data.data if notifications_data.data else []
        unread_count = len(unread_data.data) if unread_data.data else 0

        return jsonify({
            "notifications": notifications,
            "unread_count": unread_count
        })
    except Exception as e:
        print(f"Error fetching notifications: {e}")
        return jsonify({"notifications": [], "unread_count": 0})

@app.route('/admin/notifications/mark-read', methods=['POST'])
@admin_required
def mark_notifications_read():
    try:
        supabase.table("notifications").update({"is_read": True}).eq("is_read", False).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- Rutas para el footer ---
@app.route('/sustainability')
def sustainability():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sustainability.html')

@app.route('/contact')
def contact():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('contact.html')

@app.route('/terms')
def terms():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('terminos.html')
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/forgot-password')
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('forgot_password.html')

@app.route('/send-recovery', methods=['POST'])
def send_recovery():
    email = request.form.get('email')

    if not email:
        flash('Por favor ingresa tu correo electrónico', 'error')
        return redirect(url_for('forgot_password'))

    user = supabase.table("users").select("*").eq("email", email).execute()

    if not user.data:
        flash('El correo electrónico no está registrado en nuestro sistema', 'error')
        return redirect(url_for('forgot_password'))

    user_name = user.data[0]['full_name'] if user.data else 'Usuario'

    flash(f'¡Correo enviado con éxito, {user_name}! Hemos enviado un enlace de recuperación a {email}. Revisa tu bandeja de entrada (y la carpeta de spam).', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)