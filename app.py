from collections import Counter
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from supabase import create_client, Client
from user_agents import parse
import os
import random
from functools import wraps
from datetime import datetime, timedelta
from flask_cors import CORS
from dotenv import load_dotenv
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

#Para probar en local inyectando las variables de entorno de supabase
load_dotenv()

# Configuración de Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

MESSES_ES = {
    1: 'Enero', 2: 'Febrero', 3: 'Marzo', 4: 'Abril',
    5: 'Mayo', 6: 'Junio', 7: 'Julio', 8: 'Agosto',
    9: 'Septiembre', 10: 'Octubre', 11: 'Noviembre', 12: 'Diciembre'
}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no está logueado o su rol no es 'admin', va para el login (raíz)
        if 'user_id' not in session or session.get('rol') != 'admin':
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

def cajero_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no está logueado o su rol no es 'cajero', va para el login (raíz)
        if 'user_id' not in session or session.get('rol') != 'cajero':
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

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

@app.route('/', methods=['GET', 'POST'], endpoint='login')
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
            
            # Guardamos el rol que viene de tu nueva columna en Supabase
            session['rol'] = user_data.get('rol', 'cliente')
            
            # Redirección automática según el rol
            if session['rol'] == 'admin':
                return redirect(url_for('admin_dashboard'))
                
            elif session['rol'] == 'cajero':
                return redirect(url_for('cajero_pedidos'))
                
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Correo o contraseña incorrectos', 'error')
            
    return render_template('login.html')
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

@app.route('/admin')
def dashboard():
    # 1. Traer todos los productos
    prod_resp = supabase.table("products").select("*").execute()
    productos = prod_resp.data if prod_resp.data else []

    # 2. Traer todos los pagos para las métricas
    pagos_resp = supabase.table("pagos").select("*").execute()
    pagos = pagos_resp.data if pagos_resp.data else []

    # --- CALCULAR ESTADÍSTICAS EN EL BACKEND ---
    total_items = len(productos)
    
    # Categorías únicas con validación por si 'category' viene vacío
    categorias_unicas = len(set(p['category'] for p in productos if p.get('category'))) if productos else 0
    
    # Disponibilidad (Protegido contra valores None / Null en la base de datos)
    productos_disponibles = 0
    for p in productos:
        stock_val = p.get('stock')
        # Si stock es None o vacío, asumimos que es 0. De lo contrario, usamos su valor numérico.
        stock_actual = 0 if stock_val is None else int(stock_val)
        if stock_actual > 0:
            productos_disponibles += 1
            
    disponibilidad = int((productos_disponibles / total_items) * 100) if total_items > 0 else 0

    # Más vendido
    conteo_ventas = Counter()
    for pago in pagos:
        # Asegurar que producto_id no sea nulo
        if pago.get('producto_id'):
            conteo_ventas[pago['producto_id']] += pago.get('cantidad', 1)
    
    mas_vendido = conteo_ventas.most_common(1)[0][0] if conteo_ventas else "N/A"

    # Enviar todo al HTML
    return render_template('admin/dashboard.html',
                            productos=productos, 
                            total_items=total_items, 
                            mas_vendido=mas_vendido, 
                            categorias=categorias_unicas, 
                            disponibilidad=disponibilidad)

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
    
@app.route('/admin/analiticas')
@admin_required
def admin_analiticas():
    try:
        # 1. CONSULTA REAL A LA TABLA DE PAGOS
        pagos_resp = supabase.table("pagos").select("created_at, total_pago, categoria").execute()
        lista_pagos = pagos_resp.data if pagos_resp.data else []
        
        # Inicializamos los 7 meses de la gráfica en 0: [ENE, FEB, MAR, ABR, MAY, JUN, JUL]
        ventas_por_mes = [0, 0, 0, 0, 0, 0, 0]
        
        # Variables para contar categorías vendidas en el gráfico de dona
        total_items_vendidos = len(lista_pagos)
        ventas_cafe = 0
        ventas_reposteria = 0
        
        for pago in lista_pagos:
            fecha_str = pago.get('created_at') # Formato: "2026-04-15T18:30:00+00:00"
            monto = pago.get('total_pago', 0)
            cat_pago = pago.get('categoria', '').lower()
            
            # --- Procesar Fecha para el Gráfico de Líneas ---
            if fecha_str:
                # Quitamos la zona horaria si viene con '+' para evitar errores en fromisoformat
                fecha_limpia = fecha_str.split('+')[0]
                fecha_dt = datetime.fromisoformat(fecha_limpia)
                mes = fecha_dt.month  # Devuelve un entero del 1 al 12
                
                # Clasificamos de Enero (1) a Julio (7) en sus respectivas posiciones (0 a 6)
                if 1 <= mes <= 7:
                    ventas_por_mes[mes - 1] += float(monto)
            
            # --- Procesar Categoría para el Gráfico de Dona ---
            if 'café' in cat_pago or 'cafe' in cat_pago:
                ventas_cafe += 1
            elif 'repostería' in cat_pago or 'reposteria' in cat_pago:
                ventas_reposteria += 1

        # Calcular los porcentajes reales de venta
        porcentaje_cafe = round((ventas_cafe / total_items_vendidos) * 100) if total_items_vendidos > 0 else 0
        porcentaje_reposteria = round((ventas_reposteria / total_items_vendidos) * 100) if total_items_vendidos > 0 else 0

        # 2. SEGUIMIENTO DE LEALTAD (De la tabla de usuarios como ya funcionaba)
        users_resp = supabase.table("users").select("loyalty_points").execute()
        usuarios = users_resp.data if users_resp.data else []
        puntos_ganados = sum(u.get('loyalty_points', 0) for u in usuarios if u.get('loyalty_points', 0) > 0)
        
        # 3. EXTRAER TOTAL DE CATEGORÍAS DISPONIBLES (De la tabla de productos)
        prod_resp = supabase.table("products").select("category").execute()
        productos = prod_resp.data if prod_resp.data else []
        categorias_unicas = list(set(p.get('category') for p in productos if p.get('category')))

        # ESTRUCTURA DE MÉTRICAS PARA JINJA2
        metrics = {
            'puntos_ganados': puntos_ganados,
            'puntos_redimidos': 0, # Lo dejamos estático o según tu lógica de negocio
            'total_categorias': len(categorias_unicas),
            'porcentaje_cafe': porcentaje_cafe,
            'porcentaje_reposteria': porcentaje_reposteria,
            'ventas_meses': ventas_por_mes  # <-- Lista con los totales reales de ENE a JUL
        }

        return render_template('admin/analiticas.html', metrics=metrics)
        
    except Exception as e:
        print("Error crítico en analiticas:", str(e))
        return f"Error al procesar los datos de pagos: {str(e)}", 500

@app.route('/admin/notifications/mark-read', methods=['POST'])
@admin_required
def mark_notifications_read():
    try:
        supabase.table("notifications").update({"is_read": True}).eq("is_read", False).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/admin/actualizar-stock', methods=['POST'])
def actualizar_stock():
    try:
        data = request.get_json()
        producto_id = data.get('id')
        nuevo_stock = data.get('stock')

        # Conexión directa para actualizar la columna stock en Supabase
        supabase.table("products").update({"stock": nuevo_stock}).eq("id", producto_id).execute()

        return jsonify({"status": "success", "message": "Stock modificado"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    
from flask import redirect, url_for, request

@app.route('/admin/nuevo-producto', methods=['POST'])
def nuevo_producto():
    try:
        # Obtener los datos enviados desde el Modal
        name = request.form.get('name')
        price = float(request.form.get('price', 0))
        category = request.form.get('category')
        stock = int(request.form.get('stock', 0))
        image_url = request.form.get('image_url')
        description = request.form.get('description', '')

        # Preparar el objeto para Supabase
        nuevo_item = {
            "name": name,
            "price": price,
            "category": category,
            "stock": stock,
            "image_url": image_url,
            "description": description
        }

        # Insertar fila directamente en la tabla 'products' de Supabase
        supabase.table("products").insert(nuevo_item).execute()

        # Recargar la vista del dashboard para ver el nuevo producto listado al instante
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        return f"<h3>Error al insertar producto en Supabase:</h3><pre>{str(e)}</pre>", 500
    
@app.route('/admin/eliminar-producto/<producto_id>', methods=['POST'])
def eliminar_producto(producto_id):
    try:
        supabase.table("products").delete().eq("id", producto_id).execute()
        return jsonify({"status": "success", "message": "Producto eliminado"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/admin/actualizar-producto', methods=['POST'])
def actualizar_producto():
    try:
        producto_id = request.form.get('id')
        
        datos_actualizados = {
            "name": request.form.get('name'),
            "price": float(request.form.get('price', 0)),
            "category": request.form.get('category'),
            "stock": int(request.form.get('stock', 0)),
            "image_url": request.form.get('image_url'),
            "description": request.form.get('description', '')
        }

        # Actualizar en Supabase buscando por su ID
        supabase.table("products").update(datos_actualizados).eq("id", producto_id).execute()
        
        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"<h3>Error al actualizar en Supabase:</h3><pre>{str(e)}</pre>", 500
    
@app.route('/admin/users')
@admin_required
def admin_users():
    try:
        # 1. Traemos los datos limpios de Supabase
        response = supabase.table("users").select("*").execute()
        lista_usuarios = response.data if response.data else []
        
        # 2. Imprimimos en la consola para tu control
        print("--- CONTROL DE USUARIOS EN CONSOLA ---")
        print(lista_usuarios)
        print("---------------------------------------")
        
        # 3. Enviamos la variable estricta 'users' al HTML
        return render_template('admin/users.html', users=lista_usuarios)
    except Exception as e:
        print("Error en ruta admin_users:", str(e))
        return f"Error al cargar usuarios: {str(e)}", 500
def cajero_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Verificamos si hay un usuario logueado y si su rol es 'cajero'
        if 'usuario' not in session or session.get('rol') != 'cajero':
            print("Acceso denegado: No es cajero o no ha iniciado sesión.")
            return redirect(url_for('login_cajero'))
        return f(*args, **kwargs)
    return decorated_function

# --- RUTA DE INICIO DE SESIÓN ---
@app.route('/cajero/login', methods=['GET', 'POST'])
def login_cajero():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        try:
            # 1. Buscamos el usuario en tu tabla 'users' de Supabase
            auth_resp = supabase.table("users").select("*").eq("email", email).execute()
            usuarios = auth_resp.data
            
            if usuarios:
                usuario_actual = usuarios[0]
                # NOTA: Aquí puedes validar con tu sistema de contraseñas (ej: bcrypt o texto plano temporal)
                # Para este ejemplo asumimos que el rol guardado en tu base de datos es 'cajero'
                if usuario_actual.get('role') == 'cajero' or usuario_actual.get('rol') == 'cajero':
                    session['usuario'] = usuario_actual.get('email')
                    session['rol'] = 'cajero'
                    return redirect(url_for('cajero_pedidos'))
                else:
                    return render_template('cajero/login.html', error="Tu usuario no tiene rol de Cajero.")
            else:
                return render_template('cajero/login.html', error="Credenciales incorrectas o usuario inexistente.")
                
        except Exception as e:
            return render_template('cajero/login.html', error=f"Error de conexión: {str(e)}")
            
    return render_template('cajero/login.html', error=None)

def cajero_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si no hay un id de usuario en sesión o el rol no es 'cajero', lo mandamos al login ('/')
        if 'user_id' not in session or session.get('rol') != 'cajero':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
# --- VISTA DE PEDIDOS PROTEGIDA ---
@app.route('/cajero/pedidos')
@cajero_required  # <-- Protege la vista usando la sesión del login
def cajero_pedidos():
    try:
        resp = supabase.table("pagos").select("*").order("created_at", desc=True).execute()
        pedidos = resp.data if resp.data else []
        
        ingresos_hoy = sum(float(p.get('total_pago', 0)) for p in pedidos if p.get('estado') != 'Cancelado')
        ordenes_activas = sum(1 for p in pedidos if p.get('estado') in ['Confirmada', 'En Preparación'])
        
        metrics = {
            'ingresos_hoy': ingresos_hoy,
            'ordenes_activas': ordenes_activas,
            'pico_demanda': '10:30 AM'
        }
        return render_template('cajero/pedidos.html', pedidos=pedidos, metrics=metrics)
    except Exception as e:
        return f"Error al cargar pedidos: {str(e)}", 500
    
@app.route('/logout')
def logout():
    session.clear() # Borra de forma segura todos los datos de la sesión actual
    flash('Has cerrado sesión correctamente.', 'success')
    return redirect('/') # Te manda directo a la pantalla de login
# --- API EN LIVE: CAMBIAR ESTADO EN LA BASE DE DATOS ---
@app.route('/api/pedidos/update_status', methods=['POST'])
def update_pedido_status():
    try:
        data = request.get_json()
        pedido_id = data.get('id')
        nuevo_estado = data.get('estado')
        
        if not pedido_id or not nuevo_estado:
            return jsonify({'success': False, 'error': 'Datos faltantes'}), 400
            
        # Actualizamos de forma real y persistente la columna 'estado' en Supabase
        supabase.table("pagos").update({'estado': nuevo_estado}).eq('id', pedido_id).execute()
        
        return jsonify({'success': True, 'nuevo_estado': nuevo_estado})
    except Exception as e:
        print("Error al guardar estado:", str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

# Ruta rápida para cerrar sesión
@app.route('/cajero/logout')
def logout_cajero():
    session.clear()
    return redirect(url_for('login_cajero'))


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)

