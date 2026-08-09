"""COMP 440 marketplace application for Phases 1 and 2."""

import os
import re
import secrets
from datetime import date
from decimal import Decimal, InvalidOperation
from functools import wraps

import mysql.connector
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from mysql.connector import Error
from werkzeug.security import check_password_hash, generate_password_hash


# ---------------------------------------------------------------------------
# Application and environment configuration
# ---------------------------------------------------------------------------
# Required secrets intentionally have no source-code fallback. Failing fast at
# startup is safer than accidentally running with a shared password or key.
app = Flask(__name__)
app.secret_key = os.environ["COMP440_SECRET_KEY"]
app.config.update(
    # JavaScript cannot read the session cookie, and cross-site requests do not
    # receive it in the common case. CSRF tokens below provide the write guard.
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# These defaults match the local setup documented in README.md. Every teammate
# supplies their own database password through an environment variable.
DB_CONFIG = {
    "host": os.environ.get("COMP440_DB_HOST", "localhost"),
    "user": os.environ.get("COMP440_DB_USER", "root"),
    "password": os.environ["COMP440_DB_PASSWORD"],
    "database": os.environ.get("COMP440_DB_NAME", "comp440_p1"),
}

# ---------------------------------------------------------------------------
# Shared validation and display mappings
# ---------------------------------------------------------------------------
# The same limits are also represented in schema.sql. Keep these validators and
# the database column sizes aligned whenever a field definition changes.
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\-\s()]{7,20}$")
CATEGORY_RE = re.compile(r"^[a-z]+$")
RATINGS = {"1": "Poor", "2": "Fair", "3": "Good", "4": "Excellent"}
RATING_VALUES = {value: int(key) for key, value in RATINGS.items()}


def get_db_connection():
    # Routes use short-lived connections and close them in finally blocks. This
    # keeps a failed request from leaking a connection into later requests.
    return mysql.connector.connect(**DB_CONFIG)


def login_required(view):
    # Authentication is checked server-side on every protected route. Hiding a
    # button in a template is never treated as an authorization check.
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "username" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def csrf_token():
    # One unpredictable token is stored in the signed Flask session and reused
    # by forms for the duration of that session.
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


# Templates call csrf_token() directly when rendering hidden form fields.
app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def protect_post_requests():
    # All state-changing routes use POST, so a single check here protects every
    # current form and any POST route teammates add later.
    if request.method == "POST":
        submitted = request.form.get("csrf_token", "")
        expected = session.get("_csrf_token", "")
        if not expected or not secrets.compare_digest(submitted, expected):
            abort(400, description="Invalid or missing form security token.")


# ---------------------------------------------------------------------------
# Input parsing helpers
# ---------------------------------------------------------------------------
def is_valid_username(username):
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,50}", username or ""))


def is_valid_email(email):
    return bool(EMAIL_RE.fullmatch(email or ""))


def is_valid_phone(phone):
    return bool(PHONE_RE.fullmatch(phone or ""))


def password_requirement_errors(password):
    # Return every unmet rule at once so the registration page can give useful
    # feedback without making the user submit repeatedly.
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if not (re.search(r"[a-z]", password) and re.search(r"[A-Z]", password)):
        errors.append("Password must include both upper and lowercase letters.")
    if not re.search(r"[0-9]", password):
        errors.append("Password must include at least one number.")
    return errors


def parse_categories(raw_value):
    # The form accepts comma-separated categories. Preserve the submitted order
    # while removing duplicates, then enforce the assignment's lowercase-word
    # rule before any database work begins.
    categories = []
    for value in raw_value.split(","):
        category = value.strip()
        if category and category not in categories:
            categories.append(category)
    if not categories:
        return [], "Enter at least one category."
    if len(categories) > 10:
        return [], "An item may have at most 10 categories."
    if any(len(category) > 50 or not CATEGORY_RE.fullmatch(category) for category in categories):
        return [], "Categories must be lowercase single words separated by commas."
    return categories, None


def parse_price(raw_value):
    # Decimal avoids the rounding problems that binary floating-point values
    # can introduce for money. Two decimal places match DECIMAL(10, 2) in MySQL.
    try:
        price = Decimal(raw_value).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    if price < 0 or price > Decimal("99999999.99"):
        return None
    return price


def friendly_database_message(error, fallback):
    # Database triggers are the final authority for business rules. Only expose
    # known, intentionally written rule messages; log unexpected database
    # details privately instead of leaking table or constraint information.
    message = getattr(error, "msg", str(error))
    allowed_messages = (
        "A user may post at most two items per calendar day.",
        "A user may submit at most three reviews per calendar day.",
        "A user cannot review their own item.",
        "Reviews cannot be modified after submission.",
        "Reviews cannot be deleted after submission.",
        "A seller cannot buy their own item.",
        "This item is no longer available.",
    )
    for allowed in allowed_messages:
        if allowed in message:
            return allowed
    if "uq_review_reviewer_item" in message or "Duplicate entry" in message and "review" in message:
        return "You have already reviewed this item."
    return fallback


def close_resources(cursor, connection):
    # This helper is intentionally tolerant of partially initialized routes so
    # it can be called safely from every finally block.
    if cursor is not None:
        cursor.close()
    if connection is not None and connection.is_connected():
        connection.close()


# ---------------------------------------------------------------------------
# Authentication routes
# ---------------------------------------------------------------------------
@app.route("/")
def home():
    # The root URL is only a traffic director; authenticated users go straight
    # to the marketplace and everyone else starts at login.
    return redirect(url_for("dashboard" if "username" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    # Non-sensitive fields are retained after validation errors. Passwords are
    # deliberately excluded so they are never echoed back into rendered HTML.
    form_data = {"username": "", "first_name": "", "last_name": "", "email": "", "phone": ""}
    errors = {}

    if request.method == "POST":
        # Trim identity/contact fields, but do not alter passwords: spaces may
        # be intentional password characters and must hash exactly as entered.
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        form_data = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
        }

        # Collect all local validation errors before opening a database
        # connection. This is faster and gives the user one complete response.
        if not is_valid_username(username):
            errors["username"] = "Username must be 3-50 characters (letters, numbers, underscore)."
        if not first_name:
            errors["first_name"] = "First name is required."
        elif len(first_name) > 50:
            errors["first_name"] = "First name must be 50 characters or fewer."
        if not last_name:
            errors["last_name"] = "Last name is required."
        elif len(last_name) > 50:
            errors["last_name"] = "Last name must be 50 characters or fewer."
        if len(email) > 100:
            errors["email"] = "Email must be 100 characters or fewer."
        elif not is_valid_email(email):
            errors["email"] = "Please enter a valid email address."
        if not is_valid_phone(phone):
            errors["phone"] = "Please enter a valid phone number."
        password_errors = password_requirement_errors(password)
        if password_errors:
            errors["password"] = " ".join(password_errors)
        elif password != confirm_password:
            errors["confirm_password"] = "Passwords do not match."

        connection = cursor = None
        if not errors:
            try:
                connection = get_db_connection()
                cursor = connection.cursor()
                # MySQL's text collation is case-insensitive. The Python
                # comparisons mirror that behavior so TestUser and testuser
                # produce the correct field-specific duplicate message.
                cursor.execute(
                    "SELECT username, email, phone FROM user "
                    "WHERE username = %s OR email = %s OR phone = %s",
                    (username, email, phone),
                )
                existing = cursor.fetchall()
                for row in existing:
                    if row[0].casefold() == username.casefold():
                        errors["username"] = "That username is already taken."
                    if row[1].casefold() == email.casefold():
                        errors["email"] = "That email is already registered."
                    if row[2] == phone:
                        errors["phone"] = "That phone number is already registered."
                if not errors:
                    # Werkzeug generates a salted adaptive hash. Plaintext
                    # passwords are never inserted into the user table.
                    cursor.execute(
                        "INSERT INTO user (username, password, firstName, lastName, email, phone) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (username, generate_password_hash(password), first_name, last_name, email, phone),
                    )
                    connection.commit()
                    flash("Registration successful. You can now log in.", "success")
                    return redirect(url_for("login"))
            except Error:
                # Full diagnostics belong in the server log; the browser gets a
                # generic message that does not reveal database internals.
                app.logger.exception("Database error during registration")
                errors["general"] = "Unable to complete registration right now. Please try again."
            finally:
                close_resources(cursor, connection)

        for message in errors.values():
            flash(message, "error")

    return render_template("register.html", form_data=form_data, errors=errors)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(
                "SELECT username, password, firstName FROM user WHERE username = %s",
                (username,),
            )
            user_row = cursor.fetchone()
            if user_row and check_password_hash(user_row["password"], password):
                # Clearing first prevents old session state from surviving a
                # login and gives the authenticated session a fresh CSRF token.
                session.clear()
                session["username"] = user_row["username"]
                session["first_name"] = user_row["firstName"]
                csrf_token()
                return redirect(url_for("dashboard"))
            flash("Invalid username or password.", "error")
        except Error:
            app.logger.exception("Database error during login")
            flash("Unable to log in right now. Please try again.", "error")
        finally:
            close_resources(cursor, connection)
    return render_template("login.html")


# ---------------------------------------------------------------------------
# Marketplace browsing and item creation
# ---------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    sort = request.args.get("sort", "newest")
    category = request.args.get("category", "").strip()
    # ORDER BY expressions cannot be passed as normal SQL parameters. Keep this
    # strict whitelist between user-facing sort names and trusted SQL fragments;
    # never place the raw query-string value directly into the SQL statement.
    sort_options = {
        "newest": "i.datePosted DESC, i.itemId DESC",
        "oldest": "i.datePosted ASC, i.itemId ASC",
        "price_low": "i.price ASC, i.itemId DESC",
        "price_high": "i.price DESC, i.itemId DESC",
        "likes": "likeCount DESC, i.itemId DESC",
        "likes_low": "likeCount ASC, i.itemId DESC",
        "rating": "averageRating DESC, reviewCount DESC, i.itemId DESC",
        "rating_low": "CASE WHEN reviewCount = 0 THEN 1 ELSE 0 END, averageRating ASC, i.itemId DESC",
        "reviews": "reviewCount DESC, averageRating DESC, i.itemId DESC",
        "reviews_low": "reviewCount ASC, i.itemId DESC",
    }
    if sort not in sort_options:
        sort = "newest"

    # Sold and taken-down listings remain available to their owners for record
    # keeping, but only active listings belong in the public For You feed.
    where = "WHERE i.status = 'active'"
    params = []
    if category:
        where += (
            " AND EXISTS (SELECT 1 FROM item_category filter_ic "
            "WHERE filter_ic.itemId = i.itemId AND filter_ic.categoryName = %s)"
        )
        params.append(category)

    # Category, review, and like summaries are aggregated in separate derived
    # tables. This prevents the many-to-many joins from multiplying counts.
    sql = f"""
        SELECT i.itemId, i.title, i.description, i.price, i.datePosted,
               i.seller, i.status, COALESCE(c.categories, '') AS categories,
               COALESCE(rv.reviewCount, 0) AS reviewCount,
               COALESCE(rv.averageRating, 0) AS averageRating,
               COALESCE(lk.likeCount, 0) AS likeCount
        FROM item i
        LEFT JOIN (
            SELECT itemId, GROUP_CONCAT(categoryName ORDER BY categoryName SEPARATOR ', ') AS categories
            FROM item_category GROUP BY itemId
        ) c ON c.itemId = i.itemId
        LEFT JOIN (
            SELECT itemId, COUNT(*) AS reviewCount,
                   AVG(CASE rating WHEN 'Poor' THEN 1 WHEN 'Fair' THEN 2
                       WHEN 'Good' THEN 3 WHEN 'Excellent' THEN 4 END) AS averageRating
            FROM review GROUP BY itemId
        ) rv ON rv.itemId = i.itemId
        LEFT JOIN (
            SELECT itemId, COUNT(*) AS likeCount FROM item_like GROUP BY itemId
        ) lk ON lk.itemId = i.itemId
        {where}
        ORDER BY {sort_options[sort]}
    """

    connection = cursor = None
    items = categories = []
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(sql, tuple(params))
        items = cursor.fetchall()
        cursor.execute("SELECT categoryName FROM category ORDER BY categoryName")
        # Populate the filter from real database categories instead of keeping a
        # second hard-coded list that teammates would need to maintain.
        categories = [row["categoryName"] for row in cursor.fetchall()]
    except Error:
        app.logger.exception("Database error loading marketplace")
        flash("Unable to load the marketplace right now.", "error")
    finally:
        close_resources(cursor, connection)
    return render_template(
        "dashboard.html", items=items, categories=categories,
        selected_category=category, selected_sort=sort,
    )


@app.route("/items/new", methods=["GET", "POST"])
@login_required
def create_item():
    form_data = {"title": "", "description": "", "price": "", "categories": ""}
    if request.method == "POST":
        form_data = {key: request.form.get(key, "").strip() for key in form_data}
        categories, category_error = parse_categories(form_data["categories"])
        price = parse_price(form_data["price"])
        errors = []
        if not form_data["title"] or len(form_data["title"]) > 120:
            errors.append("Title is required and must be 120 characters or fewer.")
        if not form_data["description"] or len(form_data["description"]) > 5000:
            errors.append("Description is required and must be 5,000 characters or fewer.")
        if price is None:
            errors.append("Enter a valid non-negative price.")
        if category_error:
            errors.append(category_error)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("item_form.html", form_data=form_data)

        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            # The database trigger enforces the two-posts-per-day rule even if a
            # future client bypasses this form. datePosted is also normalized by
            # that trigger to the database server's current calendar date.
            cursor.execute(
                "INSERT INTO item (title, description, datePosted, price, seller) "
                "VALUES (%s, %s, %s, %s, %s)",
                (form_data["title"], form_data["description"], date.today(), price, session["username"]),
            )
            item_id = cursor.lastrowid
            # Item and category rows are committed together. If any category
            # assignment fails, the exception handler rolls back the whole item
            # so the one-or-more-categories rule cannot be left half-complete.
            for category_name in categories:
                cursor.execute("INSERT IGNORE INTO category (categoryName) VALUES (%s)", (category_name,))
                cursor.execute(
                    "INSERT INTO item_category (itemId, categoryName) VALUES (%s, %s)",
                    (item_id, category_name),
                )
            connection.commit()
            flash("Item posted successfully.", "success")
            return redirect(url_for("item_detail", item_id=item_id))
        except Error as error:
            if connection:
                connection.rollback()
            app.logger.exception("Database error creating item")
            flash(friendly_database_message(error, "Unable to post the item right now."), "error")
        finally:
            close_resources(cursor, connection)
    return render_template("item_form.html", form_data=form_data)


# ---------------------------------------------------------------------------
# Item details and community interactions
# ---------------------------------------------------------------------------
@app.route("/items/<int:item_id>")
@login_required
def item_detail(item_id):
    connection = cursor = None
    item = None
    reviews = []
    user_liked = False
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT i.*, COALESCE(c.categories, '') AS categories,
                   COALESCE(rv.reviewCount, 0) AS reviewCount,
                   COALESCE(rv.averageRating, 0) AS averageRating,
                   COALESCE(lk.likeCount, 0) AS likeCount
            FROM item i
            LEFT JOIN (SELECT itemId, GROUP_CONCAT(categoryName ORDER BY categoryName SEPARATOR ', ') categories
                       FROM item_category GROUP BY itemId) c ON c.itemId = i.itemId
            LEFT JOIN (SELECT itemId, COUNT(*) reviewCount,
                              AVG(CASE rating WHEN 'Poor' THEN 1 WHEN 'Fair' THEN 2
                                  WHEN 'Good' THEN 3 WHEN 'Excellent' THEN 4 END) averageRating
                       FROM review GROUP BY itemId) rv ON rv.itemId = i.itemId
            LEFT JOIN (SELECT itemId, COUNT(*) likeCount FROM item_like GROUP BY itemId) lk
                       ON lk.itemId = i.itemId
            WHERE i.itemId = %s
            """,
            (item_id,),
        )
        item = cursor.fetchone()
        if not item:
            abort(404)
        # A removed listing is private to its seller. Keeping its row lets us
        # preserve purchase history without leaving a public product page.
        if item["status"] == "removed" and item["seller"] != session["username"]:
            abort(404)
        cursor.execute(
            "SELECT reviewer, rating, comment, reviewDate FROM review "
            "WHERE itemId = %s ORDER BY reviewDate DESC, reviewId DESC",
            (item_id,),
        )
        reviews = cursor.fetchall()
        # Reviews store the assignment's text labels; the template needs the
        # reverse mapping to render the corresponding 1-4 star display.
        for review in reviews:
            review["stars"] = RATING_VALUES[review["rating"]]
        cursor.execute(
            "SELECT 1 FROM item_like WHERE itemId = %s AND username = %s",
            (item_id, session["username"]),
        )
        user_liked = cursor.fetchone() is not None
    except Error:
        app.logger.exception("Database error loading item")
        flash("Unable to load this item right now.", "error")
        return redirect(url_for("dashboard"))
    finally:
        close_resources(cursor, connection)
    return render_template("item_detail.html", item=item, reviews=reviews, user_liked=user_liked)


@app.route("/items/<int:item_id>/review", methods=["POST"])
@login_required
def add_review(item_id):
    # The browser submits a star number, while MySQL stores the required rating
    # words: Poor, Fair, Good, or Excellent.
    rating = RATINGS.get(request.form.get("rating", ""))
    comment = request.form.get("comment", "").strip()
    if not rating:
        flash("Choose a rating from 1 to 4 stars.", "error")
        return redirect(url_for("item_detail", item_id=item_id))
    if not comment or len(comment) > 500:
        flash("Review comments are required and must be 500 characters or fewer.", "error")
        return redirect(url_for("item_detail", item_id=item_id))

    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "INSERT INTO review (itemId, reviewer, rating, comment, reviewDate) "
            "VALUES (%s, %s, %s, %s, %s)",
            (item_id, session["username"], rating, comment, date.today()),
        )
        connection.commit()
        flash("Review submitted. Reviews cannot be edited after submission.", "success")
    except Error as error:
        # MySQL enforces self-review, one-review-per-item, and three-per-day
        # rules. Keeping those rules in the database protects every client.
        if connection:
            connection.rollback()
        app.logger.exception("Database error creating review")
        flash(friendly_database_message(error, "Unable to submit this review."), "error")
    finally:
        close_resources(cursor, connection)
    return redirect(url_for("item_detail", item_id=item_id))


@app.route("/items/<int:item_id>/like", methods=["POST"])
@login_required
def toggle_like(item_id):
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "DELETE FROM item_like WHERE itemId = %s AND username = %s",
            (item_id, session["username"]),
        )
        # Delete-first makes this one endpoint act as like/unlike. The composite
        # primary key still guarantees at most one like per user and item.
        if cursor.rowcount == 0:
            cursor.execute(
                "INSERT INTO item_like (itemId, username) VALUES (%s, %s)",
                (item_id, session["username"]),
            )
        connection.commit()
    except Error:
        if connection:
            connection.rollback()
        app.logger.exception("Database error toggling like")
        flash("Unable to update your like right now.", "error")
    finally:
        close_resources(cursor, connection)
    return redirect(request.referrer or url_for("item_detail", item_id=item_id))


@app.route("/items/<int:item_id>/buy", methods=["POST"])
@login_required
def buy_item(item_id):
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        # Lock the listing until this transaction finishes so two buyers cannot
        # both observe it as active and purchase it at the same time.
        cursor.execute("SELECT seller, price, status FROM item WHERE itemId = %s FOR UPDATE", (item_id,))
        item = cursor.fetchone()
        if not item:
            abort(404)
        if item["seller"] == session["username"]:
            flash("You cannot buy your own item.", "error")
            return redirect(url_for("item_detail", item_id=item_id))
        if item["status"] != "active":
            flash("This item is no longer available.", "error")
            return redirect(url_for("item_detail", item_id=item_id))
        cursor.execute(
            "INSERT INTO purchase (itemId, buyer, seller, pricePaid) VALUES (%s, %s, %s, %s)",
            (item_id, session["username"], item["seller"], item["price"]),
        )
        # Purchase creation and the sold status update are one transaction. They
        # either both commit or both roll back.
        cursor.execute("UPDATE item SET status = 'sold' WHERE itemId = %s", (item_id,))
        connection.commit()
        flash("Purchase completed.", "success")
    except Error as error:
        if connection:
            connection.rollback()
        app.logger.exception("Database error buying item")
        flash(friendly_database_message(error, "Unable to complete this purchase."), "error")
    finally:
        close_resources(cursor, connection)
    return redirect(url_for("item_detail", item_id=item_id))


# ---------------------------------------------------------------------------
# Seller listing management
# ---------------------------------------------------------------------------
@app.route("/my-items")
@login_required
def my_items():
    connection = cursor = None
    items = []
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        # Purchase data is joined here so sellers can distinguish active, sold,
        # and sold-then-taken-down listings without exposing buyer details in
        # the public feed.
        cursor.execute(
            """
            SELECT i.*, COALESCE(c.categories, '') categories,
                   (SELECT COUNT(*) FROM review r WHERE r.itemId = i.itemId) reviewCount,
                   p.buyer, p.purchaseDate
            FROM item i
            LEFT JOIN (SELECT itemId, GROUP_CONCAT(categoryName ORDER BY categoryName SEPARATOR ', ') categories
                       FROM item_category GROUP BY itemId) c ON c.itemId = i.itemId
            LEFT JOIN purchase p ON p.itemId = i.itemId
            WHERE i.seller = %s ORDER BY i.datePosted DESC, i.itemId DESC
            """,
            (session["username"],),
        )
        items = cursor.fetchall()
    except Error:
        app.logger.exception("Database error loading owned items")
        flash("Unable to load your listings.", "error")
    finally:
        close_resources(cursor, connection)
    return render_template("my_items.html", items=items)


@app.route("/items/<int:item_id>/price", methods=["POST"])
@login_required
def update_price(item_id):
    price = parse_price(request.form.get("price", ""))
    if price is None:
        flash("Enter a valid non-negative price.", "error")
        return redirect(url_for("my_items"))
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        # Put ownership and active-status checks in the UPDATE itself. A forged
        # item ID therefore cannot modify another seller's listing.
        cursor.execute(
            "UPDATE item SET price = %s WHERE itemId = %s AND seller = %s AND status = 'active'",
            (price, item_id, session["username"]),
        )
        connection.commit()
        flash("Price updated." if cursor.rowcount else "Only your active items can be updated.",
              "success" if cursor.rowcount else "error")
    except Error:
        if connection:
            connection.rollback()
        app.logger.exception("Database error updating price")
        flash("Unable to update the price.", "error")
    finally:
        close_resources(cursor, connection)
    return redirect(url_for("my_items"))


@app.route("/items/<int:item_id>/remove", methods=["POST"])
@login_required
def remove_listing(item_id):
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        # Lock while deciding between deletion and archival so a purchase cannot
        # race with a seller taking down the same listing.
        cursor.execute(
            "SELECT i.status, EXISTS(SELECT 1 FROM purchase p WHERE p.itemId = i.itemId) AS wasSold "
            "FROM item i WHERE i.itemId = %s AND i.seller = %s FOR UPDATE",
            (item_id, session["username"]),
        )
        item = cursor.fetchone()
        if not item:
            flash("You can remove only your own listings.", "error")
        elif item["status"] == "removed":
            flash("This listing has already been taken down.", "error")
        elif item["wasSold"] or item["status"] == "sold":
            # Preserve the purchase and sale history, but hide the listing from
            # the marketplace. The seller can still see its sold record here.
            cursor.execute(
                "UPDATE item SET status = 'removed' WHERE itemId = %s AND seller = %s",
                (item_id, session["username"]),
            )
            connection.commit()
            flash("Sold listing taken down. Its purchase record was preserved.", "success")
        else:
            # Unsold listings have no purchase record to preserve, so this is a
            # real deletion as required by the item-management specification.
            cursor.execute(
                "DELETE FROM item WHERE itemId = %s AND seller = %s",
                (item_id, session["username"]),
            )
            connection.commit()
            flash("Listing removed.", "success")
    except Error:
        if connection:
            connection.rollback()
        app.logger.exception("Database error removing listing")
        flash("Unable to remove this listing.", "error")
    finally:
        close_resources(cursor, connection)
    return redirect(url_for("my_items"))


@app.route("/items/<int:item_id>/categories/add", methods=["POST"])
@login_required
def add_category(item_id):
    category_name = request.form.get("category", "").strip()
    if len(category_name) > 50 or not CATEGORY_RE.fullmatch(category_name):
        flash("A category must be one lowercase word.", "error")
        return redirect(url_for("my_items"))
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        # Verify ownership server-side before creating either relationship row.
        cursor.execute("SELECT 1 FROM item WHERE itemId = %s AND seller = %s", (item_id, session["username"]))
        if not cursor.fetchone():
            flash("You can change categories only on your own items.", "error")
        else:
            # Categories are shared dictionary values. INSERT IGNORE reuses an
            # existing category and makes repeat submissions harmless.
            cursor.execute("INSERT IGNORE INTO category (categoryName) VALUES (%s)", (category_name,))
            cursor.execute(
                "INSERT IGNORE INTO item_category (itemId, categoryName) VALUES (%s, %s)",
                (item_id, category_name),
            )
            connection.commit()
            flash("Category assigned.", "success")
    except Error:
        if connection:
            connection.rollback()
        app.logger.exception("Database error assigning category")
        flash("Unable to assign that category.", "error")
    finally:
        close_resources(cursor, connection)
    return redirect(url_for("my_items"))


@app.route("/items/<int:item_id>/categories/remove", methods=["POST"])
@login_required
def remove_category(item_id):
    category_name = request.form.get("category", "").strip()
    connection = cursor = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM item_category ic JOIN item i ON i.itemId = ic.itemId "
            "WHERE ic.itemId = %s AND i.seller = %s",
            (item_id, session["username"]),
        )
        category_count = cursor.fetchone()[0]
        # The assignment requires at least one category per item, so the final
        # relationship is never removable through the application.
        if category_count <= 1:
            flash("Every item must keep at least one category.", "error")
        else:
            cursor.execute(
                "DELETE ic FROM item_category ic JOIN item i ON i.itemId = ic.itemId "
                "WHERE ic.itemId = %s AND ic.categoryName = %s AND i.seller = %s",
                (item_id, category_name, session["username"]),
            )
            connection.commit()
            flash("Category removed." if cursor.rowcount else "Category was not assigned to this item.",
                  "success" if cursor.rowcount else "error")
    except Error:
        if connection:
            connection.rollback()
        app.logger.exception("Database error removing category")
        flash("Unable to remove that category.", "error")
    finally:
        close_resources(cursor, connection)
    return redirect(url_for("my_items"))


# ---------------------------------------------------------------------------
# Required advanced SQL reports
# ---------------------------------------------------------------------------
@app.route("/reports")
@login_required
def reports():
    report = request.args.get("report", "")
    category_x = request.args.get("category_x", "").strip()
    category_y = request.args.get("category_y", "").strip()
    seller = request.args.get("seller", "").strip()
    selected_date = request.args.get("date", "").strip()
    rows = []
    columns = []
    title = ""
    # Each registry entry contains: page title, ordered result columns, SQL, and
    # bound parameters. Keeping the six assignment queries together makes them
    # easy to compare with the specification and demo one by one.
    queries = {
        # Query 1: NOT EXISTS retains every tie at the category's maximum price.
        "1": (
            "Most expensive item(s) in every category",
            ["categoryName", "itemId", "title", "price", "seller"],
            """
            SELECT ic.categoryName, i.itemId, i.title, i.price, i.seller
            FROM item i JOIN item_category ic ON ic.itemId = i.itemId
            WHERE NOT EXISTS (
                SELECT 1 FROM item i2 JOIN item_category ic2 ON ic2.itemId = i2.itemId
                WHERE ic2.categoryName = ic.categoryName AND i2.price > i.price
            )
            ORDER BY ic.categoryName, i.itemId
            """,
            (),
        ),
        # Query 2: self-join items by seller/date and require different item IDs.
        "2": (
            "Users who posted two items on the same day in categories X and Y",
            ["username", "datePosted", "itemX", "titleX", "itemY", "titleY"],
            """
            SELECT DISTINCT ix.seller AS username, ix.datePosted,
                   ix.itemId AS itemX, ix.title AS titleX,
                   iy.itemId AS itemY, iy.title AS titleY
            FROM item ix
            JOIN item_category cx ON cx.itemId = ix.itemId AND cx.categoryName = %s
            JOIN item iy ON iy.seller = ix.seller AND iy.datePosted = ix.datePosted
                        AND iy.itemId <> ix.itemId
            JOIN item_category cy ON cy.itemId = iy.itemId AND cy.categoryName = %s
            ORDER BY ix.seller, ix.datePosted
            """,
            (category_x, category_y),
        ),
        # Query 3: require at least one review, then reject any Fair/Poor review.
        "3": (
            "Reviewed items by a user whose reviews are all Excellent or Good",
            ["itemId", "title", "seller", "reviewCount"],
            """
            SELECT i.itemId, i.title, i.seller,
                   (SELECT COUNT(*) FROM review r WHERE r.itemId = i.itemId) AS reviewCount
            FROM item i
            WHERE i.seller = %s
              AND EXISTS (SELECT 1 FROM review r WHERE r.itemId = i.itemId)
              AND NOT EXISTS (SELECT 1 FROM review r WHERE r.itemId = i.itemId
                              AND r.rating NOT IN ('Excellent', 'Good'))
            ORDER BY i.itemId
            """,
            (seller,),
        ),
        # Query 4: calculate per-user counts once, then return every maximum tie.
        "4": (
            "User(s) who posted the most items on a selected date",
            ["username", "itemCount"],
            """
            WITH counts AS (
                SELECT seller AS username, COUNT(*) AS itemCount
                FROM item WHERE datePosted = %s GROUP BY seller
            )
            SELECT username, itemCount FROM counts
            WHERE itemCount = (SELECT MAX(itemCount) FROM counts)
            ORDER BY username
            """,
            (selected_date,),
        ),
        # Query 5: require review activity and exclude any non-Poor rating.
        "5": (
            "Users whose submitted reviews are all Poor",
            ["username", "reviewCount"],
            """
            SELECT u.username, (SELECT COUNT(*) FROM review r WHERE r.reviewer = u.username) reviewCount
            FROM user u
            WHERE EXISTS (SELECT 1 FROM review r WHERE r.reviewer = u.username)
              AND NOT EXISTS (SELECT 1 FROM review r WHERE r.reviewer = u.username AND r.rating <> 'Poor')
            ORDER BY u.username
            """,
            (),
        ),
        # Query 6: require at least one posted item and exclude sellers with any
        # Poor review. Items with no reviews naturally pass the NOT EXISTS test.
        "6": (
            "Users whose posted items have never received a Poor review",
            ["username", "itemCount"],
            """
            SELECT u.username, (SELECT COUNT(*) FROM item i WHERE i.seller = u.username) itemCount
            FROM user u
            WHERE EXISTS (SELECT 1 FROM item i WHERE i.seller = u.username)
              AND NOT EXISTS (
                  SELECT 1 FROM item i JOIN review r ON r.itemId = i.itemId
                  WHERE i.seller = u.username AND r.rating = 'Poor'
              )
            ORDER BY u.username
            """,
            (),
        ),
    }

    # Validate report-specific inputs before opening a database connection.
    should_run = report in queries
    if report == "2" and (not CATEGORY_RE.fullmatch(category_x) or not CATEGORY_RE.fullmatch(category_y)):
        should_run = False
        flash("Enter both categories as lowercase single words.", "error")
    if report == "3" and not seller:
        should_run = False
        flash("Enter a username.", "error")
    if report == "4":
        try:
            date.fromisoformat(selected_date)
        except ValueError:
            should_run = False
            flash("Enter a valid date.", "error")

    if should_run:
        # SQL and column names come only from the trusted registry above. User
        # inputs remain bound parameters inside each query.
        title, columns, sql, params = queries[report]
        connection = cursor = None
        try:
            connection = get_db_connection()
            cursor = connection.cursor(dictionary=True)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        except Error:
            app.logger.exception("Database error running report %s", report)
            flash("Unable to run that report.", "error")
        finally:
            close_resources(cursor, connection)
    return render_template(
        "reports.html", report=report, rows=rows, columns=columns, title=title,
        category_x=category_x, category_y=category_y, seller=seller, selected_date=selected_date,
    )


@app.route("/logout", methods=["POST"])
def logout():
    # Logout is POST-only so the global CSRF guard applies; links or third-party
    # images cannot silently sign a user out.
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    # Debug mode is opt-in for local development. Never expose Flask's debugger
    # on a shared or public server.
    debug_enabled = os.environ.get("COMP440_DEBUG", "").lower() in {"1", "true", "yes"}
    app.run(debug=debug_enabled)
