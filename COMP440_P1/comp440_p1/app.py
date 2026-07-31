"""
COMP 440 - Course Project: Phase 1
Registration + Login system with SQL-injection prevention (parameterized
queries) and hashed passwords (Werkzeug's PBKDF2-based hasher).

Run:
    pip install -r requirements.txt
    mysql -u root -p < schema.sql
    python app.py
Then visit http://127.0.0.1:5000/
"""

import re
import mysql.connector
from mysql.connector import Error
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "CHANGE_ME_TO_A_RANDOM_SECRET_IN_PRODUCTION"  # needed for session cookies

# ---------------------------------------------------------------------------
# Database configuration - edit these to match your local MySQL setup
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "JBhirbod@1380!",          # <-- put your MySQL root password here
    "database": "comp440_p1",
}


def get_db_connection():
    """Open a new connection to the MySQL database."""
    return mysql.connector.connect(**DB_CONFIG)


# ---------------------------------------------------------------------------
# Simple server-side validation helpers
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\-\s()]{7,20}$")


def is_valid_username(username):
    return bool(re.match(r"^[A-Za-z0-9_]{3,50}$", username or ""))


def is_valid_email(email):
    return bool(EMAIL_RE.match(email or ""))


def is_valid_phone(phone):
    return bool(PHONE_RE.match(phone or ""))


def password_requirement_errors(password):
    """Return a list of unmet password requirements (empty list = all met).
    Kept in sync with the live checklist shown on the registration page."""
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password)):
        errors.append("Password must include both upper and lowercase letters.")
    if not re.search(r"[0-9]", password):
        errors.append("Password must include at least one number.")
    return errors


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    form_data = {"username": "", "first_name": "", "last_name": "", "email": "", "phone": ""}
    errors = {}

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        # Repopulate everything except the password fields — those are
        # never sent back to the browser, even on a failed submission.
        form_data = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
        }

        # ---- Basic input validation — collect ALL errors, not just the first ----
        if not is_valid_username(username):
            errors["username"] = "Username must be 3-50 characters (letters, numbers, underscore)."
        if not first_name:
            errors["first_name"] = "First name is required."
        if not last_name:
            errors["last_name"] = "Last name is required."
        if not is_valid_email(email):
            errors["email"] = "Please enter a valid email address."
        if not is_valid_phone(phone):
            errors["phone"] = "Please enter a valid phone number."

        pw_errors = password_requirement_errors(password)
        if pw_errors:
            errors["password"] = " ".join(pw_errors)
        elif password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        # Only hit the database once the basic format checks all pass.
        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Parameterized query: user input is NEVER concatenated into SQL text.
                cursor.execute(
                    "SELECT username, email, phone FROM user "
                    "WHERE username = %s OR email = %s OR phone = %s",
                    (username, email, phone),
                )
                existing = cursor.fetchall()

                if existing:
                    for row in existing:
                        if row[0] == username:
                            errors["username"] = "That username is already taken."
                        if row[1] == email:
                            errors["email"] = "That email is already registered."
                        if row[2] == phone:
                            errors["phone"] = "That phone number is already registered."
                    cursor.close()
                else:
                    hashed_password = generate_password_hash(password)
                    cursor.execute(
                        "INSERT INTO user (username, password, firstName, lastName, email, phone) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (username, hashed_password, first_name, last_name, email, phone),
                    )
                    conn.commit()
                    cursor.close()
                    flash("Registration successful! You can now log in.")
                    return redirect(url_for("login"))

            except Error as e:
                errors["general"] = f"Database error: {e}"
            finally:
                if conn is not None and conn.is_connected():
                    conn.close()

        for message in errors.values():
            flash(message)

    return render_template("register.html", form_data=form_data, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Parameterized query — the %s placeholders are bound as data,
            # never interpreted as SQL, which defeats SQL-injection attempts
            # like  ' OR '1'='1
            cursor.execute(
                "SELECT username, password, firstName FROM user WHERE username = %s",
                (username,),
            )
            user_row = cursor.fetchone()
            cursor.close()

            if user_row and check_password_hash(user_row["password"], password):
                session["username"] = user_row["username"]
                session["first_name"] = user_row["firstName"]
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password.")
                return render_template("login.html")

        except Error as e:
            flash(f"Database error: {e}")
            return render_template("login.html")
        finally:
            if conn is not None and conn.is_connected():
                conn.close()

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("dashboard.html", username=session["username"],
                            first_name=session.get("first_name", ""))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)