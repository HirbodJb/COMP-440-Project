# COMP 440 - Course Project: Phase 1

A Flask + MySQL app implementing user registration and login, per the
Phase 1 spec:

- `user(username, password, firstName, lastName, email, phone)` — `username`
  is the primary key; `email` and `phone` are unique.
- SQL injection is prevented by using **parameterized queries** everywhere
  (`mysql-connector-python` with `%s` placeholders) — user input is never
  concatenated into SQL strings.
- Passwords are **hashed** with Werkzeug's `generate_password_hash` /
  `check_password_hash` (a salted, adaptive password hash) — plaintext
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

Each teammate must perform this setup on their own computer. Database passwords
and Flask secret keys are local environment variables and must never be added to
the source code or committed to Git.

1. Clone the repository and open a terminal in the repository directory:

   ```powershell
   cd COMP440_P1
   ```

2. Install MySQL Server if needed and make sure it is running. In MySQL
   Workbench, open `schema.sql` and execute it. Alternatively, log in from the
   terminal:

   ```powershell
   mysql -u root -p
   ```

   Then run `source schema.sql;` at the `mysql>` prompt, followed by `exit;`.

3. Install the Python dependencies (Python 3.9+ recommended):

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. On Windows, create a unique Flask secret and save both required values as
   user environment variables. Replace `YOUR_OWN_MYSQL_PASSWORD` with that
   teammate's local MySQL password:

   ```powershell
   $secret = python -c "import secrets; print(secrets.token_hex(32))"
   [Environment]::SetEnvironmentVariable("COMP440_SECRET_KEY", $secret, "User")
   [Environment]::SetEnvironmentVariable("COMP440_DB_PASSWORD", "YOUR_OWN_MYSQL_PASSWORD", "User")
   Remove-Variable secret
   ```

   Close and reopen the terminal (and VS Code) afterward. Confirm the values
   are available without displaying them:

   ```powershell
   if ($env:COMP440_SECRET_KEY -and $env:COMP440_DB_PASSWORD) { "Configuration is ready" } else { "Configuration is missing" }
   ```

   On macOS or Linux, set the values for the current terminal instead:

   ```bash
   export COMP440_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
   export COMP440_DB_PASSWORD='YOUR_OWN_MYSQL_PASSWORD'
   ```

5. If a teammate's MySQL configuration differs from the defaults, they may
   also set these optional variables:

   | Variable | Default |
   | --- | --- |
   | `COMP440_DB_HOST` | `localhost` |
   | `COMP440_DB_USER` | `root` |
   | `COMP440_DB_NAME` | `comp440_p1` |

6. Run the application:

   ```powershell
   python app.py
   ```

7. Visit `http://127.0.0.1:5000/` in a browser.

If startup reports a missing `COMP440_SECRET_KEY` or `COMP440_DB_PASSWORD`,
close and reopen the terminal and check Step 4. Never solve that error by
putting the value directly in `app.py`.

## Safe team workflow

After these changes are committed and pushed, teammates can pull or clone the
repository without receiving another teammate's current password or Flask
secret. Git does not copy local environment variables, and the application
does not contain fallback credentials.

Each teammate must:

- create their own local MySQL database by running `schema.sql`;
- set their own `COMP440_DB_PASSWORD` and a unique `COMP440_SECRET_KEY`;
- keep credentials out of source files, screenshots, chat, commits, and pull
  requests; and
- check `git status` before committing. Files named `.env` and `.env.*` are
  ignored, but they should never be force-added with `git add -f`.

Pulling code does not overwrite anyone's environment variables or copy local
database contents. The schema is non-destructive when rerun, so it will not
drop an existing `user` table. Registered accounts remain local to each
developer unless the team deliberately connects to a shared database.

For local debugging only, `COMP440_DEBUG=1` may be set temporarily. Leave it
unset for normal use and never expose Flask's development server or debugger to
the public internet.

### Previously exposed credentials

Removing a credential from the latest files does not remove it from earlier
Git commits. Any password or key that was ever committed must be considered
exposed and rotated. Do not reuse that old value anywhere. Rewriting repository
history can remove the text from future clones, but rotation is still required
because existing clones and hosting-provider caches may retain it.

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

- `COMP440_SECRET_KEY` and `COMP440_DB_PASSWORD` are intentionally not included
  in the repository. Every teammate supplies their own values during setup.
- The repository's `.gitignore` excludes `.env` files if a teammate chooses to
  use one locally in the future. Do not force-add an `.env` file to Git.
- `schema.sql` uses `CREATE TABLE IF NOT EXISTS`, so rerunning it does not erase
  existing local accounts.
- Validation regexes for email/phone are intentionally simple; tighten
  them if your instructor's test cases need something stricter.
- If you'd rather use PostgreSQL or SQLite instead of MySQL, only
  `DB_CONFIG`/`get_db_connection()` in `app.py` and the connector import
  need to change — the rest of the app is unaffected.
