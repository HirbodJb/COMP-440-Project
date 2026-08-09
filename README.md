# COMP 440 Marketplace — Phases 1 and 2

Circuit Market is a Flask + MySQL electronics marketplace. Registered users can
post, browse, sort, like, buy, categorize, and review listings through the web
interface. The application also provides interfaces for all six advanced SQL
queries required in Phase 2.

## Team members

1. Carlos Bautista
2. Bachviet Nguyen
3. Hirbod Jabbarnezhad

## Individual contributions

- **Carlos Bautista:** Developed the backend application logic, connected the
  MySQL database to the web application, and updated the backend as the project
  progressed through each phase. He also recorded the demonstration videos for
  the assignment submissions.
- **Bachviet Nguyen:** Designed and created the MySQL database, then maintained
  and expanded its tables, relationships, constraints, and supporting SQL as
  the project requirements evolved across the phases.
- **Hirbod Jabbarnezhad:** Developed the user interface and frontend design,
  aligned the application screens and interactions with the assignment
  requirements, and updated the frontend for each phase of the project.

Although each member had primary areas of responsibility, the team worked
collaboratively throughout every phase. All members supported one another,
discussed challenging implementation decisions, and worked together to find and
verify solutions when problems affected more than one part of the application.

## Features

- Registration and login with salted password hashing
- Parameterized SQL queries throughout the application
- Reddit-style “For You” product feed
- Category filtering
- Sorting by date, price, likes, average rating, and review count in both
  directions
- Add an item with one or more categories
- Update an active listing's price or remove an owned listing
- Clear sold indicators and safe take-down controls that preserve purchase history
- Assign and remove categories while keeping at least one category per item
- Like or unlike listings
- Buy an available listing once
- Submit permanent 1–4 star reviews
- Seller management page
- Interfaces for all six required advanced SQL reports

## Rating scale

| Stars | Database value |
| ---: | --- |
| 1 | Poor |
| 2 | Fair |
| 3 | Good |
| 4 | Excellent |

The database stores the required text value. The interface converts it to stars
and the feed converts it to a numeric value when calculating average ratings.

## Software requirements

- Python 3.8 or newer, including `pip`
- MySQL Server 8.0 or newer
- MySQL Workbench or another MySQL client capable of executing SQL scripts
- Git for cloning and updating the repository
- A modern web browser
- The Python packages pinned in `requirements.txt`:
  Flask, MySQL Connector/Python, and Werkzeug

Each team member must have access to their own MySQL installation and know the
password for their local MySQL user. The application does not include or share
database passwords through Git.

## Installation instructions

Each teammate uses their own local MySQL database and environment variables.
Accounts and marketplace records are not shared unless the team intentionally
connects to the same hosted database.

1. Clone or pull the repository and open a terminal in its directory.

2. Install the dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Configure local secrets on Windows. Replace the password placeholder with
   that teammate's own MySQL password:

   ```powershell
   $secret = python -c "import secrets; print(secrets.token_hex(32))"
   [Environment]::SetEnvironmentVariable("COMP440_SECRET_KEY", $secret, "User")
   [Environment]::SetEnvironmentVariable("COMP440_DB_PASSWORD", "YOUR_OWN_MYSQL_PASSWORD", "User")
   Remove-Variable secret
   ```

   Close and reopen the terminal afterward. On macOS or Linux, use:

   ```bash
   export COMP440_SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
   export COMP440_DB_PASSWORD='YOUR_OWN_MYSQL_PASSWORD'
   ```

4. Prepare MySQL using one of these paths:

   - **Existing Phase 1 database:** open `migration.sql` in MySQL
     Workbench and execute the entire file once. Existing registered users are
     preserved.
   - **Fresh installation:** open `schema.sql` in MySQL Workbench and execute
     the entire file.

5. Run the application:

   ```powershell
   python app.py
   ```

6. Visit `http://127.0.0.1:5000/`.

Optional database settings:

| Variable | Default |
| --- | --- |
| `COMP440_DB_HOST` | `localhost` |
| `COMP440_DB_USER` | `root` |
| `COMP440_DB_NAME` | `comp440_p1` |

For local debugging only, set `COMP440_DEBUG=1`. Never expose Flask's
development server or debugger to the public internet.

## Phase 2 database design

| Table | Purpose |
| --- | --- |
| `user` | Registered accounts from Phase 1 |
| `item` | Marketplace listings, seller, price, date, and active/sold/removed status |
| `item_post_history` | Permanent audit count for the daily posting limit |
| `category` | Valid lowercase single-word categories |
| `item_category` | Many-to-many relationship between items and categories |
| `review` | Permanent rating and comment for an item |
| `review_submission_history` | Permanent audit count for the daily review limit |
| `item_like` | One like per user and item |
| `purchase` | The one completed purchase allowed for a listing |

## Business-rule enforcement

| Requirement | Enforcement |
| --- | --- |
| Only registered users may post, buy, or review | Login-protected Flask routes and MySQL foreign keys |
| At most two item posts per user per calendar day | MySQL trigger plus permanent `item_post_history`, so deleting a listing does not reset the count |
| Every item has one or more categories | Flask creation transaction and last-category removal guard |
| Categories are lowercase single words | Flask validation and MySQL `CHECK` constraint |
| Only the seller may update price or remove an item | Seller-qualified statements in Flask; unsold items are deleted while sold items are marked removed to preserve purchases |
| At most three reviews per user per calendar day | MySQL trigger plus permanent `review_submission_history` |
| One review per user per item | MySQL `UNIQUE (reviewer, itemId)` constraint |
| A seller cannot review their own item | MySQL `trg_review_rules` trigger |
| Rating is Poor, Fair, Good, or Excellent | MySQL `ENUM` plus Flask validation |
| Reviews cannot be modified | No edit interface plus MySQL update/delete triggers |
| An item may have zero or many reviews | Foreign-key relationship from `review` to `item` |
| A listing can be purchased only once | MySQL unique constraint on `purchase.itemId` |
| A seller cannot buy their own listing | Flask transaction and MySQL `trg_purchase_rules` trigger |

All writes involving multiple tables use a transaction. MySQL errors are logged
privately, while the browser receives a safe, useful message.

## Required advanced SQL queries

Open **SQL reports** after logging in. The application provides:

1. Every most-expensive item in each category, including price ties.
2. Users who posted two different same-day items in user-entered categories X
   and Y.
3. A specified user's reviewed items for which every rating is Good or
   Excellent.
4. Every user tied for the most item posts on a user-entered date.
5. Users who wrote one or more reviews and all their reviews are Poor.
6. Users with posted items that have never received a Poor review, including
   items with no reviews.

## Automated checks

The tests use fake database connections and do not change a teammate's MySQL
data:

```powershell
python -m unittest discover -s tests -v
```

They cover authentication protection, CSRF protection, validation, duplicate
username capitalization, rating conversion, and the required database rules
and report registrations.

## Demo data for manual testing

Populate the local marketplace with 18 users, 28 listings, many categories,
reviews, likes, and several completed purchases:

```powershell
python seed_demo.py
```

Every demo account uses the local test-only password `DemoPass1!`. The script
prints the usernames and recommended SQL-report inputs when it finishes.

To remove and recreate only this exact demo dataset:

```powershell
python seed_demo.py --reset
```

The generated data is designed to exercise price ties, same-day category
posts, Good/Excellent-only items, a tie for the top daily posters, a user whose
reviews are all Poor, sellers with no Poor reviews, likes, sold status, and all
daily-limit error messages. Do not use these public demo credentials outside a
local test database.

## Security and team workflow

- Passwords are hashed with Werkzeug and never stored as plain text.
- User input is passed through MySQL parameter placeholders rather than being
  concatenated into SQL.
- Database passwords and Flask keys come only from local environment variables.
- `.env` and `.env.*` files are ignored and must never be force-added to Git.
- Detailed database errors stay in the private server log.
- Any credential that was previously committed must remain rotated and must
  never be reused, because removing it from current files does not erase Git
  history.

## Demonstration checklist

- Register and log in through the application.
- Post two items in one day, then demonstrate that a third is rejected.
- Add multiple categories, search by category, and remove a category.
- Change the price of an owned item and delete an owned active item.
- Submit reviews and demonstrate the self-review, duplicate-review, and daily
  review restrictions.
- Demonstrate that submitted reviews cannot be edited.
- Sort the feed by likes, reviews, date, and price.
- Run all six advanced SQL reports from the SQL reports page.

Phase 1 demonstration: https://youtu.be/sclwZpTEeho
