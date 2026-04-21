from flask import Flask, render_template, request, redirect, url_for, session, flash
from supabase import create_client, Client
from user_agents import parse
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Configuración de Supabase
url: str = "https://lmvulmiiuoknceifvrcy.supabase.co"
key: str = "sb_secret_-jqmUZ8z63E4ymW9UxHa3w_dkd0Xd9i"
supabase: Client = create_client(url, key)

def init_db():
    user = supabase.table("users").select("*").eq("email", "admin@correo.com").execute()
    if not user.data:
        supabase.table("users").insert({
            "full_name": "admin",
            "email": "admin@correo.com",
            "password": "admin"
        }).execute()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = supabase.table("users").select("*").eq("email", email).eq("password", password).execute()
        if user.data:
            session['user_id'] = user.data[0]['id']
            session['email'] = user.data[0]['email']
            session['full_name'] = user.data[0]['full_name']
            flash('¡Inicio de sesión exitoso!', 'success')
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

# --- Nuevas rutas para el footer ---
@app.route('/sustainability')
def sustainability():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return "Sección de Sostenibilidad - Aquí verás información sobre nuestras prácticas sostenibles."

@app.route('/contact')
def contact():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return "Sección de Contacto - Aquí podrás contactarnos para cualquier consulta."

@app.route('/terms')
def terms():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return "Sección de Términos y Condiciones - Aquí encontrarás los términos legales de nuestro servicio."
# --- Fin de nuevas rutas ---

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)