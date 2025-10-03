from flask import Flask, render_template, request, redirect, url_for, flash, send_file, session, abort
from google.cloud import firestore
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import os, secrets
from werkzeug.utils import secure_filename
import cloudinary
import cloudinary.uploader

app = Flask(__name__)
app.secret_key = "your_secret_key"

# -------------------------
# Firestore client
# -------------------------
db = firestore.Client.from_service_account_json("traineedata-a1379-8c9c23dd84c8.json")

# -------------------------
# Cloudinary Config
# -------------------------
cloudinary.config(
    cloud_name="dvhlxd4da",
    api_key="245219356924251",
    api_secret="YkrL125ing29yT574dvjqjbjGJE"
)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

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
    expiry = datetime.utcnow() + timedelta(hours=24)   # 24 hours validity
    invite_tokens[token] = expiry
    invite_link = url_for("invite_form", token=token, _external=True)
    flash(f"🔗 Invite link (valid 24 hours): {invite_link}", "success")
    return redirect(url_for("index"))


@app.route("/invite/<token>", methods=["GET", "POST"])
def invite_form(token):
    expiry = invite_tokens.get(token)
    if not expiry or datetime.utcnow() > expiry:
        return abort(403, description="❌ This invite link has expired")

    if request.method == "POST":
        cnic = request.form["cnic"].strip()

        # 🔎 Check if CNIC already exists
        existing = db.collection("internees").where("cnic", "==", cnic).stream()
        if any(existing):
            flash("⚠️ CNIC already exists! Staff cannot be added again.", "warning")
            return redirect(url_for("invite_form", token=token))

        data = {
            "name": request.form["name"],
            "father": request.form["father"],
            "cnic": cnic,
            "phone": request.form["phone"],
            "gender": request.form["gender"],

            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"],
        }

        # ✅ Upload to Cloudinary
        image_file = request.files.get("image")
        cnic_file = request.files.get("cnic_image")

        if image_file and allowed_file(image_file.filename):
            upload_result = cloudinary.uploader.upload(image_file, folder="internees")
            data["image"] = upload_result["secure_url"]

        if cnic_file and allowed_file(cnic_file.filename):
            upload_result = cloudinary.uploader.upload(cnic_file, folder="internees/cnic")
            data["cnic_image"] = upload_result["secure_url"]

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
    cnic = request.form["cnic"].strip()

    # 🔎 Check if CNIC already exists
    existing = db.collection("internees").where("cnic", "==", cnic).stream()
    if any(existing):
        flash("⚠️ CNIC already exists! Internee cannot be added again.", "warning")
        return redirect(url_for("index"))

    data = {
        "name": request.form["name"],
        "father": request.form["father"],
        "cnic": cnic,
        "phone": request.form["phone"],
        "gender": request.form["gender"],

        "field": request.form["field"],
        "start": request.form["start"],
        "end": request.form["end"],
    }

    # ✅ Upload to Cloudinary
    image_file = request.files.get("image")
    cnic_file = request.files.get("cnic_image")

    if image_file and allowed_file(image_file.filename):
        upload_result = cloudinary.uploader.upload(image_file, folder="internees")
        data["image"] = upload_result["secure_url"]

    if cnic_file and allowed_file(cnic_file.filename):
        upload_result = cloudinary.uploader.upload(cnic_file, folder="internees/cnic")
        data["cnic_image"] = upload_result["secure_url"]

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
            "gender": request.form["gender"],

            "field": request.form["field"],
            "start": request.form["start"],
            "end": request.form["end"]
        }

        # ✅ Upload new image if provided
        image_file = request.files.get("image")
        if image_file and allowed_file(image_file.filename):
            upload_result = cloudinary.uploader.upload(image_file, folder="internees")
            update_data["image"] = upload_result["secure_url"]

        doc_ref.update(update_data)
        flash("✅ Staff Updated Successfully!", "success")
        return redirect(url_for("index"))

    return render_template("edit.html", internee=data, id=id)

# -------------------------
# Delete internee
# -------------------------
@app.route("/delete/<id>")
def delete_internee(id):
    db.collection("internees").document(id).delete()
    flash("❌ Staff Deleted Successfully!", "danger")
    return redirect(url_for("index"))

from reportlab.lib.utils import simpleSplit

# -------------------------
# Generate internship completion letter (PDF)
# -------------------------
@app.route("/letter/<id>", methods=["POST"])
def generate_letter(id):
    internee = db.collection("internees").document(id).get().to_dict()
    if not internee:
        flash("❌ Staff not found!", "danger")
        return redirect(url_for("index"))

    letters_dir = "letters"
    os.makedirs(letters_dir, exist_ok=True)
    filepath_pdf = os.path.join(
        letters_dir, f"{internee['name'].replace(' ', '_')}_letter.pdf"
    )

    c = canvas.Canvas(filepath_pdf, pagesize=A4)
    width, height = A4
    margin = 50
    y = height - margin

    # Header Image
    header_path = "static/s4.png"
    if os.path.exists(header_path):
        c.drawImage(
            header_path,
            margin - 55,
            y - 100,
            width=width + 20,
            preserveAspectRatio=True,
            mask="auto",
        )
        y -= 120

    # Stamp Image
    stamp_path = "static/stamp1.png"
    if os.path.exists(stamp_path):
        stamp_width = 250
        stamp_height = 250
        c.drawImage(
            stamp_path,
            width - stamp_width - 20,
            230,
            width=stamp_width,
            height=stamp_height,
            preserveAspectRatio=True,
            mask="auto",
        )

    # Issued On (top left)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin, y, f"ISSUE DATE: {datetime.today().strftime('%d-%m-%Y')}")
    y -= 40

    # Title (centered)
    c.setFont("Helvetica-Bold", 16)
    c.drawCentredString(width / 2, y, "To whom it may concern")
    y -= 50

    # ---------------- Gender-based pronouns ----------------
    gender = internee.get("gender", "").lower()
    if gender == "male":
        relation = "son"
        pronoun_subject = "he"
        pronoun_object = "him"
        pronoun_possessive = "his"
    elif gender == "female":
        relation = "daughter"
        pronoun_subject = "she"
        pronoun_object = "her"
        pronoun_possessive = "her"
    else:
        # default neutral (in case gender not set)
        relation = "son/daughter"
        pronoun_subject = "he/she"
        pronoun_object = "him/her"
        pronoun_possessive = "his/her"

    # Body (wrapped with bold name + field)
    max_width = width - (2 * margin)

    segments = [
        ("normal", "This is to certify that "),
        ("bold", internee['name']),
        ("normal", f", {relation} of {internee['father']}, worked as a "),
        ("bold", internee['field']),
        (
            "normal",
            f" Intern at TreeSol Technologies PVT Ltd. from {internee['start']} to {internee['end']}. "
            f"During the internship, {pronoun_subject} demonstrated good skills with a self-motivated attitude "
            f"to learn new things. We wish {pronoun_object} all the best for {pronoun_possessive} future endeavors."
        ),
    ]

    x, current_y = margin, y
    line_height = 18
    font_size = 12

    for style, text in segments:
        if style == "bold":
            c.setFont("Helvetica-Bold", font_size)
        else:
            c.setFont("Helvetica", font_size)

        words = text.split(" ")
        for word in words:
            word_width = c.stringWidth(word + " ", c._fontname, font_size)
            if x + word_width > width - margin:  # wrap to next line
                current_y -= line_height
                x = margin
            c.drawString(x, current_y, word)
            x += word_width

    y = current_y - 40  # move down after paragraph

    # Warm Regards (left)
    c.setFont("Helvetica", 12)
    c.drawString(margin, y, "Warm Regards,")

    # Footer Image
    footer_path = "static/s3.png"
    if os.path.exists(footer_path):
        c.drawImage(
            footer_path,
            -20,
            -80,
            width=width + 20,
            preserveAspectRatio=True,
            mask="auto",
        )

    c.save()
    return send_file(filepath_pdf, as_attachment=True)



# -------------------------
# Letter by Name (Public)
# -------------------------
@app.route("/letter_by_name", methods=["GET", "POST"])
def letter_by_name():
    if request.method == "POST":
        name = request.form.get("cnic", "").strip()
        if not name:
            flash("❌ Please provide a CNIC!", "danger")
            return redirect(url_for("letter_by_name"))

        docs = db.collection("internees").where("cnic", "==", name).stream()
        internee = None
        for doc in docs:
            internee = doc.to_dict()
            break

        if not internee:
            flash(f"❌ No Staff found with CNIC '{name}'", "danger")
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
        filepath_pdf = os.path.join(
            letters_dir, f"{internee['name'].replace(' ', '_')}_letter.pdf"
        )

        c = canvas.Canvas(filepath_pdf, pagesize=A4)
        width, height = A4
        margin = 50
        y = height - margin

        # ---------------- Header Image ----------------
        header_path = "static/s4.png"
        if os.path.exists(header_path):
            c.drawImage(
                header_path,
                margin - 55,
                y - 100,
                width=width + 20,
                preserveAspectRatio=True,
                mask="auto",
            )
            y -= 120

        # ---------------- Stamp Image ----------------
        stamp_path = "static/stamp1.png"
        if os.path.exists(stamp_path):
            stamp_width = 250
            stamp_height = 250
            c.drawImage(
                stamp_path,
                width - stamp_width - 20,
                230,
                width=stamp_width,
                height=stamp_height,
                preserveAspectRatio=True,
                mask="auto",
            )

        # ---------------- Issued Date ----------------
        c.setFont("Helvetica-Bold", 12)
        c.drawString(margin, y, f"ISSUE DATE: {datetime.today().strftime('%d-%m-%Y')}")
        y -= 40

        # ---------------- Title ----------------
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, y, "To whom it may concern")
        y -= 50

        # ---------------- Gender-based pronouns ----------------
        gender = internee.get("gender", "").lower()
        if gender == "male":
            relation = "son"
            pronoun_subject = "he"
            pronoun_object = "him"
            pronoun_possessive = "his"
        elif gender == "female":
            relation = "daughter"
            pronoun_subject = "she"
            pronoun_object = "her"
            pronoun_possessive = "her"
        else:
            relation = "son/daughter"
            pronoun_subject = "he/she"
            pronoun_object = "him/her"
            pronoun_possessive = "his/her"

        # ---------------- Body with Bold Segments ----------------
        max_width = width - (2 * margin)
        segments = [
            ("normal", "This is to certify that "),
            ("bold", internee["name"]),
            ("normal", f", {relation} of {internee['father']}, worked as a "),
            ("bold", internee["field"]),
            (
                "normal",
                f" Intern at TreeSol Technologies PVT Ltd. from {internee['start']} to {internee['end']}. "
                f"During the internship, {pronoun_subject} demonstrated good skills with a self-motivated attitude "
                f"to learn new things. We wish {pronoun_object} all the best for {pronoun_possessive} future endeavors.",
            ),
        ]

        x, current_y = margin, y
        line_height = 18
        font_size = 12

        for style, text in segments:
            if style == "bold":
                c.setFont("Helvetica-Bold", font_size)
            else:
                c.setFont("Helvetica", font_size)

            words = text.split(" ")
            for word in words:
                word_width = c.stringWidth(word + " ", c._fontname, font_size)
                if x + word_width > width - margin:  # wrap to next line
                    current_y -= line_height
                    x = margin
                c.drawString(x, current_y, word)
                x += word_width

        y = current_y - 40  # move down after paragraph

        # ---------------- Warm Regards ----------------
        c.setFont("Helvetica", 12)
        c.drawString(margin, y, "Warm Regards,")
        y -= 36  # gap

        # ---------------- Footer Image ----------------
        footer_path = "static/s3.png"
        if os.path.exists(footer_path):
            c.drawImage(
                footer_path,
                -20,
                -80,
                width=width + 20,
                preserveAspectRatio=True,
                mask="auto",
            )

        c.save()
        return send_file(filepath_pdf, as_attachment=True)

    return render_template("letter_by_name.html")



# -------------------------
# Run Server
# -------------------------
from waitress import serve
if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=8080)

