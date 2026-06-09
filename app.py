from flask import Flask, jsonify, request, render_template, send_file
import pandas as pd
import os
import qrcode
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='templates', static_url_path='/static')
EXCEL_FILE = "inventory.xlsx"
ALLOWED_EXTENSIONS = {'xlsx'}

# Auto generate inventory on startup if not exists
if not os.path.exists(EXCEL_FILE):
    import subprocess
    subprocess.run(["python", "generate_qr.py"])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_data():
    return pd.read_excel(EXCEL_FILE, dtype=str)

def save_data(df):
    df.to_excel(EXCEL_FILE, index=False)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/item/<qr_id>", methods=["GET"])
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
def update_item(qr_id):
    try:
        df = load_data()
        idx = df[df["QR Code ID"] == qr_id].index
        if idx.empty:
            return jsonify({"error": "Item not found"}), 404
        data = request.json
        for key, value in data.items():
            if key in df.columns:
                df.at[idx[0], key] = value
        save_data(df)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/qrcode/<qr_id>")
def serve_qr(qr_id):
    path = f"qrcodes/{qr_id}.png"
    if not os.path.exists(path):
        return "Not found", 404
    return send_file(path, mimetype="image/png")

@app.route("/upload-excel", methods=["POST"])
def upload_excel():
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({"error": "Invalid file. Please upload .xlsx"}), 400
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
        return jsonify({
            "success": True,
            "total_items": len(df),
            "new_qr_generated": new_qr
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/items", methods=["GET"])
def get_all_items():
    try:
        if not os.path.exists(EXCEL_FILE):
            return jsonify([])
        df = load_data()
        return jsonify(df.to_dict(orient='records'))
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