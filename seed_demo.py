"""Create a repeatable Circuit Market demo dataset.

Usage:
    python seed_demo.py
    python seed_demo.py --reset

The --reset option removes only the exact demo accounts listed below and then
recreates the dataset. Never use these public demo credentials outside local
testing.
"""

import sys
from datetime import date

from werkzeug.security import generate_password_hash

from app import get_db_connection


DEMO_PASSWORD = "DemoPass1!"
DEMO_USERS = (
    ("demo_alex", "Alex", "Rivera", "demo.alex@example.com", "555-010-1001"),
    ("demo_blair", "Blair", "Morgan", "demo.blair@example.com", "555-010-1002"),
    ("demo_casey", "Casey", "Patel", "demo.casey@example.com", "555-010-1003"),
    ("demo_drew", "Drew", "Kim", "demo.drew@example.com", "555-010-1004"),
    ("demo_erin", "Erin", "Lopez", "demo.erin@example.com", "555-010-1005"),
    ("demo_finn", "Finn", "Brooks", "demo.finn@example.com", "555-010-1006"),
    ("demo_gale", "Gale", "Nguyen", "demo.gale@example.com", "555-010-1007"),
    ("demo_harper", "Harper", "Singh", "demo.harper@example.com", "555-010-1008"),
    ("demo_jordan", "Jordan", "Lee", "demo.jordan@example.com", "555-010-1009"),
    ("demo_kai", "Kai", "Martinez", "demo.kai@example.com", "555-010-1010"),
    ("demo_logan", "Logan", "Chen", "demo.logan@example.com", "555-010-1011"),
    ("demo_morgan", "Morgan", "Davis", "demo.morgan@example.com", "555-010-1012"),
    ("demo_noel", "Noel", "Wilson", "demo.noel@example.com", "555-010-1013"),
    ("demo_parker", "Parker", "Shah", "demo.parker@example.com", "555-010-1014"),
    ("demo_quinn", "Quinn", "Brown", "demo.quinn@example.com", "555-010-1015"),
    ("demo_riley", "Riley", "Garcia", "demo.riley@example.com", "555-010-1016"),
    ("demo_skyler", "Skyler", "Johnson", "demo.skyler@example.com", "555-010-1017"),
    ("demo_taylor", "Taylor", "Anderson", "demo.taylor@example.com", "555-010-1018"),
)

DEMO_ITEMS = (
    ("alex_keyboard", "demo_alex", "Mechanical Keyboard", "Hot-swappable mechanical keyboard with tactile switches and RGB backlighting.", "129.99", ("keyboards", "gaming")),
    ("alex_monitor", "demo_alex", "4K Productivity Monitor", "A sharp 27-inch 4K IPS monitor with USB-C input and an adjustable stand.", "399.99", ("monitors", "electronics")),
    ("blair_mouse", "demo_blair", "Wireless Gaming Mouse", "Lightweight wireless mouse with programmable buttons and a precise optical sensor.", "59.99", ("mice", "gaming")),
    ("blair_cable", "demo_blair", "Braided USB-C Cable", "Durable two-meter charging and data cable rated for 100W power delivery.", "19.99", ("cables", "electronics")),
    ("casey_laptop", "demo_casey", "Developer Laptop", "Portable laptop with 16 GB RAM, a 1 TB SSD, and a high-resolution display.", "999.99", ("laptops", "electronics")),
    ("casey_monitor", "demo_casey", "Portable Monitor", "Slim 15-inch portable display powered over USB-C for travel and remote work.", "249.99", ("monitors", "electronics")),
    ("drew_keyboard", "demo_drew", "Wireless Compact Keyboard", "Compact multi-device keyboard with quiet switches and long battery life.", "129.99", ("keyboards", "gaming")),
    ("drew_dock", "demo_drew", "Thunderbolt Dock", "Desktop dock with display outputs, Ethernet, card reader, and fast USB ports.", "199.99", ("docks", "electronics")),
    ("jordan_keyboard", "demo_jordan", "Ergonomic Split Keyboard", "A comfortable split keyboard with tenting feet and programmable shortcut keys.", "89.99", ("keyboards", "office")),
    ("jordan_monitor", "demo_jordan", "34-inch Ultrawide Monitor", "Curved ultrawide display with a high refresh rate and generous desktop space.", "549.99", ("monitors", "electronics")),
    ("kai_headphones", "demo_kai", "Noise-Canceling Headphones", "Wireless over-ear headphones with active noise cancellation and long battery life.", "199.99", ("audio", "electronics")),
    ("kai_webcam", "demo_kai", "4K USB Webcam", "Sharp 4K webcam with autofocus, dual microphones, and a privacy cover.", "79.99", ("webcams", "accessories")),
    ("logan_minipc", "demo_logan", "Compact Mini PC", "Small desktop computer with 16 GB RAM, Wi-Fi 6, and quiet cooling.", "649.99", ("computers", "electronics")),
    ("logan_ssd", "demo_logan", "2 TB External SSD", "Pocket-sized high-speed solid-state drive with USB-C connectivity.", "119.99", ("storage", "electronics")),
    ("morgan_stand", "demo_morgan", "Aluminum Laptop Stand", "Adjustable ventilated stand that raises a laptop to a comfortable viewing height.", "49.99", ("accessories", "office")),
    ("morgan_numpad", "demo_morgan", "Mechanical Number Pad", "Wireless mechanical numpad with hot-swappable switches and macro support.", "69.99", ("keyboards", "accessories")),
    ("noel_router", "demo_noel", "Wi-Fi 6 Mesh Router", "Fast dual-band mesh router with broad coverage and straightforward setup.", "159.99", ("networking", "electronics")),
    ("noel_cable", "demo_noel", "Cat 6 Ethernet Cable", "Ten-meter shielded network cable suitable for gigabit connections.", "14.99", ("cables", "networking")),
    ("parker_laptop", "demo_parker", "High-Performance Gaming Laptop", "Powerful gaming laptop with dedicated graphics and a 165 Hz display.", "1499.99", ("laptops", "gaming")),
    ("parker_cooler", "demo_parker", "RGB Laptop Cooling Pad", "Quiet multi-fan cooling pad with adjustable height and lighting.", "44.99", ("accessories", "gaming")),
    ("quinn_gpu", "demo_quinn", "Performance Graphics Card", "Modern graphics card for high-resolution gaming and creative applications.", "699.99", ("components", "gaming")),
    ("quinn_psu", "demo_quinn", "850W Modular Power Supply", "Efficient fully modular desktop power supply with quiet fan operation.", "109.99", ("components", "electronics")),
    ("riley_streamdeck", "demo_riley", "Creator Control Pad", "Customizable shortcut pad for streaming, productivity, and media controls.", "139.99", ("streaming", "accessories")),
    ("riley_microphone", "demo_riley", "USB Broadcast Microphone", "Cardioid USB microphone with desk stand and headphone monitoring.", "129.99", ("audio", "streaming")),
    ("skyler_tablet", "demo_skyler", "11-inch Productivity Tablet", "Portable tablet with a bright display, quad speakers, and all-day battery.", "499.99", ("tablets", "electronics")),
    ("skyler_stylus", "demo_skyler", "Pressure-Sensitive Stylus", "Low-latency rechargeable stylus for drawing, notes, and precise editing.", "79.99", ("tablets", "accessories")),
    ("taylor_watch", "demo_taylor", "GPS Smart Watch", "Water-resistant smart watch with fitness tracking and phone notifications.", "249.99", ("wearables", "electronics")),
    ("taylor_powerbank", "demo_taylor", "20,000 mAh Power Bank", "High-capacity portable charger with USB-C fast charging and two outputs.", "59.99", ("charging", "accessories")),
)

DEMO_REVIEWS = (
    ("alex_keyboard", "demo_erin", "Excellent", "Excellent build quality and satisfying switches."),
    ("casey_laptop", "demo_erin", "Good", "Fast and reliable for development work."),
    ("drew_keyboard", "demo_erin", "Good", "Compact layout without feeling cramped."),
    ("alex_monitor", "demo_finn", "Poor", "The panel did not meet my expectations."),
    ("blair_mouse", "demo_finn", "Poor", "The shape was uncomfortable for my hand."),
    ("alex_keyboard", "demo_gale", "Good", "Great keyboard with only minor software issues."),
    ("casey_laptop", "demo_gale", "Excellent", "Excellent performance and battery life."),
    ("blair_cable", "demo_gale", "Fair", "Works correctly, but the connector feels stiff."),
    ("blair_mouse", "demo_harper", "Excellent", "Very responsive and surprisingly light."),
    ("drew_dock", "demo_harper", "Good", "All ports worked immediately on my laptop."),
    ("casey_monitor", "demo_harper", "Good", "A useful second screen for travel."),
    ("kai_headphones", "demo_jordan", "Excellent", "Comfortable headphones with impressive noise cancellation."),
    ("kai_webcam", "demo_jordan", "Good", "Clear picture and reliable autofocus."),
    ("logan_minipc", "demo_jordan", "Fair", "Capable machine, although the fan is noticeable."),
    ("logan_ssd", "demo_kai", "Excellent", "Transfers large files extremely quickly."),
    ("morgan_stand", "demo_kai", "Good", "Solid stand with useful height adjustment."),
    ("morgan_numpad", "demo_kai", "Fair", "Good switches but the wireless setup took time."),
    ("noel_router", "demo_logan", "Excellent", "Strong signal throughout my apartment."),
    ("noel_cable", "demo_logan", "Good", "Well-built cable that reaches across the room."),
    ("parker_laptop", "demo_logan", "Good", "Excellent frame rates, but it is fairly heavy."),
    ("parker_cooler", "demo_morgan", "Good", "Noticeably lowers temperatures under load."),
    ("quinn_gpu", "demo_morgan", "Excellent", "Runs modern games smoothly at high settings."),
    ("quinn_psu", "demo_morgan", "Good", "Quiet, efficient, and easy to cable-manage."),
    ("riley_streamdeck", "demo_noel", "Excellent", "Made my editing workflow much faster."),
    ("riley_microphone", "demo_noel", "Good", "Clean voice quality without extra hardware."),
    ("skyler_tablet", "demo_noel", "Fair", "Great display, but I expected faster charging."),
    ("skyler_stylus", "demo_parker", "Good", "Accurate input with almost no visible delay."),
    ("taylor_watch", "demo_parker", "Excellent", "Reliable activity tracking and GPS."),
    ("taylor_powerbank", "demo_parker", "Good", "Enough capacity for several phone charges."),
    ("jordan_keyboard", "demo_quinn", "Good", "The split layout became comfortable quickly."),
    ("jordan_monitor", "demo_quinn", "Excellent", "Fantastic screen for both work and gaming."),
    ("kai_headphones", "demo_quinn", "Poor", "The clamping force was uncomfortable for me."),
    ("logan_minipc", "demo_riley", "Good", "A surprisingly capable little workstation."),
    ("morgan_stand", "demo_riley", "Excellent", "Stable, attractive, and easy to adjust."),
    ("noel_router", "demo_riley", "Good", "Setup was simple and coverage is consistent."),
    ("parker_laptop", "demo_skyler", "Excellent", "Very fast gaming performance and a great screen."),
    ("quinn_gpu", "demo_skyler", "Good", "Strong performance with reasonable temperatures."),
    ("riley_microphone", "demo_skyler", "Fair", "Good sound, although the stand is basic."),
    ("jordan_keyboard", "demo_taylor", "Excellent", "Comfortable for long writing sessions."),
    ("logan_ssd", "demo_taylor", "Good", "Fast, compact, and easy to carry."),
    ("riley_streamdeck", "demo_taylor", "Good", "Useful buttons and simple customization."),
)

DEMO_LIKES = (
    ("alex_keyboard", "demo_blair"),
    ("alex_keyboard", "demo_casey"),
    ("alex_keyboard", "demo_erin"),
    ("alex_monitor", "demo_drew"),
    ("blair_mouse", "demo_alex"),
    ("blair_mouse", "demo_harper"),
    ("blair_cable", "demo_casey"),
    ("casey_laptop", "demo_alex"),
    ("casey_laptop", "demo_blair"),
    ("casey_laptop", "demo_drew"),
    ("casey_laptop", "demo_erin"),
    ("casey_monitor", "demo_gale"),
    ("drew_keyboard", "demo_alex"),
    ("drew_dock", "demo_casey"),
)

DEMO_PURCHASES = (
    ("blair_cable", "demo_harper"),
    ("kai_webcam", "demo_erin"),
    ("logan_ssd", "demo_alex"),
    ("morgan_stand", "demo_finn"),
    ("noel_cable", "demo_gale"),
    ("riley_microphone", "demo_casey"),
)


def placeholders(values):
    return ", ".join(["%s"] * len(values))


def clear_demo_data(cursor):
    usernames = tuple(user[0] for user in DEMO_USERS)
    user_slots = placeholders(usernames)
    cursor.execute(f"SELECT itemId FROM item WHERE seller IN ({user_slots})", usernames)
    item_ids = tuple(row[0] for row in cursor.fetchall())

    if item_ids:
        item_slots = placeholders(item_ids)
        cursor.execute(f"DELETE FROM purchase WHERE itemId IN ({item_slots})", item_ids)
        cursor.execute(f"DELETE FROM item WHERE itemId IN ({item_slots})", item_ids)

    cursor.execute(f"DELETE FROM review_submission_history WHERE reviewer IN ({user_slots})", usernames)
    cursor.execute(f"DELETE FROM item_post_history WHERE seller IN ({user_slots})", usernames)
    cursor.execute(f"DELETE FROM item_like WHERE username IN ({user_slots})", usernames)
    cursor.execute(f"DELETE FROM user WHERE username IN ({user_slots})", usernames)


def seed_demo_data(reset=False):
    connection = get_db_connection()
    cursor = connection.cursor()
    try:
        usernames = tuple(user[0] for user in DEMO_USERS)
        cursor.execute(
            f"SELECT username FROM user WHERE username IN ({placeholders(usernames)})",
            usernames,
        )
        existing = [row[0] for row in cursor.fetchall()]
        if existing and not reset:
            print("Demo data already exists. Run 'python seed_demo.py --reset' to rebuild it.")
            return
        if reset:
            clear_demo_data(cursor)

        password_hash = generate_password_hash(DEMO_PASSWORD)
        for username, first_name, last_name, email, phone in DEMO_USERS:
            cursor.execute(
                "INSERT INTO user (username, password, firstName, lastName, email, phone) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (username, password_hash, first_name, last_name, email, phone),
            )

        item_ids = {}
        for key, seller, title, description, price, categories in DEMO_ITEMS:
            cursor.execute(
                "INSERT INTO item (title, description, datePosted, price, seller) "
                "VALUES (%s, %s, %s, %s, %s)",
                (title, description, date.today(), price, seller),
            )
            item_ids[key] = cursor.lastrowid
            for category in categories:
                cursor.execute("INSERT IGNORE INTO category (categoryName) VALUES (%s)", (category,))
                cursor.execute(
                    "INSERT INTO item_category (itemId, categoryName) VALUES (%s, %s)",
                    (item_ids[key], category),
                )

        for item_key, reviewer, rating, comment in DEMO_REVIEWS:
            cursor.execute(
                "INSERT INTO review (itemId, reviewer, rating, comment, reviewDate) "
                "VALUES (%s, %s, %s, %s, %s)",
                (item_ids[item_key], reviewer, rating, comment, date.today()),
            )

        for item_key, username in DEMO_LIKES:
            cursor.execute(
                "INSERT INTO item_like (itemId, username) VALUES (%s, %s)",
                (item_ids[item_key], username),
            )

        # Give every demo account several interactions across listings they do
        # not own. INSERT IGNORE safely avoids any likes already listed above.
        item_keys = list(item_ids)
        seller_by_key = {key: seller for key, seller, *_ in DEMO_ITEMS}
        for user_index, username in enumerate(usernames):
            likes_added = 0
            offset = 1
            while likes_added < 5:
                item_key = item_keys[(user_index * 3 + offset) % len(item_keys)]
                offset += 1
                if seller_by_key[item_key] == username:
                    continue
                cursor.execute(
                    "INSERT IGNORE INTO item_like (itemId, username) VALUES (%s, %s)",
                    (item_ids[item_key], username),
                )
                likes_added += cursor.rowcount

        item_details = {key: (seller, price) for key, seller, _, _, price, _ in DEMO_ITEMS}
        for item_key, buyer in DEMO_PURCHASES:
            seller, price = item_details[item_key]
            item_id = item_ids[item_key]
            cursor.execute(
                "INSERT INTO purchase (itemId, buyer, seller, pricePaid) VALUES (%s, %s, %s, %s)",
                (item_id, buyer, seller, price),
            )
            cursor.execute("UPDATE item SET status = 'sold' WHERE itemId = %s", (item_id,))
        connection.commit()

        print("Expanded demo marketplace created successfully.")
        print(f"Users: {', '.join(usernames)}")
        print(f"Password for every demo user: {DEMO_PASSWORD}")
        print(f"Use {date.today().isoformat()} for the date-based SQL report.")
        print("Useful report inputs: categories gaming/electronics; seller demo_alex.")
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    if len(sys.argv) > 2 or (len(sys.argv) == 2 and sys.argv[1] != "--reset"):
        raise SystemExit("Usage: python seed_demo.py [--reset]")
    seed_demo_data(reset="--reset" in sys.argv)
