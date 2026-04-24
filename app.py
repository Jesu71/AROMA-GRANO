from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from user_agents import parse
import os
from functools import wraps
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

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

# Helper para obtener el conteo del carrito
def get_cart_count(user_id):
    try:
        cart_data = supabase.table("cart_items").select("id").eq("user_id", user_id).execute()
        return len(cart_data.data) if cart_data.data else 0
    except:
        return 0

# Helper para limpiar items huérfanos del carrito (productos que ya no existen)
def clean_orphan_cart_items(user_id):
    """Elimina del carrito los items cuyo product_id ya no existe en la tabla products"""
    try:
        # Obtener todos los items del carrito del usuario
        cart_data = supabase.table("cart_items").select("product_id, id").eq("user_id", user_id).execute()
        if not cart_data.data:
            return []

        # Obtener todos los IDs de productos existentes
        products_data = supabase.table("products").select("id").execute()
        existing_ids = set(p['id'] for p in products_data.data) if products_data.data else set()

        # Identificar items huérfanos
        orphan_ids = []
        orphan_product_ids = []
        for item in cart_data.data:
            if item['product_id'] not in existing_ids:
                orphan_ids.append(item['id'])
                orphan_product_ids.append(item['product_id'])

        # Eliminar items huérfanos
        if orphan_ids:
            for orphan_id in orphan_ids:
                supabase.table("cart_items").delete().eq("id", orphan_id).execute()

        return orphan_product_ids
    except Exception as e:
        print(f"Error cleaning orphan cart items: {e}")
        return []

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

    cart_count = get_cart_count(session['user_id'])

    if agent.is_mobile:
        return render_template('dashboard_mobile.html', products=products, category=category, origin=origin, cart_count=cart_count)
    else:
        return render_template('dashboard_pc.html', products=products, category=category, origin=origin, cart_count=cart_count)

@app.route('/customize/<int:product_id>')
def customize(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product_data = supabase.table("products").select("*").eq("id", product_id).execute()

    if not product_data.data:
        flash('Producto no encontrado', 'error')
        return redirect(url_for('dashboard'))

    product = product_data.data[0]
    cart_count = get_cart_count(session['user_id'])

    user_agent = request.headers.get('User-Agent')
    agent = parse(user_agent)

    if agent.is_mobile:
        return render_template('customize_mobile.html', product=product, cart_count=cart_count)
    else:
        return render_template('customize_pc.html', product=product, cart_count=cart_count)

@app.route('/add-to-cart', methods=['POST'])
def add_to_cart():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "No autenticado"}), 401

    try:
        user_id = session['user_id']
        product_id = request.form.get('product_id')

        # Verificar que el producto sigue existiendo antes de añadirlo
        product_check = supabase.table("products").select("id, name").eq("id", product_id).execute()
        if not product_check.data:
            flash('Este producto ya no está disponible', 'error')
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

        cart_item = {
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
        }

        supabase.table("cart_items").insert(cart_item).execute()
        flash('¡Producto añadido al carrito con éxito!', 'success')
        return redirect(url_for('orders'))
    except Exception as e:
        flash(f'Error al añadir al carrito: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Limpiar items huérfanos antes de mostrar el carrito
    removed = clean_orphan_cart_items(user_id)
    if removed:
        flash(f'Se eliminaron {len(removed)} producto(s) de tu carrito porque ya no están disponibles', 'warning')

    cart_data = supabase.table("cart_items").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    cart_items = cart_data.data if cart_data.data else []
    total = sum(item['total_price'] for item in cart_items)
    cart_count = len(cart_items)

    user_agent = request.headers.get('User-Agent')
    agent = parse(user_agent)

    if agent.is_mobile:
        return render_template('orders_mobile.html', cart_items=cart_items, total=total, cart_count=cart_count)
    else:
        return render_template('orders_pc.html', cart_items=cart_items, total=total, cart_count=cart_count)

@app.route('/remove-from-cart/<int:item_id>', methods=['POST', 'GET'])
def remove_from_cart(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    try:
        supabase.table("cart_items").delete().eq("id", item_id).eq("user_id", session['user_id']).execute()
        flash('Producto eliminado del carrito', 'success')
    except Exception as e:
        flash('Error al eliminar el producto', 'error')
    return redirect(url_for('orders'))

@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Limpiar items huérfanos antes de mostrar la pasarela
    removed = clean_orphan_cart_items(user_id)
    if removed:
        flash(f'Se eliminaron {len(removed)} producto(s) de tu carrito porque ya no están disponibles', 'warning')

    cart_data = supabase.table("cart_items").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
    cart_items = cart_data.data if cart_data.data else []
    total = sum(item['total_price'] for item in cart_items)
    cart_count = len(cart_items)

    user_agent = request.headers.get('User-Agent')
    agent = parse(user_agent)

    if agent.is_mobile:
        return render_template('checkout_mobile.html', cart_items=cart_items, total=total, cart_count=cart_count)
    else:
        return render_template('checkout_pc.html', cart_items=cart_items, total=total, cart_count=cart_count)

@app.route('/process-payment', methods=['POST'])
def process_payment():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Verificar que todos los productos siguen existiendo antes de confirmar
    cart_data = supabase.table("cart_items").select("product_id").eq("user_id", user_id).execute()
    if cart_data.data:
        products_data = supabase.table("products").select("id").execute()
        existing_ids = set(p['id'] for p in products_data.data) if products_data.data else set()

        for item in cart_data.data:
            if item['product_id'] not in existing_ids:
                # Hay productos que ya no existen, limpiar y avisar
                clean_orphan_cart_items(user_id)
                flash('Tu pedido no pudo procesarse porque algunos productos ya no están disponibles. Se eliminaron de tu carrito.', 'error')
                return redirect(url_for('orders'))

    try:
        supabase.table("cart_items").delete().eq("user_id", user_id).execute()
        flash('¡Pedido realizado con éxito! Tu café está en preparación.', 'success')
    except Exception as e:
        flash('Error al procesar el pedido', 'error')
    return redirect(url_for('dashboard'))

@app.route('/cart-count')
def cart_count_api():
    if 'user_id' not in session:
        return jsonify({"count": 0})
    count = get_cart_count(session['user_id'])
    return jsonify({"count": count})

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

# ===================== RUTAS DE ADMINISTRACIÓN =====================

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
    categories = list(set([p['category'] for p in products if 'category' in p]))
    active_count = sum(1 for p in products if p.get('status') == 'active')
    availability = round((active_count / len(products)) * 100) if products else 0
    return render_template('admin/dashboard.html', products=products, categories=categories, availability=availability)

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
            if product_id:
                supabase.table("products").update(product_data).eq("id", product_id).execute()
                create_notification('product_updated', f'Producto actualizado: {product_data["name"]}')
                flash('Producto actualizado con éxito', 'success')
            else:
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
        product = supabase.table("products").select("name").eq("id", product_id).single().execute()
        product_name = product.data['name'] if product.data else 'Producto desconocido'

        # Eliminar el producto
        supabase.table("products").delete().eq("id", product_id).execute()

        # Eliminar TODOS los items de carrito que referencian este producto
        orphan_cleanup = supabase.table("cart_items").delete().eq("product_id", product_id).execute()

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

@app.route('/admin/users/<int:user_id>/toggle-role', methods=['POST'])
@admin_required
def toggle_user_role(user_id):
    try:
        if user_id == session.get('user_id'):
            return jsonify({"success": False, "message": "No puedes cambiar tu propio rol"}), 400
        user = supabase.table("users").select("*").eq("id", user_id).single().execute()
        if not user.data:
            return jsonify({"success": False, "message": "Usuario no encontrado"}), 404
        new_role = not user.data.get('is_admin', False)
        supabase.table("users").update({"is_admin": new_role}).eq("id", user_id).execute()
        role_name = "Administrador" if new_role else "Cliente"
        create_notification('user_role_changed', f'Rol cambiado: {user.data["full_name"]} ahora es {role_name}')
        return jsonify({"success": True, "message": f"Rol cambiado a {role_name}", "is_admin": new_role})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/admin/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    try:
        if user_id == session.get('user_id'):
            return jsonify({"success": False, "message": "No puedes eliminar tu propia cuenta"}), 400
        user = supabase.table("users").select("full_name").eq("id", user_id).single().execute()
        user_name = user.data['full_name'] if user.data else 'Usuario desconocido'

        # Eliminar carrito del usuario antes de eliminarlo
        supabase.table("cart_items").delete().eq("user_id", user_id).execute()

        # Eliminar usuario
        supabase.table("users").delete().eq("id", user_id).execute()

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

@app.route('/admin/notifications')
@admin_required
def admin_notifications():
    try:
        notifications_data = supabase.table("notifications").select("*").order("created_at", desc=True).limit(20).execute()
        unread_data = supabase.table("notifications").select("id").eq("is_read", False).execute()
        notifications = notifications_data.data if notifications_data.data else []
        unread_count = len(unread_data.data) if unread_data.data else 0
        return jsonify({"notifications": notifications, "unread_count": unread_count})
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

# ===================== RUTAS DEL FOOTER =====================

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
    flash(f'¡Correo enviado con éxito, {user_name}! Hemos enviado un enlace de recuperación a {email}.', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)