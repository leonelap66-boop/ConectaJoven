# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, datetime

APP_NAME = "Conecta Joven"
DB_PATH = os.path.join(os.path.dirname(__file__), "conecta_joven.db")
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
MEET_LINK = "https://meet.google.com/gny-hczd-zep"

# --------------------------
# DB
# --------------------------
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Crea la base si no existe y asegura tablas si ya existía."""
    if os.path.exists(DB_PATH):
        conn = get_db(); cur = conn.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS appointments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dni TEXT NOT NULL,
            name TEXT NOT NULL,
            advisor TEXT NOT NULL,
            date TEXT NOT NULL,   -- YYYY-MM-DD
            time TEXT NOT NULL,   -- HH:MM
            created_at TEXT NOT NULL
        )""")
        cur.execute("""CREATE TABLE IF NOT EXISTS job_applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(user_id, job_id)
        )""")
        conn.commit(); conn.close()
        return

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('Estudiante interesado','Mentor')),
        created_at TEXT NOT NULL
    )""")

    cur.execute("""CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        company TEXT NOT NULL,
        link TEXT NOT NULL,
        description TEXT,
        created_by INTEGER,
        created_at TEXT NOT NULL,
        FOREIGN KEY(created_by) REFERENCES users(id)
    )""")

    cur.execute("""CREATE TABLE mentor_prereg (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'PENDIENTE',
        created_at TEXT NOT NULL
    )""")

    cur.execute("""CREATE TABLE appointments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        dni TEXT NOT NULL,
        name TEXT NOT NULL,
        advisor TEXT NOT NULL,
        date TEXT NOT NULL,
        time TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")

    cur.execute("""CREATE TABLE job_applications(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        job_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(user_id, job_id)
    )""")

    # Usuarios iniciales
    cur.execute(
        "INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
        ("Usuario Demo", "demo@conectajoven.pe", generate_password_hash("demo123"), "Estudiante interesado",
         datetime.datetime.utcnow().isoformat())
    )
    cur.execute(
        "INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
        ("Administrador", "admin@conectajoven.pe", generate_password_hash("admin123"), "Mentor",
         datetime.datetime.utcnow().isoformat())
    )

    # Convocatorias demo
    demo_jobs = [
        ("Asistente de Ventas", "Comercial ABC", "https://pe.computrabajo.com/", "Atención al cliente y metas semanales."),
        ("Soporte TI Jr.", "Tech Perú", "https://www.bumeran.com.pe/", "Brindar soporte a usuarios y documentar incidencias."),
        ("Auxiliar Administrativo", "Servicios Lima", "https://www.empleosperu.gob.pe/portal-mtpe/#/", "Gestión documental y data entry.")
    ]
    for t, c, l, d in demo_jobs:
        cur.execute(
            "INSERT INTO jobs (title,company,link,description,created_by,created_at) VALUES (?,?,?,?,?,?)",
            (t, c, l, d, 1, datetime.datetime.utcnow().isoformat())
        )

    conn.commit(); conn.close()

# --------------------------
# APP
# --------------------------
app = Flask(__name__)
app.secret_key = SECRET_KEY

# Filtro timeago
import datetime as _dt
@app.template_filter("timeago")
def timeago(value):
    if not value:
        return ""
    try:
        dt = _dt.datetime.fromisoformat(value)
    except Exception:
        return value
    now = _dt.datetime.utcnow()
    diff = now - dt
    s = int(diff.total_seconds())
    if s < 60:
        return f"hace {s} segundo{'s' if s != 1 else ''}"
    m = s // 60
    if m < 60:
        return f"hace {m} minuto{'s' if m != 1 else ''}"
    h = m // 60
    if h < 24:
        return f"hace {h} hora{'s' if h != 1 else ''}"
    d = h // 24
    if d < 7:
        return f"hace {d} día{'s' if d != 1 else ''}"
    return dt.strftime("%d/%m/%Y")

app.add_template_filter(timeago, "timeago")

@app.context_processor
def inject_now():
    return {"APP_NAME": APP_NAME, "year": datetime.datetime.now().year, "MEET_LINK": MEET_LINK}

# Decoradores
def login_required(view):
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper

def admin_required(view):
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            abort(403)
        return view(*args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper

# --------------------------
# Auth
# --------------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("home"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        conn = get_db(); cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email=?", (email,))
        user = cur.fetchone(); conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_email"] = user["email"]
            session["role"] = user["role"]
            session["is_admin"] = (user["email"] == "admin@conectajoven.pe")
            flash(f"¡Bienvenido/a, {user['name']}!", "success")
            return redirect(url_for("home"))
        flash("Credenciales inválidas", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        role = 'Estudiante interesado'
        if not name or not email or not password:
            flash("Completa todos los campos.", "warning")
            return render_template("register.html")
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name,email,password_hash,role,created_at) VALUES (?,?,?,?,?)",
                (name, email, generate_password_hash(password), role, datetime.datetime.utcnow().isoformat())
            )
            conn.commit()
            flash("Cuenta creada. Ahora inicia sesión.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Ese correo ya está registrado.", "danger")
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/register-mentor", methods=["GET","POST"])
def register_mentor():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        email = request.form.get("email","").strip().lower()
        if not name or not email:
            flash("Completa nombre y correo.", "warning")
            return render_template("register_mentor.html", success=False)
        conn = get_db(); cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO mentor_prereg (name,email,created_at) VALUES (?,?,?)",
                (name, email, datetime.datetime.utcnow().isoformat())
            )
            conn.commit()
            return render_template("register_mentor.html", success=True, name=name, email=email)
        except sqlite3.IntegrityError:
            flash("Ese correo ya fue pre-registrado.", "info")
            return render_template("register_mentor.html", success=False)
        finally:
            conn.close()
    return render_template("register_mentor.html", success=False)

@app.route("/logout")
def logout():
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for("login"))

# --------------------------
# Home
# --------------------------
@app.route("/home")
@login_required
def home():
    novedades = [
        {"titulo":"Open Academy de Santander","url":"https://www.santanderopenacademy.com/es/index.html"},
        {"titulo":"Feria de trabajo de UDEP","url":"https://www.udep.edu.pe/cdcudep/te-conectamos/job-day/"},
        {"titulo":"¡Mejora tu CV con estos pasos! - con Adecco","url":"https://www.adecco.com/en-ca/job-seekers/resources/article/resume-refresh-how-make-cv-stand-out-2025"}
    ]
    enlaces_trabajo = [
        {"nombre":"Computrabajo","url":"https://pe.computrabajo.com/"},
        {"nombre":"Bumeran Perú","url":"https://www.bumeran.com.pe/"},
        {"nombre":"Empleos Perú (MTPE)","url":"https://www.empleosperu.gob.pe/portal-mtpe/#/"}
    ]
    return render_template("home.html", novedades=novedades, enlaces=enlaces_trabajo)

# --------------------------
# Convocatorias (Jobs)
# --------------------------
@app.route("/jobs", methods=["GET","POST"])
@login_required
def jobs():
    conn = get_db(); cur = conn.cursor()

    # === SOLO ADMIN puede agregar ===
    if request.method == "POST":
        if not session.get("is_admin"):
            flash("Solo el administrador puede agregar convocatorias.", "warning")
            return redirect(url_for("jobs"))

        title = request.form.get("title","").strip()
        company = request.form.get("company","").strip()
        link = request.form.get("link","").strip()
        description = request.form.get("description","").strip()
        if title and company and link:
            cur.execute(
                "INSERT INTO jobs (title,company,link,description,created_by,created_at) VALUES (?,?,?,?,?,?)",
                (title, company, link, description, session.get("user_id"), datetime.datetime.utcnow().isoformat())
            )
            conn.commit()
            flash("Convocatoria agregada.", "success")
        else:
            flash("Título, empresa y link son obligatorios.", "warning")

    q = request.args.get("q","").strip()
    if q:
        cur.execute("SELECT * FROM jobs WHERE title LIKE ? OR company LIKE ? ORDER BY id DESC",
                    (f"%{q}%", f"%{q}%"))
    else:
        cur.execute("SELECT * FROM jobs ORDER BY id DESC")
    jobs_list = cur.fetchall()
    conn.close()
    return render_template("jobs.html", jobs=jobs_list, q=q)

@app.route("/jobs/<int:job_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_job(job_id):
    conn = get_db(); cur = conn.cursor()
    # Admin puede borrar cualquier convocatoria
    cur.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    conn.commit(); conn.close()
    flash("Convocatoria eliminada.", "info")
    return redirect(url_for("jobs"))

# Historial de postulaciones (si ya lo usas)
@app.route("/jobs/history")
@login_required
def jobs_history():
    if session.get("is_admin"):
        flash("El historial de postulaciones es solo para usuarios.", "info")
        return redirect(url_for("jobs"))

    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        SELECT j.id, j.title, j.company, j.link, j.description, j.created_at,
               a.created_at AS applied_at
        FROM job_applications a
        JOIN jobs j ON j.id = a.job_id
        WHERE a.user_id = ?
        ORDER BY a.created_at DESC
    """, (session.get("user_id"),))
    applied_jobs = cur.fetchall()
    conn.close()

    return render_template("jobs_history.html", applied_jobs=applied_jobs)

# --------------------------
# Cursos
# --------------------------
@app.route("/courses")
@login_required
def courses():
    categorias = {
        "Tecnología y habilidades digitales": [
            {"id":"prog0","nombre":"Programación desde cero (intro)","desc":"Fundamentos de lógica y programación.","url":"https://www.iue.edu.co/wp-content/uploads/2023/10/Fundamentos-de-programacion.pdf"},
            {"id":"ofimatica","nombre":"Ofimática esencial","desc":"Word, Excel y Presentaciones para principiantes.","url":"https://fpbpastrana.weebly.com/uploads/1/9/6/3/19634459/manual_de_ofim%C3%A1tica.pdf"},
            {"id":"ciberseguridad","nombre":"Ciberseguridad para principiantes","desc":"Buenas prácticas de seguridad personal en línea.","url":"https://www.incibe.es/sites/default/files/docs/senior/guia_ciberseguridad_para_todos.pdf"},
            {"id":"disenoweb","nombre":"Diseño web básico (HTML/CSS)","desc":"Estructura y estilos para tu primera web.","url":"https://ceper.uniandes.edu.co/files/2022/10/MANUAL-HTML-Y-CSS.pdf"},
        ],
        "Idiomas y comunicación": [
            {"id":"inglesA1","nombre":"Inglés A1 — básico","desc":"Vocabulario y frases esenciales para empezar.","url":"https://archive.org/download/1.-el-curso-mas-completo-de-ingles-autor-omar-ali-caldela/1.%20El%20curso%20m%C3%A1s%20completo%20de%20ingl%C3%A9s%20autor%20Omar%20Ali%20Caldela.pdf"},
            {"id":"comunicacion","nombre":"Comunicación efectiva","desc":"Presentación, escucha activa y feedback.","url":"https://solidar-suiza.org.bo/wp-content/uploads/2023/12/guia-habilidades-blandas-conceptos-nov.pdf"},
        ],
        "Empleabilidad y desarrollo profesional": [
            {"id":"cv","nombre":"CV ganador y marca personal","desc":"Estructura, logros y CV amigable con ATS.","url":"https://fisica.us.es/sites/fisica/files/users/user381/CV-Y-MARCA-PERSONAL.pdf"},
            {"id":"entrevista","nombre":"Entrevistas: preguntas frecuentes","desc":"STAR, preguntas difíciles y follow-up.","url":"https://qinnova.uned.es/archivos_publicos/qweb_paginas/3439/entrevistadetrabajo3865.pdf"},
        ],
        "Habilidades técnicas y oficios": [
            {"id":"atencion","nombre":"Atención al cliente y ventas","desc":"Empatía, objeciones y cierre.","url":"https://www.wscconsulting.net/calendario/manualdeventas.pdf"},
            {"id":"primerosAux","nombre":"Primeros auxilios esenciales","desc":"RCP básica, hemorragias y quemaduras.","url":"https://www.unirioja.es/servicios/sprl/pdf/manual_primeros_auxilios.pdf"},
        ],
        "Emprendimiento (opcional)": [
            {"id":"finanzas","nombre":"Finanzas personales para jóvenes","desc":"Presupuesto, ahorro e interés compuesto.","url":"https://webappsos.condusef.gob.mx/EducaTuCartera/GuiasEF/guia_jovenes/guia%20Jovenes%2018-23_2024.pdf"},
            {"id":"emprende","nombre":"Emprendimiento: de idea a piloto","desc":"Propuesta de valor, MVP y pitch.","url":"https://www.youtube.com/watch?v=KEtVQgUBt-w"},
        ],
    }
    return render_template("courses.html", categorias=categorias)

@app.route("/download/<path:filename>")
@login_required
def download(filename):
    dir_path = os.path.join(os.path.dirname(__file__), "static", "courses")
    return send_from_directory(dir_path, filename, as_attachment=True)

# --------------------------
# Asesorías
# --------------------------
def _asesores_base():
    # Avatares demo con i.pravatar.cc
    return [
        {"nombre":"Gustavo","cualidades":["Asertivo","Motivador","Paciente"],"slots":["Lun 10:00-11:00","Mié 16:00-17:00","Vie 09:00-10:00"],"foto":"https://i.pravatar.cc/100?img=11"},
        {"nombre":"Elvis","cualidades":["Servicial","Didáctico","Empático"],"slots":["Lun 17:00-18:00","Jue 15:00-16:00","Sáb 10:00-11:00"],"foto":"https://i.pravatar.cc/100?img=12"},
        {"nombre":"Ángel","cualidades":["Motivador","Organizado","Resolutivo"],"slots":["Mar 09:00-10:00","Jue 19:00-20:00","Sáb 08:00-09:00"],"foto":"https://i.pravatar.cc/100?img=13"},
        {"nombre":"Leonel","cualidades":["Orientador","Empático","Práctico"],"slots":["Mié 11:00-12:00","Vie 18:00-19:00","Dom 16:00-17:00"],"foto":"https://i.pravatar.cc/100?img=14"},
        {"nombre":"Zayuri","cualidades":["Asertiva","Inspiradora","Colaborativa"],"slots":["Mar 18:00-19:00","Jue 09:00-10:00","Sáb 14:00-15:00"],"foto":"https://i.pravatar.cc/100?img=15"},
    ]

@app.route("/advisors", methods=["GET","POST"])
@login_required
def advisors():
    asesores = _asesores_base()
    scheduled = None
    lookup_result = None

    conn = get_db(); cur = conn.cursor()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "schedule":
            dni = request.form.get("dni","").strip()
            name = request.form.get("name","").strip()
            advisor = request.form.get("advisor","").strip()
            date = request.form.get("date","").strip()
            time = request.form.get("time","").strip()

            if not (dni and name and advisor and date and time):
                flash("Completa todos los campos para agendar.", "warning")
            else:
                cur.execute(
                    "INSERT INTO appointments (dni,name,advisor,date,time,created_at) VALUES (?,?,?,?,?,?)",
                    (dni, name, advisor, date, time, datetime.datetime.utcnow().isoformat())
                )
                conn.commit()
                scheduled = {"dni":dni,"name":name,"advisor":advisor,"date":date,"time":time}
                flash("¡Asesoría agendada con éxito!", "success")

        elif action == "lookup":
            dni = request.form.get("dni_lookup","").strip()
            if dni:
                cur.execute("SELECT * FROM appointments WHERE dni=? ORDER BY date,time LIMIT 1", (dni,))
                lookup_result = cur.fetchone()
                if not lookup_result:
                    flash("No hay agendamientos con ese DNI.", "info")
            else:
                flash("Ingresa un DNI para consultar.", "warning")

    appointments = []
    if session.get("is_admin"):
        cur.execute("SELECT * FROM appointments ORDER BY date,time")
        appointments = cur.fetchall()

    conn.close()
    return render_template(
        "advisors.html",
        asesores=asesores,
        scheduled=scheduled,
        appointments=appointments,
        is_admin=session.get("is_admin", False),
        lookup_result=lookup_result
    )

# --------------------------
# Run
# --------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
