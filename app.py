"""
COMP 440 - Course Project: Phase 1
Registration + Login system with SQL-injection prevention (parameterized
queries) and salted password hashing through Werkzeug.

Run:
    pip install -r requirements.txt
    mysql -u root -p < schema.sql
    python app.py
Then visit http://127.0.0.1:5000/
"""
import os
import re
import mysql.connector
from mysql.connector import Error
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ["COMP440_SECRET_KEY"]  # needed for session cookies

# ---------------------------------------------------------------------------
# Database configuration.
# Credentials come from local environment variables so secrets never need to
# live in the repository.
# ---------------------------------------------------------------------------
DB_CONFIG = {
    "host": os.environ.get("COMP440_DB_HOST", "localhost"),
    "user": os.environ.get("COMP440_DB_USER", "root"),
    "password": os.environ["COMP440_DB_PASSWORD"],
    "database": os.environ.get("COMP440_DB_NAME", "comp440_p1"),
}


def get_db_connection():
    """Open a fresh connection to the configured MySQL database."""
    return mysql.connector.connect(**DB_CONFIG)


# ---------------------------------------------------------------------------
# Server-side validation helpers.
# These checks keep obviously invalid input out of the database layer and
# let us show helpful feedback before any write is attempted.
# ---------------------------------------------------------------------------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\-\s()]{7,20}$")


def is_valid_username(username):
    # Keep usernames simple and predictable for both users and queries.
    return bool(re.match(r"^[A-Za-z0-9_]{3,50}$", username or ""))


def is_valid_email(email):
    # This is intentionally lightweight validation, not full RFC parsing.
    return bool(EMAIL_RE.match(email or ""))


def is_valid_phone(phone):
    # Accept common phone formatting characters while rejecting junk input.
    return bool(PHONE_RE.match(phone or ""))


def password_requirement_errors(password):
    """Return the unmet password requirements, or an empty list if valid.

    This stays aligned with the checklist shown on the registration page so
    the server and the UI enforce the same baseline policy.
    """
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
    # Send authenticated users straight to the app and everyone else to login.
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    # Preserve the user's non-sensitive form input so the template can re-render
    # the page with their entries after validation fails.
    form_data = {"username": "", "first_name": "", "last_name": "", "email": "", "phone": ""}
    errors = {}

    if request.method == "POST":
        # Read and normalize each submitted field up front so validation uses
        # the same trimmed values everywhere below.
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()

        # Repopulate everything except the password fields. Passwords should not
        # be echoed back to the browser, even when validation fails.
        form_data = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
        }

        # Collect every input error in one pass so the user can fix them all at
        # once instead of discovering them one at a time.
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

        # Only hit the database after local validation has already passed.
        if not errors:
            conn = None
            try:
                conn = get_db_connection()
                cursor = conn.cursor()

                # Use parameterized SQL so user input is treated as data, not as
                # executable SQL text.
                cursor.execute(
                    "SELECT username, email, phone FROM user "
                    "WHERE username = %s OR email = %s OR phone = %s",
                    (username, email, phone),
                )
                existing = cursor.fetchall()

                # Check each returned row so we can report the exact duplicate
                # field(s) back to the user.
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
                # Surface database failures as a user-visible error instead of
                # silently failing or returning a generic page.
                errors["general"] = f"Database error: {e}"
            finally:
                # Always close the connection if it was successfully opened.
                if conn is not None and conn.is_connected():
                    conn.close()

        # Flash each validation/database message so the template can display it
        # without needing to know about the internal errors dict.
        for message in errors.values():
            flash(message)

    return render_template("register.html", form_data=form_data, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # Keep login input handling parallel with registration: trim the
        # username, but leave the password untouched.
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)

            # Parameterized query keeps the username from being interpreted as
            # SQL, which blocks injection attempts such as ' OR '1'='1.
            cursor.execute(
                "SELECT username, password, firstName FROM user WHERE username = %s",
                (username,),
            )
            user_row = cursor.fetchone()
            cursor.close()

            # Verify the stored hash instead of comparing plain text passwords.
            if user_row and check_password_hash(user_row["password"], password):
                session["username"] = user_row["username"]
                session["first_name"] = user_row["firstName"]
                return redirect(url_for("dashboard"))
            else:
                # Keep the failure message generic so we don't reveal whether
                # the username exists.
                flash("Invalid username or password.")
                return render_template("login.html")

        except Error as e:
            # Database problems should be visible to the developer and surfaced
            # to the user in a controlled way.
            flash(f"Database error: {e}")
            return render_template("login.html")
        finally:
            # Close the database connection no matter how the request ends.
            if conn is not None and conn.is_connected():
                conn.close()

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    # The dashboard is private; unauthenticated users must log in first.
    if "username" not in session:
        return redirect(url_for("login"))
    # Fall back to an empty string if the first name is missing from session.
    return render_template("dashboard.html", username=session["username"],
                            first_name=session.get("first_name", ""))


@app.route("/logout")
def logout():
    # Clear the whole session so the next request starts from a clean slate.
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    # Keep the interactive debugger off by default. A developer can opt in
    # locally with COMP440_DEBUG=1; never enable it on a shared/public server.
    debug_enabled = os.environ.get("COMP440_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(debug=debug_enabled)
