from flask import Flask, render_template, request, redirect, send_from_directory, url_for, flash, send_file, session, abort
from google.cloud import firestore
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os, secrets
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Firestore client
db = firestore.Client.from_service_account_json("traineedata-a1379-8c9c23dd84c8.json")

# -------------------------
# File Upload Config
# -------------------------
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# -------------------------
# Serve Uploaded Files
# -------------------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -------------------------
# Invite Token Storage
# -------------------------
invite_tokens = {}  # {token: expiry_datetime}

# -------------------------
# Login System
# -------------------------
USERNAME = "rizwan89"
PASSWORD = "1234567891"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if username == USERNAME and password == PASSWORD:
            session["user"] = username
            flash("✅ Logged in successfully!", "success")
            return redirect(url_for("index"))
        else:
            flash("❌ Invalid username or password", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

# -------------------------
# Protect main routes
# -------------------------
@app.before_request
def require_login():
    allowed_routes = ["login", "static", "letter_by_name", "invite_form"]
    if "user" not in session and request.endpoint not in allowed_routes:
        return redirect(url_for("login"))

# -------------------------
# Home → Show internee list
# -------------------------
@app.route("/")
def index():
    docs = db.collection("internees").stream()
    internees = []
    today = datetime.today().date()
    is_direct_open = request.referrer is None or request.referrer.endswith(request.host_url)

    for doc in docs:
        d = doc.to_dict()
        d["id"] = doc.id
        if is_direct_open:
            try:
                end_date = datetime.strptime(d["end"], "%Y-%m-%d").date()
                days_left = (end_date - today).days
                if days_left in [2, 3]:
                    flash(f"⚠️ {d['name']}'s internship ends in {days_left} days!", "warning")
            except Exception as e:
                print("Date parse error:", e)
        internees.append(d)

    return render_template("index.html", internees=internees)

# -------------------------
# Generate secure invite link (valid 10 min)
# -------------------------
@app.route("/generate_invite")
def generate_invite():
    token = secrets.token_urlsafe(16)
    expiry = datetime.utcnow() + timedelta(minutes=10)
    invite_tokens[token] = expiry
    invite_link = url_for("invite_form", token=token, _external=True)
    flash(f"🔗 Invite link (valid 10 min): {invite_link}", "success")
    return redirect(url_for("index"))

@app.route("/invite/<token>", methods=["GET", "POST"])
def invite_form(token):
    expiry = invite_tokens.get(token)
    if not expiry or datetime.utcnow() > expiry:
        return abort(403, description="❌ This invite link has expired")

    if request.method == "POST":
        data = {
            "name": request.form["name"],
            "father": request.form["father"],
            "cnic": request.form["cnic"],
            "phone": request.form["phone"],
            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"],
        }

        # ✅ Handle image upload
        image_file = request.files.get("image")
        cnic_file = request.files.get("cnic_image")

        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if not os.path.exists(save_path):  # <-- check before saving
             image_file.save(save_path)
            data["image"] = filename  # only store filename in Firestore

        if cnic_file and allowed_file(cnic_file.filename):
           cnic_filename = secure_filename(cnic_file.filename)
           cnic_file.save(os.path.join(app.config["UPLOAD_FOLDER"], cnic_filename))
           if not os.path.exists(save_path):  # <-- check before saving
            image_file.save(save_path)
           data["cnic_image"] = cnic_filename

        db.collection("internees").add(data)

        # Invalidate token after use
        invite_tokens.pop(token, None)

        flash("✅ Staff data added successfully!", "success")
        return redirect(url_for("login"))

    return render_template("invite_form.html")

# -------------------------
# Add internee (Admin only)
# -------------------------
@app.route("/add", methods=["POST"])
def add_internee():
    data = {
        "name": request.form["name"],
        "father": request.form["father"],
        "cnic": request.form["cnic"],
        "phone": request.form["phone"],
        "field": request.form["field"],
        "start": request.form["start"],
        "end": request.form["end"],
    }

    # Handle image upload
    image_file = request.files.get("image")
    cnic_file = request.files.get("cnic_image")

    if image_file and allowed_file(image_file.filename):
        filename = secure_filename(image_file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        if not os.path.exists(save_path):  # <-- check before saving
         image_file.save(save_path)
        data["image"] = filename  # ✅ only save filename in Firestore

    if cnic_file and allowed_file(cnic_file.filename):
       cnic_filename = secure_filename(cnic_file.filename)
       cnic_file.save(os.path.join(app.config["UPLOAD_FOLDER"], cnic_filename))
       if not os.path.exists(save_path):  # <-- check before saving
        image_file.save(save_path)
       data["cnic_image"] = cnic_filename

    db.collection("internees").add(data)
    flash("✅ Internee Added Successfully!", "success")
    return redirect(url_for("index"))



# -------------------------
# Edit internee
# -------------------------
@app.route("/edit/<id>", methods=["GET", "POST"])
def edit_internee(id):
    doc_ref = db.collection("internees").document(id)
    data = doc_ref.get().to_dict()
    if request.method == "POST":
        update_data = {
            "name": request.form["name"],
            "father": request.form["father"],
            "cnic": request.form["cnic"],
            "phone": request.form["phone"],
            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"]
        }

        # ✅ Handle new image if uploaded
        image_file = request.files.get("image")
        if image_file and allowed_file(image_file.filename):
            filename = secure_filename(image_file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            if not os.path.exists(save_path):  # <-- check before saving
             image_file.save(save_path)
            update_data["image"] = filename  # overwrite old image in Firestore

        doc_ref.update(update_data)
        flash("✅ Internee Updated Successfully!", "success")
        return redirect(url_for("index"))

    return render_template("edit.html", internee=data, id=id)


# -------------------------
# Delete internee
# -------------------------
@app.route("/delete/<id>")
def delete_internee(id):
    db.collection("internees").document(id).delete()
    flash("❌ Internee Deleted Successfully!", "danger")
    return redirect(url_for("index"))

# -------------------------
# Generate internship completion letter (PDF)
# -------------------------
@app.route("/letter/<id>", methods=["POST"])
def generate_letter(id):
    internee = db.collection("internees").document(id).get().to_dict()
    if not internee:
        flash("❌ Internee not found!", "danger")
        return redirect(url_for("index"))

    letters_dir = "letters"
    os.makedirs(letters_dir, exist_ok=True)
    filepath_pdf = os.path.join(letters_dir, f"{internee['name'].replace(' ', '_')}_letter.pdf")

    c = canvas.Canvas(filepath_pdf, pagesize=A4)
    width, height = A4
    margin = 50
    y = height - margin

    # Header Image
    header_path = "static/s4.png"
    if os.path.exists(header_path):
        c.drawImage(header_path, margin - 55, y - 100, width=width + 20, preserveAspectRatio=True, mask='auto')
        y -= 120

    # Stamp Image
    stamp_path = "static/stamp.png"
    if os.path.exists(stamp_path):
        stamp_width = 100
        stamp_height = 100
        c.drawImage(stamp_path, width - stamp_width - 20, 130, width=stamp_width, height=stamp_height, preserveAspectRatio=True, mask='auto')

    # Title
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width/2, y, "Internship Completion Letter")
    y -= 50

    # Body
    c.setFont("Helvetica", 12)
    text_lines = [
        f"This is to certify that {internee['name']},",
        f"Son/Daughter of {internee['father']},",
        f"worked as a {internee['field']} Intern at TreeSol Technologies PVT Ltd.",
        f"from {internee['start']} to {internee['end']}.",
        "During the internship, he/she demonstrated good skills with a self-motivated attitude",
        "to learn new things.",
        "We wish him/her all the best for his/her future endeavors.",
        "",
        f"Issued on: {datetime.today().strftime('%d-%m-%Y')}",
        "",
        "Warm Regards,",
        "TreeSol Technologies PVT Ltd."
    ]
    for line in text_lines:
        c.drawString(margin, y, line)
        y -= 20

    # Footer
    footer_path = "static/s3.png"
    if os.path.exists(footer_path):
        c.drawImage(footer_path, -20, -80, width=width + 20, preserveAspectRatio=True, mask='auto')

    c.save()
    return send_file(filepath_pdf, as_attachment=True)

# -------------------------
# Letter by Name (Public)
# -------------------------
@app.route("/letter_by_name", methods=["GET", "POST"])
def letter_by_name():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("❌ Please provide a name!", "danger")
            return redirect(url_for("letter_by_name"))

        docs = db.collection("internees").where("name", "==", name).stream()
        internee = None
        for doc in docs:
            internee = doc.to_dict()
            break

        if not internee:
            flash(f"❌ No internee found with name '{name}'", "danger")
            return redirect(url_for("letter_by_name"))

        # ✅ Check internship end date
        try:
            end_date = datetime.strptime(internee["end"], "%Y-%m-%d").date()
            today = datetime.today().date()
            if today < end_date:
                flash(f"⚠️ Letter cannot be generated before internship end date ({end_date})", "warning")
                return redirect(url_for("letter_by_name"))
        except Exception:
            flash("❌ Invalid end date format in record", "danger")
            return redirect(url_for("letter_by_name"))

        letters_dir = "letters"
        os.makedirs(letters_dir, exist_ok=True)
        filepath_pdf = os.path.join(letters_dir, f"{internee['name'].replace(' ', '_')}_letter.pdf")

        c = canvas.Canvas(filepath_pdf, pagesize=A4)
        width, height = A4
        margin = 50
        y = height - margin

        header_path = "static/s4.png"
        if os.path.exists(header_path):
            c.drawImage(header_path, margin - 55, y - 100, width=width + 20, preserveAspectRatio=True, mask='auto')
            y -= 120

        stamp_path = "static/stamp.png"
        if os.path.exists(stamp_path):
            stamp_width = 100
            stamp_height = 100
            c.drawImage(stamp_path, width - stamp_width - 20, 130, width=stamp_width, height=stamp_height, preserveAspectRatio=True, mask='auto')

        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width/2, y, "Internship Completion Letter")
        y -= 50

        c.setFont("Helvetica", 12)
        text_lines = [
            f"This is to certify that {internee['name']},",
            f"Son/Daughter of {internee['father']},",
            f"worked as a {internee['field']} Intern at TreeSol Technologies PVT Ltd.",
            f"from {internee['start']} to {internee['end']}.",
            "During the internship, he/she demonstrated good skills with a self-motivated attitude",
            "to learn new things.",
            "We wish him/her all the best for his/her future endeavors.",
            "",
            f"Issued on: {datetime.today().strftime('%d-%m-%Y')}",
            "",
            "Warm Regards,",
            "TreeSol Technologies PVT Ltd."
        ]
        for line in text_lines:
            c.drawString(margin, y, line)
            y -= 20

        footer_path = "static/s3.png"
        if os.path.exists(footer_path):
            c.drawImage(footer_path, -20, -80, width=width + 20, preserveAspectRatio=True, mask='auto')

        c.save()
        return send_file(filepath_pdf, as_attachment=True)

    return render_template("letter_by_name.html")

# -------------------------
# Run Server
# -------------------------
from waitress import serve
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
