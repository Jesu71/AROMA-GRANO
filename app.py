
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from user_agents import parse
import os
import random
from functools import wraps
from datetime import datetime, timedelta
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Configuración de Supabase
url: str = "https://lmvulmiiuoknceifvrcy.supabase.co"
key: str = "sb_secret_-jqmUZ8z63E4ymW9UxHa3w_dkd0Xd9i"
supabase: Client = create_client(url, key)

MESSES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}


def format_order_date(date_str):
    if not date_str:
        return ''
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        dt_co = dt - timedelta(hours=5)
        return f"{dt_co.day} de {MESSES_ES[dt_co.month]}"
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
        print(f"Error creating notification: {e}")


def get_cart_count(user_id):
    try:
        cart_data = supabase.table("cart_items").select("id").eq("user_id", user_id).execute()
        return len(cart_data.data) if cart_data.data else 0
    except:
        return 0


def clean_orphan_cart_items(user_id):
    try:
        cart_data = supabase.table("cart_items").select("product_id, id").eq("user_id", user_id).execute()
        if not cart_data.data:
            return []
        products_data = supabase.table("products").select("id").execute()
        existing_ids = set(p['id'] for p in products_data.data) if products_data.data else set()
        orphan_ids = []
        orphan_product_ids = []
        for item in cart_data.data:
            if item['product_id'] not in existing_ids:
                orphan_ids.append(item['id'])
                orphan_product_ids.append(item['product_id'])
        if orphan_ids:
            for orphan_id in orphan_ids:
                supabase.table("cart_items").delete().eq("id", orphan_id).execute()
        return orphan_product_ids
    except Exception as e:
        print(f"Error cleaning orphan cart items: {e}")
        return []


def get_active_products():
    try:
        products_data = supabase.table("products").select("*").execute()
        if not products_data.data:
            return []
        active = [p for p in products_data.data if p.get('status', 'active') == 'active']
        return active if active else products_data.data
    except Exception as e:
        print(f"Error getting active products: {e}")
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


# ===================== AUTENTICACIÓN =====================

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
        flash('¡Producto añadido al carrito con éxito!', 'success')
        return redirect(url_for('orders'))
    except Exception as e:
        flash(f'Error al añadir al carrito: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


# ===================== CARRITO =====================

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

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


# ===================== CHECKOUT Y PAGO =====================

@app.route('/checkout')
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

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

    cart_data = supabase.table("cart_items").select("*").eq("user_id", user_id).execute()
    cart_items = cart_data.data if cart_data.data else []

    if not cart_items:
        flash('Tu carrito está vacío.', 'error')
        return redirect(url_for('orders'))

    products_data = supabase.table("products").select("id").execute()
    existing_ids = set(p['id'] for p in products_data.data) if products_data.data else set()

    for item in cart_items:
        if item['product_id'] not in existing_ids:
            clean_orphan_cart_items(user_id)
            flash('Algunos productos ya no están disponibles. Se eliminaron de tu carrito.', 'error')
            return redirect(url_for('orders'))

    try:
        has_reward_item = any(item.get('origin') == 'Con descuento lealtad' for item in cart_items)

        items_json = []
        for item in cart_items:
            is_reward = item.get('origin') == 'Con descuento lealtad'
            items_json.append({
                "product_id": item.get("product_id"),
                "product_name": item.get("product_name"),
                "product_image_url": item.get("product_image_url", ""),
                "origin": item.get("origin", "Etiopía"),
                "milk_type": item.get("milk_type", "Entera"),
                "temperature": item.get("temperature", "Caliente"),
                "sweetness": item.get("sweetness", 50),
                "quantity": item.get("quantity", 1),
                "unit_price": item.get("unit_price", 0),
                "milk_surcharge": item.get("milk_surcharge", 0),
                "total_price": item.get("total_price", 0),
                "is_reward": is_reward
            })

        total = sum(item['total_price'] for item in cart_items)
        points_earned = 0 if has_reward_item else 7

        supabase.table("orders_history").insert({
            "user_id": user_id,
            "items": items_json,
            "total": total,
            "points_earned": points_earned
        }).execute()

        if points_earned > 0:
            current_user = supabase.table("users").select("loyalty_points").eq("id", user_id).single().execute()
            current_points = current_user.data.get('loyalty_points', 0) if current_user.data else 0
            supabase.table("users").update({"loyalty_points": current_points + points_earned}).eq("id", user_id).execute()

        supabase.table("cart_items").delete().eq("user_id", user_id).execute()

        if has_reward_item:
            flash('¡Pedido realizado con éxito! Descuento de lealtad aplicado.', 'success')
        else:
            flash(f'¡Pedido realizado con éxito! Ganaste {points_earned} puntos de lealtad.', 'success')
    except Exception as e:
        print(f"Error en process_payment: {e}")
        flash('Error al procesar el pedido.', 'error')

    return redirect(url_for('dashboard'))


# ===================== PERFIL Y LEALTAD =====================

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    user_data = supabase.table("users").select("*").eq("id", user_id).single().execute()
    user = user_data.data if user_data.data else {}
    loyalty_points = user.get('loyalty_points', 0)

    try:
        orders_data = supabase.table("orders_history").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(10).execute()
        raw_orders = orders_data.data if orders_data.data else []
    except:
        raw_orders = []

    orders = []
    for order in raw_orders:
        order_items = order.get('items', [])
        if isinstance(order_items, list):
            first_item = order_items[0] if order_items else {}
            first_image = first_item.get('product_image_url', '') if first_item else ''
            item_count = len(order_items)

            is_reward = any(it.get('is_reward', False) for it in order_items)
            is_free = order.get('total', 0) == 0

            if is_reward or is_free:
                can_reorder = False
            else:
                can_reorder = False
                for it in order_items:
                    pid = it.get('product_id')
                    if pid and not it.get('is_reward', False):
                        check = supabase.table("products").select("id").eq("id", pid).execute()
                        if check.data:
                            can_reorder = True
                            break
        else:
            first_item = {}
            first_image = ''
            item_count = 0
            is_reward = False
            is_free = False
            can_reorder = False

        orders.append({
            'id': order.get('id'),
            'formatted_date': format_order_date(order.get('created_at')),
            'total': order.get('total', 0),
            'points_earned': order.get('points_earned', 0),
            'first_item': first_item,
            'first_image': first_image,
            'item_count': item_count,
            'can_reorder': can_reorder,
            'is_reward': is_reward,
            'is_free': is_free
        })

    cart_count = get_cart_count(user_id)

    user_agent = request.headers.get('User-Agent')
    agent = parse(user_agent)

    if agent.is_mobile:
        return render_template('profile_mobile.html', user=user, loyalty_points=loyalty_points, orders=orders, cart_count=cart_count)
    else:
        return render_template('profile_pc.html', user=user, loyalty_points=loyalty_points, orders=orders, cart_count=cart_count)


@app.route('/redeem-reward', methods=['POST'])
def redeem_reward():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    reward_type = request.form.get('reward_type', 'coffee')
    points_required = 500 if reward_type == 'coffee' else 800

    user_data = supabase.table("users").select("loyalty_points").eq("id", session['user_id']).single().execute()
    if not user_data.data:
        flash('Error al obtener tu perfil.', 'error')
        return redirect(url_for('profile'))

    current_points = user_data.data.get('loyalty_points', 0)
    if current_points < points_required:
        flash(f'Necesitas {points_required} puntos. Tienes {current_points}.', 'error')
        return redirect(url_for('profile'))

    new_points = current_points - points_required
    supabase.table("users").update({"loyalty_points": new_points}).eq("id", session['user_id']).execute()

    if reward_type == 'coffee':
        cheapest = get_cheapest_product()
        if not cheapest:
            supabase.table("users").update({"loyalty_points": current_points}).eq("id", session['user_id']).execute()
            flash('No hay productos disponibles para canjear en este momento.', 'error')
            return redirect(url_for('profile'))

        items_json = [{
            "product_id": cheapest.get('id'),
            "product_name": cheapest.get('name', 'Café de la Casa'),
            "product_image_url": cheapest.get('image_url', ''),
            "origin": "Cortesía de la casa",
            "milk_type": "Entera",
            "temperature": "Caliente",
            "sweetness": 50,
            "quantity": 1,
            "unit_price": 0,
            "milk_surcharge": 0,
            "total_price": 0,
            "is_reward": True
        }]
        try:
            supabase.table("orders_history").insert({
                "user_id": session['user_id'],
                "items": items_json,
                "total": 0,
                "points_earned": 0
            }).execute()
        except Exception as e:
            print(f"Error creating free coffee order: {e}")

        flash(f'☕ ¡Canjeaste un Café Gratis ({cheapest.get("name", "Café")})! Puedes pasar a recogerlo a nuestra tienda en Chapinero Alto. Se descontaron {points_required} puntos.', 'success')

    else:
        random_product = get_random_product()
        if not random_product:
            supabase.table("users").update({"loyalty_points": current_points}).eq("id", session['user_id']).execute()
            flash('No hay productos disponibles para canjear en este momento.', 'error')
            return redirect(url_for('profile'))

        original_price = random_product.get('price', 0)
        discounted_price = int(original_price * 0.8)

        try:
            supabase.table("cart_items").insert({
                "user_id": session['user_id'],
                "product_id": random_product.get('id'),
                "product_name": random_product.get('name', 'Café') + ' (20% desc.)',
                "product_image_url": random_product.get('image_url', ''),
                "origin": "Con descuento lealtad",
                "milk_type": "Entera",
                "temperature": "Caliente",
                "sweetness": 50,
                "quantity": 1,
                "unit_price": discounted_price,
                "milk_surcharge": 0,
                "total_price": discounted_price
            }).execute()
        except Exception as e:
            print(f"Error adding discounted item to cart: {e}")

        flash(f'🏷️ ¡Canjeaste 20% de descuento en {random_product.get("name", "Café")}! Original: ${original_price:,} → Con descuento: ${discounted_price:,} COP. Revisa tu carrito para confirmar. Se descontaron {points_required} puntos.', 'success')

    return redirect(url_for('profile'))


@app.route('/reorder/<int:order_id>', methods=['POST'])
def reorder(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    order = supabase.table("orders_history").select("*").eq("id", order_id).eq("user_id", session['user_id']).single().execute()
    if not order.data:
        flash('Pedido no encontrado.', 'error')
        return redirect(url_for('profile'))

    items = order.data.get('items', [])

    is_reward_order = any(it.get('is_reward', False) for it in items)
    is_free_order = order.data.get('total', 0) == 0
    if is_reward_order or is_free_order:
        flash('Los pedidos de recompensa no se pueden repetir. Si deseas otro, canjea más puntos.', 'error')
        return redirect(url_for('profile'))

    added = 0
    skipped = False
    for item in items:
        product_id = item.get('product_id')
        if not product_id:
            skipped = True
            continue
        if item.get('is_reward', False):
            skipped = True
            continue
        check = supabase.table("products").select("id").eq("id", product_id).execute()
        if not check.data:
            skipped = True
            continue
        try:
            supabase.table("cart_items").insert({
                "user_id": session['user_id'],
                "product_id": product_id,
                "product_name": item.get('product_name', ''),
                "product_image_url": item.get('product_image_url', ''),
                "origin": item.get('origin', 'Etiopía'),
                "milk_type": item.get('milk_type', 'Entera'),
                "temperature": item.get('temperature', 'Caliente'),
                "sweetness": item.get('sweetness', 50),
                "quantity": item.get('quantity', 1),
                "unit_price": item.get('unit_price', 0),
                "milk_surcharge": item.get('milk_surcharge', 0),
                "total_price": item.get('total_price', 0)
            }).execute()
            added += 1
        except:
            pass

    if skipped:
        flash('Algunos productos de ese pedido ya no están disponibles y se omitieron.', 'warning')

    if added > 0:
        flash(f'¡Se añadieron {added} producto(s) a tu carrito!', 'success')
    elif skipped and added == 0:
        flash('Los productos de ese pedido ya no están disponibles.', 'error')
    else:
        flash('No se pudo repetir el pedido.', 'error')
    return redirect(url_for('orders'))


@app.route('/send-support', methods=['POST'])
def send_support():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    message = request.form.get('message', '').strip()
    if message:
        user_name = session.get('full_name', 'Usuario')
        user_email = session.get('email', '')
        create_notification('support_message', f'Soporte de {user_name} ({user_email}): {message}')
        flash('¡Mensaje enviado! Te responderemos pronto.', 'success')
    else:
        flash('Escribe tu mensaje.', 'error')
    return redirect(url_for('profile'))


@app.route('/subscription')
def subscription():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('profile'))


# ===================== FOOTER =====================

@app.route('/sustainability')
def sustainability():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('sustainability.html')


@app.route('/contact')
def contact():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    cart_count = get_cart_count(session['user_id'])
    return render_template('contact.html', cart_count=cart_count)


@app.route('/send-contact', methods=['POST'])
def send_contact():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    name = request.form.get('name', '').strip()
    email = request.form.get('email', '').strip()
    message = request.form.get('message', '').strip()

    if not name or not email or not message:
        flash('Por favor completa todos los campos.', 'error')
        return redirect(url_for('contact'))

    if '@' not in email:
        flash('El correo electrónico debe contener @.', 'error')
        return redirect(url_for('contact'))

    create_notification('contact_message', f'Contacto de {name} ({email}): {message}')
    flash('¡Mensaje enviado con éxito! Te responderemos pronto.', 'success')
    return redirect(url_for('contact'))


@app.route('/terms')
def terms():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('terminos.html')


# ===================== ADMIN =====================

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
        supabase.table("products").delete().eq("id", product_id).execute()
        supabase.table("cart_items").delete().eq("product_id", product_id).execute()
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
        supabase.table("cart_items").delete().eq("user_id", user_id).execute()
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

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=False)