# COMP 440 - Course Project: Phase 1

A Flask + MySQL app implementing user registration and login, per the
Phase 1 spec:

- `user(username, password, firstName, lastName, email, phone)` — `username`
  is the primary key; `email` and `phone` are unique.
- SQL injection is prevented by using **parameterized queries** everywhere
  (`mysql-connector-python` with `%s` placeholders) — user input is never
  concatenated into SQL strings.
- Passwords are **hashed** with Werkzeug's `generate_password_hash` /
  `check_password_hash` (PBKDF2-SHA256 with a random salt) — plaintext
  passwords are never stored.
- Sign-up detects duplicate username, email, or phone, and rejects
  mismatched password confirmation.
- The registration page shows a live, terminal-style requirements
  checklist (username format, password length/case/number, password
  match) and a password-strength meter — the same rules are enforced
  again on the server in `password_requirement_errors()`, since
  client-side checks alone can always be bypassed.
- All functionality is exposed through the web GUI (`/register`, `/login`,
  `/dashboard`) — no direct SQL execution is required to use the app.

## Setup

1. Install MySQL Server if you don't have it, and make sure it's running.
2. Create the database and table:
   ```bash
   mysql -u root -p < schema.sql
   ```
3. Install Python dependencies (Python 3.9+ recommended):
   ```bash
   pip install -r requirements.txt
   ```
4. Open `app.py` and set your MySQL password in `DB_CONFIG` (and change
   `host`/`user` if needed).
5. Run the app:
   ```bash
   python app.py
   ```
6. Visit `http://127.0.0.1:5000/` in your browser.

## How SQL injection is prevented

Every query in `app.py` uses parameter placeholders, e.g.:

```python
cursor.execute(
    "SELECT username, password, firstName FROM user WHERE username = %s",
    (username,),
)
```

The `mysql-connector-python` driver sends the query text and the parameter
value **separately** to the database, so a malicious login attempt such as

```
username: foo
password: any' OR '1'='1
```

is treated as a literal password string, not as SQL code — the classic
attack shown in the SQL Injection slides cannot succeed here. This
satisfies "Avoid the use of dynamic SQL queries" / parameterized statements
from the SQL Injection reference material for this project.

## Submission checklist (from the assignment)

- [ ] Zip/war the source into `COMP440_TeamNo_P1` (replace `TeamNo` with
      your team number).
- [ ] Record a screen + voice demo of registering a user, being blocked on
      duplicate username/email/phone and mismatched passwords, then
      logging in successfully.
- [ ] Upload the demo to YouTube and put the link in this README (or a
      separate `readme.txt`) inside the submitted project folder.

## Notes / things you may want to adjust

- `app.secret_key` is a placeholder — swap it for a real random value
  before treating this as anything beyond a class project.
- Validation regexes for email/phone are intentionally simple; tighten
  them if your instructor's test cases need something stricter.
- If you'd rather use PostgreSQL or SQLite instead of MySQL, only
  `DB_CONFIG`/`get_db_connection()` in `app.py` and the connector import
  need to change — the rest of the app is unaffected.
