from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import base64
from Crypto.Cipher import AES
from datetime import datetime, timedelta
import requests

app = Flask(__name__)
app.secret_key = "supersecretkey"

DB = "database.db"
AES_KEY = b"Sixteen byte key"  # Must match ESP32 key (16 bytes)
WEATHER_API_KEY = "94a0aec010d14f6e94c210133250511 "  # <--  actual key

# ---------------- DATABASE SETUP ----------------
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS users(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE,
                 password TEXT,
                 security_question TEXT,
                 security_answer TEXT
                 )""")
    c.execute("""CREATE TABLE IF NOT EXISTS sensor_data(
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 temperature TEXT,
                 humidity TEXT,
                 timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                 )""")
    conn.commit()
    conn.close()
init_db()

# ---------------- AES DECRYPTION ----------------
def decrypt_aes_ecb(enc_b64):
    try:
        enc_bytes = base64.b64decode(enc_b64)
        cipher = AES.new(AES_KEY, AES.MODE_ECB)
        decrypted = cipher.decrypt(enc_bytes)

        # Proper PKCS7 unpadding
        pad_len = decrypted[-1]
        if pad_len < 1 or pad_len > 16:
            return "ERROR"
        decrypted = decrypted[:-pad_len]

        clean = "".join([c for c in decrypted.decode("latin1") if c.isdigit() or c=='.' or c=='-'])
        return clean
    except Exception as e:
        print(f"Decryption error: {e}")
        return "ERROR"

# ---------------- SECURITY QUESTIONS ----------------
SECURITY_QUESTIONS = [
    "What was the name of your first pet?",
    "What is your mother’s maiden name?",
    "What was the make of your first car?",
    "In which city were you born?",
    "What is your favorite book?",
    "What is your favorite food?",
    "What was the name of your elementary school?",
    "What is your father’s middle name?",
    "What is your favorite color?",
    "What was your childhood nickname?",
    "What street did you grow up on?",
    "What was the name of your first teacher?",
    "What is the name of your best friend from childhood?",
    "What was your dream job as a child?",
    "What is your favorite movie?",
    "What is your favorite sport?",
    "What is the name of your first stuffed animal?",
    "Where did you go on your first vacation?",
    "What is your favorite holiday destination?",
    "What is your favorite restaurant?"
]

# ---------------- AUTH ----------------
@app.route("/", methods=["GET","POST"])
def auth():
    if "user_id" in session:
        return redirect(url_for("dashboard"))

    active_tab = "login"
    if request.method=="POST":
        action = request.form.get("action")
        username = request.form.get("username")
        password = request.form.get("password")
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        if action=="login":
            c.execute("SELECT id,password FROM users WHERE username=?",(username,))
            row = c.fetchone()
            conn.close()
            if row and check_password_hash(row[1], password):
                session["user_id"] = row[0]
                return redirect(url_for("dashboard"))
            else:
                flash("Incorrect username or password","danger")
                active_tab = "login"
        elif action=="register":
            confirm_password = request.form.get("confirm_password")
            question = request.form.get("security_question")
            answer = request.form.get("security_answer")
            if password != confirm_password:
                flash("Passwords do not match","danger")
                active_tab="register"
            else:
                hashed = generate_password_hash(password)
                try:
                    c.execute("INSERT INTO users(username,password,security_question,security_answer) VALUES (?,?,?,?)",
                              (username,hashed,question,answer))
                    conn.commit()
                    flash("Registration successful. Please login.","success")
                    active_tab="login"
                except sqlite3.IntegrityError:
                    flash("Username already exists","danger")
                    active_tab="register"
                finally:
                    conn.close()
    return render_template("auth.html", active_tab=active_tab, questions=SECURITY_QUESTIONS)

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth"))

# ---------------- FORGOT PASSWORD ----------------
@app.route("/forgot", methods=["GET","POST"])
def forgot():
    verified=False
    if request.method=="POST":
        username = request.form.get("username")
        question = request.form.get("security_question")
        answer = request.form.get("security_answer")
        new_pass = request.form.get("new_password")
        confirm_pass = request.form.get("confirm_password")

        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=? AND security_question=? AND security_answer=?",
                  (username,question,answer))
        row = c.fetchone()
        if row:
            verified=True
            if new_pass and confirm_pass:
                if new_pass != confirm_pass:
                    flash("Passwords do not match","danger")
                else:
                    hashed = generate_password_hash(new_pass)
                    c.execute("UPDATE users SET password=? WHERE id=?",(hashed,row[0]))
                    conn.commit()
                    flash("Password reset successful. Please login.","success")
                    conn.close()
                    return redirect(url_for("auth"))
        else:
            flash("Incorrect username/question/answer","danger")
        conn.close()
    return render_template("forgot.html", questions=SECURITY_QUESTIONS, verified=verified)

# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("auth"))
    username = get_username(session["user_id"])
    return render_template("dashboard.html", username=username, current_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

def get_username(user_id):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE id=?",(user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "User"

# ---------------- ESP32 DATA ----------------
@app.route("/api/upload", methods=["POST"])
def api_upload():
    data = request.get_json()
    try:
        temp_enc = data.get("temperature")
        hum_enc = data.get("humidity")
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("INSERT INTO sensor_data(temperature,humidity) VALUES (?,?)",(temp_enc,hum_enc))
        conn.commit()
        conn.close()
        return jsonify({"status":"success"}),200
    except Exception as e:
        print(f"Error uploading sensor data: {e}")
        return jsonify({"status":"error","message":str(e)}),400

@app.route("/api/sensor_data")
def api_sensor_data():
    limit = request.args.get("limit", default=None, type=int)
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    if limit:
        c.execute("SELECT temperature,humidity,timestamp FROM sensor_data ORDER BY timestamp DESC LIMIT ?",(limit,))
    else:
        c.execute("SELECT temperature,humidity,timestamp FROM sensor_data ORDER BY timestamp DESC")
    rows = c.fetchall()
    conn.close()
    data=[]
    for row in reversed(rows):
        temp_enc, hum_enc, ts = row
        data.append({"temperature":decrypt_aes_ecb(temp_enc),
                     "humidity":decrypt_aes_ecb(hum_enc),
                     "timestamp":ts})
    return jsonify(data)

# ---------------- WEATHER API ----------------
weather_cache={"data":None,"timestamp":None}

@app.route("/api/weather")
def api_weather():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"error":"Missing lat/lon"}),400

    if weather_cache["data"] and (datetime.now()-weather_cache["timestamp"]) < timedelta(minutes=10):
        return jsonify(weather_cache["data"])

    try:
        url = f"http://api.weatherapi.com/v1/current.json?key={WEATHER_API_KEY}&q={lat},{lon}"
        r = requests.get(url, timeout=5)
        r.raise_for_status()
        data = r.json()
        weather={ 
            "location": data["location"]["name"],
            "temperature": data["current"]["temp_c"],
            "humidity": data["current"]["humidity"],
            "condition": data["current"]["condition"]["text"]
        }
        weather_cache["data"]=weather
        weather_cache["timestamp"]=datetime.now()
        return jsonify(weather)
    except Exception as e:
        print("Weather API error:", e)
        return jsonify({"error":"Failed to fetch weather"}),500

# ---------------- REVERSE GEOCODING ----------------
@app.route("/api/reverse_geocode")
def reverse_geocode():
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    if not lat or not lon:
        return jsonify({"error":"Missing lat/lon"}),400
    try:
        r = requests.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lon}", headers={"User-Agent":"IoT-Dashboard"})
        r.raise_for_status()
        data = r.json()
        return jsonify(data.get("address",{}))
    except Exception as e:
        print("Reverse geocode error:",e)
        return jsonify({"error":"Failed"}),500

# ---------------- RUN ----------------
# app.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

