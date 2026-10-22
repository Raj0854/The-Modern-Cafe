import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sqlite3
import sys
import time
from getpass import getpass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("CAFE_DB_PATH", ROOT / "data" / "cafe.sqlite3"))
HOST = os.environ.get("CAFE_HOST", "127.0.0.1")
PORT = int(os.environ.get("CAFE_PORT", "8000"))
COOKIE_SECURE = os.environ.get("CAFE_COOKIE_SECURE", "0") == "1"
MAX_BODY = 64 * 1024
PBKDF2_ROUNDS = 310_000
ALLOWED_CATEGORIES = {"coffee", "breakfast", "desserts"}
ORDER_STATUSES = {"pending", "confirmed", "preparing", "ready", "completed", "cancelled"}
SESSIONS = {}
LOGIN_ATTEMPTS = {}

SEED_PRODUCTS = [
    ("Espresso", "A bold, rich shot of pure coffee with thick golden crema", 150, "coffee", "img/espresso.png"),
    ("Cappuccino", "Classic espresso topped with steamed milk and silky foam", 180, "coffee", "img/cappuccino.png"),
    ("Latte", "Smooth and creamy espresso with perfectly steamed milk", 200, "coffee", "img/latte.png"),
    ("Mocha", "Rich espresso blended with chocolate and whipped cream", 220, "coffee", "img/mocha.png"),
    ("Americano", "Espresso diluted with hot water for a smooth black coffee", 160, "coffee", "img/americano.png"),
    ("Flat White", "Velvety microfoam with rich espresso base", 190, "coffee", "img/flatwhite.png"),
    ("Butter Croissant", "Freshly baked flaky croissant served with butter and jam", 120, "breakfast", "img/buttercroissant.png"),
    ("Avocado Toast", "Smashed avocado on sourdough with cherry tomatoes & poached egg", 180, "breakfast", "img/avocadotoast.png"),
    ("Classic Pancakes", "Fluffy pancakes with maple syrup, fresh berries & whipped cream", 160, "breakfast", "img/pancakes.png"),
    ("Cheese Omelette", "Three-egg omelette with cheddar cheese, herbs & toast", 170, "breakfast", "img/omelette.png"),
    ("Breakfast Sandwich", "Toasted bun with egg, cheese, chicken sausage & veggies", 190, "breakfast", "img/breakfast-sandwich.png"),
    ("French Toast", "Golden French toast with cinnamon, honey & fresh fruits", 150, "breakfast", "img/french-toast.png"),
    ("Chocolate Lava Cake", "Warm molten chocolate cake with vanilla ice cream", 220, "desserts", "img/chocolate-lava-cake.png"),
    ("New York Cheesecake", "Classic creamy cheesecake with berry compote", 200, "desserts", "img/new-york-cheesecake.png"),
    ("Classic Tiramisu", "Coffee-soaked ladyfingers with mascarpone cream", 180, "desserts", "img/classictiramisu.png"),
    ("Walnut Brownie", "Fudgy chocolate brownie with walnuts & ice cream", 160, "desserts", "img/walnutbrowine.png"),
    ("Crème Brûlée", "Silky vanilla custard with caramelized sugar crust", 190, "desserts", "img/creme-brulee.png"),
    ("Warm Apple Pie", "Cinnamon-spiced apple pie served with vanilla ice cream", 170, "desserts", "img/Warm Apple Pie.png"),
]


def connect_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with connect_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL,
                price INTEGER NOT NULL CHECK(price >= 0),
                category TEXT NOT NULL CHECK(category IN ('coffee', 'breakfast', 'desserts')),
                image TEXT NOT NULL,
                stock_quantity INTEGER NOT NULL DEFAULT 100 CHECK(stock_quantity >= 0),
                available INTEGER NOT NULL DEFAULT 1 CHECK(available IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                order_number TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                customer_email TEXT NOT NULL,
                customer_phone TEXT NOT NULL,
                total INTEGER NOT NULL CHECK(total >= 0),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE RESTRICT,
                product_id INTEGER REFERENCES products(id) ON DELETE SET NULL,
                product_name TEXT NOT NULL,
                unit_price INTEGER NOT NULL CHECK(unit_price >= 0),
                quantity INTEGER NOT NULL CHECK(quantity > 0),
                line_total INTEGER NOT NULL CHECK(line_total >= 0)
            );
            CREATE TABLE IF NOT EXISTS administrators (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                password_salt BLOB NOT NULL,
                password_hash BLOB NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS order_status_history (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders(created_at);
            CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
            CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
            """
        )
        count = db.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        if count == 0:
            db.executemany(
                """INSERT INTO products
                   (name, description, price, category, image, stock_quantity, available)
                   VALUES (?, ?, ?, ?, ?, 100, 1)""",
                SEED_PRODUCTS,
            )


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return salt, digest


def set_admin_password(password):
    if len(password) < 12:
        raise ValueError("Administrator password must be at least 12 characters.")
    salt, digest = hash_password(password)
    with connect_db() as db:
        db.execute(
            """INSERT INTO administrators (id, password_salt, password_hash)
               VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
               password_salt = excluded.password_salt,
               password_hash = excluded.password_hash,
               updated_at = CURRENT_TIMESTAMP""",
            (salt, digest),
        )


def public_product(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "price": row["price"],
        "category": row["category"],
        "image": row["image"],
        "stock_quantity": row["stock_quantity"],
        "available": bool(row["available"]),
    }


class CafeHandler(BaseHTTPRequestHandler):
    server_version = "ModernCafe/1.0"

    def log_message(self, format_string, *args):
        print("%s - %s" % (self.address_string(), format_string % args))

    def _send(self, status, payload, headers=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid request body length.")
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Request body must be between 1 and 65536 bytes.")
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ValueError("Request body must be valid JSON.")
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _session(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
        except Exception:
            return None
        morsel = cookie.get("cafe_admin")
        if not morsel:
            return None
        session = SESSIONS.get(morsel.value)
        if session and session["expires"] > time.time():
            return session
        SESSIONS.pop(morsel.value, None)
        return None

    def _require_admin(self, mutation=False):
        session = self._session()
        if not session:
            self._send(401, {"error": "Administrator login required."})
            return False
        if mutation and not hmac.compare_digest(
            self.headers.get("X-CSRF-Token", ""), session["csrf"]
        ):
            self._send(403, {"error": "Invalid or missing CSRF token."})
            return False
        return True

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        try:
            if path == "/api/health":
                self._send(200, {"status": "ok"})
                return
            if path == "/api/products":
                with connect_db() as db:
                    rows = db.execute(
                        "SELECT * FROM products ORDER BY CASE category WHEN 'coffee' THEN 1 WHEN 'breakfast' THEN 2 ELSE 3 END, id"
                    ).fetchall()
                self._send(200, [public_product(row) for row in rows])
                return
            if path == "/api/admin/dashboard":
                if not self._require_admin():
                    return
                with connect_db() as db:
                    metrics = {
                        "total_orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                        "pending_orders": db.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0],
                        "total_revenue": db.execute(
                            "SELECT COALESCE(SUM(total), 0) FROM orders WHERE status != 'cancelled'"
                        ).fetchone()[0],
                        "product_count": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
                        "low_stock": db.execute(
                            "SELECT COUNT(*) FROM products WHERE stock_quantity <= 5 AND available = 1"
                        ).fetchone()[0],
                    }
                    orders = db.execute(
                        """SELECT id, order_number, customer_name, customer_email, customer_phone,
                                  total, status, created_at FROM orders ORDER BY id DESC LIMIT 100"""
                    ).fetchall()
                    products = db.execute("SELECT * FROM products ORDER BY category, id").fetchall()
                self._send(200, {
                    "metrics": metrics,
                    "orders": [dict(row) for row in orders],
                    "products": [public_product(row) for row in products],
                })
                return
            if path.startswith("/api/"):
                self._send(404, {"error": "API route not found."})
                return
            self._serve_static(path)
        except sqlite3.Error:
            print("Database operation failed.", file=sys.stderr)
            self._send(500, {"error": "A database error occurred."})

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/admin/login":
                self._admin_login()
            elif path == "/api/admin/logout":
                if not self._require_admin(mutation=True):
                    return
                cookie = SimpleCookie()
                cookie.load(self.headers.get("Cookie", ""))
                morsel = cookie.get("cafe_admin")
                if morsel:
                    SESSIONS.pop(morsel.value, None)
                self._send(200, {"ok": True}, {
                    "Set-Cookie": "cafe_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
                })
            elif path == "/api/orders":
                self._create_order()
            elif path == "/api/admin/products":
                if not self._require_admin(mutation=True):
                    return
                self._save_product(None)
            else:
                self._send(404, {"error": "API route not found."})
        except ValueError as error:
            self._send(400, {"error": str(error)})
        except sqlite3.IntegrityError:
            self._send(409, {"error": "That record conflicts with existing data."})
        except sqlite3.Error:
            print("Database operation failed.", file=sys.stderr)
            self._send(500, {"error": "A database error occurred."})

    def do_PUT(self):
        path = urlparse(self.path).path
        if path.startswith("/api/admin/") and not self._require_admin(mutation=True):
            return
        try:
            if path.startswith("/api/admin/products/"):
                product_id = self._path_id(path, "/api/admin/products/")
                self._save_product(product_id)
            elif path.startswith("/api/admin/orders/"):
                order_id = self._path_id(path, "/api/admin/orders/")
                self._update_order_status(order_id)
            else:
                self._send(404, {"error": "API route not found."})
        except ValueError as error:
            self._send(400, {"error": str(error)})
        except sqlite3.Error:
            print("Database operation failed.", file=sys.stderr)
            self._send(500, {"error": "A database error occurred."})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self._require_admin(mutation=True):
            return
        try:
            product_id = self._path_id(path, "/api/admin/products/")
            with connect_db() as db:
                cursor = db.execute(
                    "UPDATE products SET available = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (product_id,),
                )
            if cursor.rowcount == 0:
                self._send(404, {"error": "Product not found."})
            else:
                self._send(200, {"ok": True})
        except ValueError as error:
            self._send(400, {"error": str(error)})
        except sqlite3.Error:
            print("Database operation failed.", file=sys.stderr)
            self._send(500, {"error": "A database error occurred."})

    def _admin_login(self):
        ip = self.client_address[0]
        now = time.time()
        recent = [stamp for stamp in LOGIN_ATTEMPTS.get(ip, []) if now - stamp < 300]
        if len(recent) >= 10:
            self._send(429, {"error": "Too many login attempts. Try again in five minutes."})
            return
        LOGIN_ATTEMPTS[ip] = recent
        payload = self._read_json()
        password = payload.get("password")
        if not isinstance(password, str) or len(password) > 1024:
            raise ValueError("Enter a valid administrator password.")
        with connect_db() as db:
            admin = db.execute("SELECT password_salt, password_hash FROM administrators WHERE id = 1").fetchone()
        valid = False
        if admin:
            _, actual = hash_password(password, admin["password_salt"])
            valid = hmac.compare_digest(actual, admin["password_hash"])
        if not valid:
            LOGIN_ATTEMPTS[ip].append(now)
            self._send(401, {"error": "Invalid administrator credentials."})
            return
        LOGIN_ATTEMPTS.pop(ip, None)
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        SESSIONS[token] = {"csrf": csrf, "expires": now + 8 * 60 * 60}
        cookie = f"cafe_admin={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=28800"
        if COOKIE_SECURE:
            cookie += "; Secure"
        self._send(200, {"csrfToken": csrf}, {"Set-Cookie": cookie})

    def _create_order(self):
        payload = self._read_json()
        customer = payload.get("customer")
        items = payload.get("items")
        if not isinstance(customer, dict) or not isinstance(items, list) or not items or len(items) > 50:
            raise ValueError("Provide customer details and between 1 and 50 cart lines.")
        name = self._text(customer.get("name"), "Name", 1, 100)
        email = self._text(customer.get("email"), "Email", 3, 254)
        phone = self._text(customer.get("phone"), "Phone", 7, 30)
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            raise ValueError("Enter a valid email address.")
        if not any(char.isdigit() for char in phone):
            raise ValueError("Enter a valid phone number.")

        quantities = {}
        for line in items:
            if not isinstance(line, dict):
                raise ValueError("Each cart line must include a product and quantity.")
            product_id = line.get("productId")
            quantity = line.get("quantity")
            if not isinstance(product_id, int) or isinstance(product_id, bool):
                raise ValueError("Cart product id is invalid.")
            if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1 or quantity > 99:
                raise ValueError("Each item quantity must be between 1 and 99.")
            quantities[product_id] = quantities.get(product_id, 0) + quantity
        if any(quantity > 99 for quantity in quantities.values()):
            raise ValueError("A product quantity cannot exceed 99.")

        with connect_db() as db:
            db.execute("BEGIN IMMEDIATE")
            product_rows = {}
            for product_id, quantity in quantities.items():
                row = db.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
                if row is None or not row["available"]:
                    raise ValueError("A cart item is no longer available. Refresh the menu.")
                if row["stock_quantity"] < quantity:
                    raise ValueError(f"Not enough stock available for {row['name']}.")
                product_rows[product_id] = row
            total = sum(product_rows[pid]["price"] * qty for pid, qty in quantities.items())
            order_number = "MC-" + secrets.token_hex(4).upper()
            cursor = db.execute(
                """INSERT INTO orders
                   (order_number, customer_name, customer_email, customer_phone, total)
                   VALUES (?, ?, ?, ?, ?)""",
                (order_number, name, email, phone, total),
            )
            order_id = cursor.lastrowid
            for product_id, quantity in quantities.items():
                product = product_rows[product_id]
                db.execute(
                    """INSERT INTO order_items
                       (order_id, product_id, product_name, unit_price, quantity, line_total)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (order_id, product_id, product["name"], product["price"], quantity, product["price"] * quantity),
                )
                db.execute(
                    "UPDATE products SET stock_quantity = stock_quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (quantity, product_id),
                )
            db.execute(
                "INSERT INTO order_status_history (order_id, status) VALUES (?, 'pending')",
                (order_id,),
            )
        self._send(201, {"orderNumber": order_number, "total": total, "status": "pending"})

    def _save_product(self, product_id):
        payload = self._read_json()
        name = self._text(payload.get("name"), "Product name", 1, 100)
        description = self._text(payload.get("description"), "Description", 1, 500)
        price = payload.get("price")
        stock = payload.get("stock_quantity")
        category = payload.get("category")
        image = payload.get("image")
        if not isinstance(price, int) or isinstance(price, bool) or price < 0 or price > 1_000_000:
            raise ValueError("Price must be a whole number between 0 and 1000000.")
        if not isinstance(stock, int) or isinstance(stock, bool) or stock < 0 or stock > 1_000_000:
            raise ValueError("Stock must be a whole number between 0 and 1000000.")
        if category not in ALLOWED_CATEGORIES:
            raise ValueError("Choose coffee, breakfast, or desserts as the category.")
        if not isinstance(image, str) or not image.startswith("img/") or len(image) > 200 or ".." in image:
            raise ValueError("Image must be a relative path inside the img folder.")
        image_path = (ROOT / image).resolve()
        image_root = (ROOT / "img").resolve()
        if not image_path.is_relative_to(image_root) or not image_path.is_file() or image_path.suffix.lower() not in {
            ".png", ".jpg", ".jpeg", ".webp"
        }:
            raise ValueError("Choose an existing PNG, JPG, or WEBP image from the img folder.")
        available = payload.get("available", True)
        if not isinstance(available, bool):
            raise ValueError("Availability must be true or false.")
        creating = product_id is None
        with connect_db() as db:
            values = (name, description, price, category, image, stock, int(available))
            if product_id is None:
                cursor = db.execute(
                    """INSERT INTO products
                       (name, description, price, category, image, stock_quantity, available)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                product_id = cursor.lastrowid
            else:
                cursor = db.execute(
                    """UPDATE products SET name = ?, description = ?, price = ?, category = ?,
                       image = ?, stock_quantity = ?, available = ?, updated_at = CURRENT_TIMESTAMP
                       WHERE id = ?""",
                    values + (product_id,),
                )
                if cursor.rowcount == 0:
                    self._send(404, {"error": "Product not found."})
                    return
        self._send(201 if creating else 200, {"id": product_id})

    def _update_order_status(self, order_id):
        payload = self._read_json()
        status = payload.get("status")
        if status not in ORDER_STATUSES:
            raise ValueError("Choose a supported order status.")
        with connect_db() as db:
            db.execute("BEGIN IMMEDIATE")
            order = db.execute("SELECT status FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order is None:
                self._send(404, {"error": "Order not found."})
                return
            previous = order["status"]
            if previous == status:
                self._send(200, {"ok": True})
                return
            if previous != "cancelled" and status == "cancelled":
                db.execute(
                    """UPDATE products SET stock_quantity = stock_quantity + (
                       SELECT quantity FROM order_items WHERE order_id = ? AND product_id = products.id
                       ), updated_at = CURRENT_TIMESTAMP WHERE id IN (
                       SELECT product_id FROM order_items WHERE order_id = ? AND product_id IS NOT NULL)""",
                    (order_id, order_id),
                )
            elif previous == "cancelled" and status != "cancelled":
                items = db.execute(
                    "SELECT product_id, quantity FROM order_items WHERE order_id = ? AND product_id IS NOT NULL",
                    (order_id,),
                ).fetchall()
                for item in items:
                    stock = db.execute(
                        "SELECT stock_quantity FROM products WHERE id = ?", (item["product_id"],)
                    ).fetchone()
                    if stock is None or stock["stock_quantity"] < item["quantity"]:
                        raise ValueError("Cannot reopen this order because an item is out of stock.")
                for item in items:
                    db.execute(
                        "UPDATE products SET stock_quantity = stock_quantity - ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (item["quantity"], item["product_id"]),
                    )
            db.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
            db.execute(
                "INSERT INTO order_status_history (order_id, status) VALUES (?, ?)",
                (order_id, status),
            )
        self._send(200, {"ok": True})

    @staticmethod
    def _text(value, label, minimum, maximum):
        if not isinstance(value, str):
            raise ValueError(f"{label} must be text.")
        value = value.strip()
        if not minimum <= len(value) <= maximum:
            raise ValueError(f"{label} must be between {minimum} and {maximum} characters.")
        return value

    @staticmethod
    def _path_id(path, prefix):
        suffix = path[len(prefix):]
        if not suffix.isdigit() or int(suffix) < 1:
            raise ValueError("Record id is invalid.")
        return int(suffix)

    def _serve_static(self, url_path):
        if url_path == "/":
            url_path = "/index.html"
        relative = Path(url_path.lstrip("/"))
        target = (ROOT / relative).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file() or target.name.startswith("."):
            self.send_error(404, "File not found.")
            return
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(content)


def main():
    initialize_database()
    if len(sys.argv) > 1 and sys.argv[1] == "set-admin":
        first = getpass("New administrator password (minimum 12 characters): ")
        second = getpass("Confirm password: ")
        if not hmac.compare_digest(first, second):
            print("Passwords do not match.", file=sys.stderr)
            return 1
        try:
            set_admin_password(first)
        except ValueError as error:
            print(error, file=sys.stderr)
            return 1
        print("Administrator password saved.")
        return 0
    server = ThreadingHTTPServer((HOST, PORT), CafeHandler)
    print(f"Modern Cafe running at http://{HOST}:{PORT}")
    print("Set an administrator password with: python server.py set-admin")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
