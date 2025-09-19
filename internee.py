from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session
from google.cloud import firestore
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Firestore client
db = firestore.Client.from_service_account_json("traineedata-a1379-8c9c23dd84c8.json")

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
    allowed_routes = ["login", "static", "letter_by_name"]
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
# Add internee
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
        doc_ref.update({
            "name": request.form["name"],
            "father": request.form["father"],
            "cnic": request.form["cnic"],
            "phone": request.form["phone"],
            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"]
        })
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
# Generate internship completion letter (PDF) using ReportLab
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

    # Body Text
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

    # Footer Image
    footer_path = "static/s3.png"
    if os.path.exists(footer_path):
        c.drawImage(footer_path, -20, -80, width=width + 20, preserveAspectRatio=True, mask='auto')

    c.save()
    return send_file(filepath_pdf, as_attachment=True)

# -------------------------
# Generate letter by Name (no login required)
# -------------------------
@app.route("/letter_by_name", methods=["GET", "POST"])
def letter_by_name():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("❌ Please provide a name!", "danger")
            return redirect(url_for("letter_by_name"))

        # Search Firestore by name
        docs = db.collection("internees").where("name", "==", name).stream()
        internee = None
        for doc in docs:
            internee = doc.to_dict()
            break

        if not internee:
            flash(f"❌ No internee found with name '{name}'", "danger")
            return redirect(url_for("letter_by_name"))

        # Generate PDF (reuse same code)
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

        # Body Text
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

        # Footer Image
        footer_path = "static/s3.png"
        if os.path.exists(footer_path):
            c.drawImage(footer_path, -20, -80, width=width + 20, preserveAspectRatio=True, mask='auto')

        c.save()
        return send_file(filepath_pdf, as_attachment=True)

    return render_template("letter_by_name.html")  # new template with a form to enter name

# -------------------------
# Run Server
# -------------------------
from waitress import serve

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)
