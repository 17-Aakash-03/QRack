from flask import Flask, jsonify, request, render_template, send_file, session, redirect
import pandas as pd
import os
import qrcode
import io
from werkzeug.utils import secure_filename
from database import init_db, hash_password, get_user, create_user, log_scan, get_scan_logs, get_all_users, delete_user
from functools import wraps

app = Flask(__name__, static_folder='templates', static_url_path='/static')
app.secret_key = "qrack_secret_2024"
EXCEL_FILE = "inventory.xlsx"
ALLOWED_EXTENSIONS = {'xlsx'}

# Init DB on startup
init_db()
if not os.path.exists(EXCEL_FILE):
    import subprocess
    subprocess.run(["python", "generate_qr.py"])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_data():
    return pd.read_excel(EXCEL_FILE, dtype=str)

def save_data(df):
    df.to_excel(EXCEL_FILE, index=False)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "Login required"}), 401
        return f(*args, **kwargs)
    return decorated

def head_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "Login required"}), 401
        if session.get('role') != 'head':
            return jsonify({"error": "Team head access only"}), 403
        return f(*args, **kwargs)
    return decorated

# AUTH ROUTES
@app.route("/")
def index():
    if 'username' not in session:
        return render_template("index.html", logged_in=False)
    return render_template("index.html", logged_in=True,
                           username=session['username'], role=session['role'])

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    user = get_user(data.get("username"))
    if user and user['password'] == hash_password(data.get("password", "")):
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({"success": True, "username": user['username'], "role": user['role']})
    return jsonify({"error": "Invalid username or password"}), 401

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/me")
def me():
    if 'username' not in session:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "username": session['username'], "role": session['role']})

# USER MANAGEMENT (head only)
@app.route("/users", methods=["GET"])
@head_required
def get_users():
    return jsonify(get_all_users())

@app.route("/users", methods=["POST"])
@head_required
def add_user():
    data = request.json
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "member")
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400
    if create_user(username, password, role):
        return jsonify({"success": True})
    return jsonify({"error": "Username already exists"}), 400

@app.route("/users/<int:user_id>", methods=["DELETE"])
@head_required
def remove_user(user_id):
    delete_user(user_id)
    return jsonify({"success": True})

# ITEM ROUTES
@app.route("/item/<qr_id>", methods=["GET"])
@login_required
def get_item(qr_id):
    try:
        df = load_data()
        row = df[df["QR Code ID"] == qr_id]
        if row.empty:
            return jsonify({"error": "Item not found"}), 404
        return jsonify(row.iloc[0].to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/item/<qr_id>", methods=["POST"])
@login_required
def update_item(qr_id):
    try:
        data = request.json
        remark = data.pop("remark", "")
        role = session.get('role')

        df = load_data()
        idx = df[df["QR Code ID"] == qr_id].index
        if idx.empty:
            return jsonify({"error": "Item not found"}), 404

        # Only head can change verification status
        if role != 'head' and 'Verification Status' in data:
            data.pop('Verification Status')

        for key, value in data.items():
            if key in df.columns:
                df.at[idx[0], key] = value

        # Log scan timestamp
        df.at[idx[0], 'Last Scanned'] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        df.at[idx[0], 'Scanned By'] = session['username']

        save_data(df)

        # Log to SQLite
        current_status = df.at[idx[0], 'Verification Status']
        log_scan(qr_id, session['username'], remark, current_status)

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/scan-log/<qr_id>", methods=["POST"])
@login_required
def log_scan_only(qr_id):
    try:
        data = request.json
        remark = data.get("remark", "")
        df = load_data()
        row = df[df["QR Code ID"] == qr_id]
        if row.empty:
            return jsonify({"error": "Item not found"}), 404
        status = row.iloc[0].get("Verification Status", "")
        log_scan(qr_id, session['username'], remark, status)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/items", methods=["GET"])
@login_required
def get_all_items():
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify([])
        df = load_data()
        return jsonify(df.to_dict(orient='records'))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/upload-excel", methods=["POST"])
@head_required
def upload_excel():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file"}), 400
        file.save(EXCEL_FILE)
        df = load_data()
        new_qr = 0
        os.makedirs("qrcodes", exist_ok=True)
        for _, row in df.iterrows():
            qr_id = str(row.get("QR Code ID", "")).strip()
            if qr_id and qr_id != 'nan' and not os.path.exists(f"qrcodes/{qr_id}.png"):
                qr = qrcode.make(qr_id)
                qr.save(f"qrcodes/{qr_id}.png")
                new_qr += 1
        return jsonify({"success": True, "total_items": len(df), "new_qr_generated": new_qr})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/qrcode/<qr_id>")
def serve_qr(qr_id):
    path = f"qrcodes/{qr_id}.png"
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, mimetype="image/png")

# REPORT
@app.route("/report")
@head_required
def get_report():
    try:
        logs = get_scan_logs()
        df = load_data()
        total = len(df)
        scanned = len(logs)
        verified = sum(1 for l in logs if l['verification_status'] == 'Verified')
        pending = sum(1 for l in logs if l['verification_status'] == 'Pending')
        rejected = sum(1 for l in logs if l['verification_status'] == 'Rejected')
        not_scanned = total - scanned
        return jsonify({
            "total": total, "scanned": scanned,
            "verified": verified, "pending": pending,
            "rejected": rejected, "not_scanned": not_scanned,
            "logs": logs
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/report/download")
@head_required
def download_report():
    try:
        logs = get_scan_logs()
        df_logs = pd.DataFrame(logs, columns=['id','qr_id','scanned_by','timestamp','remark','verification_status'])
        df_logs.drop(columns=['id'], inplace=True)
        df_logs.columns = ['QR Code ID', 'Scanned By', 'Timestamp', 'Remark', 'Verification Status']

        # Merge with inventory
        if os.path.exists(EXCEL_FILE):
            df_inv = load_data()
            df_merged = pd.merge(df_inv, df_logs, on='QR Code ID', how='left')
        else:
            df_merged = df_logs

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_merged.to_excel(writer, sheet_name='Scan Report', index=False)
            # Summary sheet
            df_summary = pd.DataFrame({
                'Status': ['Total Items', 'Scanned', 'Verified', 'Pending', 'Rejected', 'Not Scanned'],
                'Count': [
                    len(df_inv) if os.path.exists(EXCEL_FILE) else 0,
                    len(logs),
                    sum(1 for l in logs if l['verification_status'] == 'Verified'),
                    sum(1 for l in logs if l['verification_status'] == 'Pending'),
                    sum(1 for l in logs if l['verification_status'] == 'Rejected'),
                    (len(df_inv) if os.path.exists(EXCEL_FILE) else 0) - len(logs)
                ]
            })
            df_summary.to_excel(writer, sheet_name='Summary', index=False)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name='QRack_Report.xlsx')
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/static/manifest.json')
def manifest():
    return send_file('templates/manifest.json', mimetype='application/manifest+json')

@app.route('/static/sw.js')
def sw():
    return send_file('templates/sw.js', mimetype='application/javascript')

if __name__ == "__main__":
    app.run(debug=False)