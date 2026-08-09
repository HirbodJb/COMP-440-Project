"""Fast application tests that do not alter a developer's real MySQL data."""

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("COMP440_SECRET_KEY", "automated-test-secret")
os.environ.setdefault("COMP440_DB_PASSWORD", "automated-test-password")

# Let the test module still exercise validation and Flask routes when the MySQL
# driver has not yet been installed in the current Python environment.
try:
    import mysql.connector  # noqa: F401
except ModuleNotFoundError:
    mysql_module = types.ModuleType("mysql")
    connector_module = types.ModuleType("mysql.connector")

    class TestDatabaseError(Exception):
        pass

    connector_module.Error = TestDatabaseError
    connector_module.connect = lambda **kwargs: None
    mysql_module.connector = connector_module
    sys.modules["mysql"] = mysql_module
    sys.modules["mysql.connector"] = connector_module

import app as marketplace


# These small database doubles let route tests exercise the real application
# logic without opening a connection to a teammate's local MySQL database.
# They implement only the connector behavior that the tested routes need.
class FakeCursor:
    def __init__(self, fetchall_rows=None, fetchone_rows=None, dictionary=False):
        # Tests preload query results to reproduce a particular database state.
        self.fetchall_rows = list(fetchall_rows or [])
        self.fetchone_rows = list(fetchone_rows or [])

        # Keep a normalized history so tests can verify the SQL and parameters
        # chosen by a route without depending on whitespace or formatting.
        self.statements = []
        self.rowcount = 0
        self.lastrowid = 1
        self.dictionary = dictionary

    def execute(self, sql, params=()):
        self.statements.append((" ".join(sql.split()), params))

    def fetchall(self):
        return self.fetchall_rows

    def fetchone(self):
        # Return results in query order, just as consecutive fetchone() calls
        # against a real cursor would do.
        return self.fetchone_rows.pop(0) if self.fetchone_rows else None

    def close(self):
        pass


class FakeConnection:
    def __init__(self, cursor):
        self.test_cursor = cursor

        # Transaction flags make it possible to confirm that successful work is
        # committed and validation failures do not write anything.
        self.committed = False
        self.rolled_back = False

    def cursor(self, dictionary=False):
        self.test_cursor.dictionary = dictionary
        return self.test_cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def is_connected(self):
        return True

    def close(self):
        pass


class MarketplaceTests(unittest.TestCase):
    def setUp(self):
        # Flask's test client sends requests directly to the application, so the
        # suite does not need a running development server.
        marketplace.app.config.update(TESTING=True)
        self.client = marketplace.app.test_client()

    def set_session(self, username=None):
        # All POST routes require the same CSRF token stored in the signed Flask
        # session. Supplying a username also represents a logged-in user.
        with self.client.session_transaction() as flask_session:
            flask_session["_csrf_token"] = "test-csrf-token"
            if username:
                flask_session["username"] = username
                flask_session["first_name"] = "Test"

    def test_protected_marketplace_requires_login(self):
        # Anonymous visitors must be sent to login before viewing the market.
        response = self.client.get("/dashboard")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_post_without_csrf_token_is_rejected(self):
        # Reject form submissions that were not created from a valid session.
        response = self.client.post("/login", data={"username": "TestUser", "password": "Password1"})
        self.assertEqual(response.status_code, 400)

    def test_category_parser_requires_lowercase_single_words(self):
        # Categories are lowercase words, and repeated entries are stored once.
        categories, error = marketplace.parse_categories("keyboards, gaming, keyboards")
        self.assertEqual(categories, ["keyboards", "gaming"])
        self.assertIsNone(error)
        self.assertIsNotNone(marketplace.parse_categories("Keyboards")[1])
        self.assertIsNotNone(marketplace.parse_categories("computer parts")[1])

    def test_price_parser_rejects_negative_and_invalid_values(self):
        # Valid prices are normalized to cents; invalid or negative prices fail.
        self.assertEqual(str(marketplace.parse_price("19.9")), "19.90")
        self.assertIsNone(marketplace.parse_price("-1"))
        self.assertIsNone(marketplace.parse_price("not-a-price"))

    def test_password_policy(self):
        # Keep registration password rules covered independently of the UI.
        self.assertEqual(marketplace.password_requirement_errors("StrongPass1"), [])
        self.assertGreater(len(marketplace.password_requirement_errors("weak")), 0)

    def test_registration_reports_case_insensitive_duplicate_username(self):
        # MySQL treats the existing TestUser and submitted testuser as the same
        # username. The form should explain the conflict and preserve input.
        cursor = FakeCursor(fetchall_rows=[("TestUser", "existing@example.com", "(555) 111-2222")])
        connection = FakeConnection(cursor)
        self.set_session()
        with patch.object(marketplace, "get_db_connection", return_value=connection):
            response = self.client.post(
                "/register",
                data={
                    "csrf_token": "test-csrf-token",
                    "username": "testuser",
                    "password": "StrongPass1",
                    "confirm_password": "StrongPass1",
                    "first_name": "Test",
                    "last_name": "Person",
                    "email": "new@example.com",
                    "phone": "(555) 333-4444",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"That username is already taken.", response.data)
        self.assertIn(b'value="testuser"', response.data)
        self.assertFalse(connection.committed)

    def test_registration_rejects_oversized_fields_before_database(self):
        # Field lengths should be reported by the form before MySQL can reject
        # the row. No connection is needed when application validation fails.
        self.set_session()
        with patch.object(marketplace, "get_db_connection") as connection_factory:
            response = self.client.post(
                "/register",
                data={
                    "csrf_token": "test-csrf-token",
                    "username": "NewUser",
                    "password": "StrongPass1",
                    "confirm_password": "StrongPass1",
                    "first_name": "x" * 51,
                    "last_name": "Person",
                    "email": f"{'e' * 90}@example.com",
                    "phone": "(555) 333-4444",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"First name must be 50 characters or fewer.", response.data)
        self.assertIn(b"Email must be 100 characters or fewer.", response.data)
        connection_factory.assert_not_called()

    def test_review_maps_four_stars_to_excellent(self):
        # The interface uses numeric stars, while the database stores the four
        # assignment labels: Poor, Fair, Good, and Excellent.
        cursor = FakeCursor()
        connection = FakeConnection(cursor)
        self.set_session("Reviewer")
        with patch.object(marketplace, "get_db_connection", return_value=connection):
            response = self.client.post(
                "/items/7/review",
                data={"csrf_token": "test-csrf-token", "rating": "4", "comment": "Excellent item."},
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(connection.committed)
        insert_params = cursor.statements[0][1]
        self.assertEqual(insert_params[0:3], (7, "Reviewer", "Excellent"))

    def test_active_listing_removal_uses_delete(self):
        # An unsold listing has no purchase history to retain and may be deleted.
        cursor = FakeCursor(fetchone_rows=[{"status": "active", "wasSold": 0}])
        connection = FakeConnection(cursor)
        self.set_session("Seller")
        with patch.object(marketplace, "get_db_connection", return_value=connection):
            response = self.client.post(
                "/items/7/remove", data={"csrf_token": "test-csrf-token"}
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(connection.committed)
        self.assertTrue(any(statement.startswith("DELETE FROM item") for statement, _ in cursor.statements))

    def test_sold_listing_take_down_preserves_item_and_purchase(self):
        # A sold item must be hidden with a status update instead of deleted so
        # its purchase record and related database history remain valid.
        cursor = FakeCursor(fetchone_rows=[{"status": "sold", "wasSold": 1}])
        connection = FakeConnection(cursor)
        self.set_session("Seller")
        with patch.object(marketplace, "get_db_connection", return_value=connection):
            response = self.client.post(
                "/items/7/remove", data={"csrf_token": "test-csrf-token"}
            )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(connection.committed)
        self.assertTrue(any("SET status = 'removed'" in statement for statement, _ in cursor.statements))
        self.assertFalse(any(statement.startswith("DELETE FROM item") for statement, _ in cursor.statements))

    def test_phase_two_schema_contains_required_database_enforcement(self):
        # This is a lightweight migration guard, not a live database test. It
        # checks that schema.sql still declares the constraints and triggers
        # used to enforce the Phase 2 business rules at the database level.
        schema = (Path(__file__).parents[1] / "schema.sql").read_text(encoding="utf-8")
        required_fragments = (
            "trg_item_daily_limit",
            "item_post_history",
            "trg_review_rules",
            "review_submission_history",
            "uq_review_reviewer_item",
            "trg_review_no_update",
            "trg_review_no_delete",
            "CHECK (categoryName REGEXP '^[a-z]+$')",
            "FOREIGN KEY (seller)",
        )
        for fragment in required_fragments:
            self.assertIn(fragment, schema)

    def test_all_six_advanced_reports_are_registered(self):
        # Every required report must remain available through the application.
        # Checking the registration table catches an accidentally removed query.
        source = Path(marketplace.__file__).read_text(encoding="utf-8")
        for report_number in range(1, 7):
            self.assertIn(f'"{report_number}": (', source)


if __name__ == "__main__":
    # Allow either direct execution or unittest discovery from the project root.
    unittest.main()
