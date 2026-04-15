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
    # Verificar si el usuario admin existe, si no, crearlo
    user = supabase.table("users").select("*").eq("email", "admin").execute()
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

        # Verificar si el correo ya está registrado
        existing_user = supabase.table("users").select("*").eq("email", email).execute()
        if existing_user.data:
            flash('El correo ya está registrado', 'error')
            return redirect(url_for('register'))

        # Insertar el nuevo usuario
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

    if agent.is_mobile:
        return render_template('dashboard_mobile.html')
    else:
        return render_template('dashboard_pc.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))
if __name__ == '__main__':
    init_db()
    app.run(debug=True)   