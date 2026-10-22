import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class CafeApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temporary_directory.name) / "test.sqlite3"
        server.initialize_database()
        server.set_admin_password("test-password-for-admin")
        cls.http_server = ThreadingHTTPServer(("127.0.0.1", 0), server.CafeHandler)
        cls.thread = threading.Thread(target=cls.http_server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.http_server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.http_server.shutdown()
        cls.thread.join()
        cls.http_server.server_close()
        cls.temporary_directory.cleanup()
        server.SESSIONS.clear()
        server.LOGIN_ATTEMPTS.clear()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request_headers = dict(headers or {})
        if body is not None:
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(body))
        connection.request(method, path, body, request_headers)
        response = connection.getresponse()
        data = response.read()
        response_headers = dict(response.getheaders())
        connection.close()
        return response.status, json.loads(data) if data else None, response_headers

    def test_checkout_uses_database_price_and_persists_line_item(self):
        products_status, products, _ = self.request("GET", "/api/products")
        self.assertEqual(products_status, 200)
        espresso = next(product for product in products if product["name"] == "Espresso")
        status, result, _ = self.request("POST", "/api/orders", {
            "customer": {"name": "Test Customer", "email": "test@example.com", "phone": "9876543210"},
            "items": [{"productId": espresso["id"], "quantity": 2, "price": 1}],
        })
        self.assertEqual(status, 201)
        self.assertEqual(result["total"], espresso["price"] * 2)
        with server.connect_db() as db:
            line = db.execute(
                "SELECT product_name, unit_price, quantity, line_total FROM order_items"
            ).fetchone()
            stock = db.execute("SELECT stock_quantity FROM products WHERE id = ?", (espresso["id"],)).fetchone()[0]
            order_id = db.execute("SELECT id FROM orders WHERE order_number = ?", (result["orderNumber"],)).fetchone()[0]
        self.assertEqual(tuple(line), ("Espresso", espresso["price"], 2, espresso["price"] * 2))
        self.assertEqual(stock, 98)
        _, login, headers = self.request(
            "POST", "/api/admin/login", {"password": "test-password-for-admin"}
        )
        auth_headers = {
            "Cookie": headers["Set-Cookie"].split(";", 1)[0],
            "X-CSRF-Token": login["csrfToken"],
        }
        status, _, _ = self.request(
            "PUT", f"/api/admin/orders/{order_id}", {"status": "cancelled"}, auth_headers
        )
        self.assertEqual(status, 200)
        with server.connect_db() as db:
            stock = db.execute("SELECT stock_quantity FROM products WHERE id = ?", (espresso["id"],)).fetchone()[0]
        self.assertEqual(stock, 100)
        status, _, _ = self.request(
            "PUT", f"/api/admin/orders/{order_id}", {"status": "pending"}, auth_headers
        )
        self.assertEqual(status, 200)
        with server.connect_db() as db:
            stock = db.execute("SELECT stock_quantity FROM products WHERE id = ?", (espresso["id"],)).fetchone()[0]
        self.assertEqual(stock, 98)

    def test_admin_routes_require_login_and_csrf(self):
        status, result, _ = self.request("GET", "/api/admin/dashboard")
        self.assertEqual(status, 401)
        status, result, headers = self.request("POST", "/api/admin/login", {"password": "test-password-for-admin"})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        csrf_token = result["csrfToken"]
        status, _, _ = self.request("POST", "/api/admin/products", {
            "name": "Test Item", "description": "Test description", "price": 50,
            "stock_quantity": 3, "category": "coffee", "image": "img/espresso.png",
        }, {"Cookie": cookie})
        self.assertEqual(status, 403)
        status, data, _ = self.request("GET", "/api/admin/dashboard", headers={"Cookie": cookie})
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["metrics"]["product_count"], 18)
        status, _, _ = self.request("POST", "/api/admin/products", {
            "name": "Test Item", "description": "Test description", "price": 50,
            "stock_quantity": 3, "category": "coffee", "image": "img/espresso.png",
        }, {"Cookie": cookie, "X-CSRF-Token": csrf_token})
        self.assertEqual(status, 201)

    def test_invalid_checkout_is_rejected(self):
        status, result, _ = self.request("POST", "/api/orders", {
            "customer": {"name": "Test Customer", "email": "not-an-email", "phone": "9876543210"},
            "items": [{"productId": 1, "quantity": 1}],
        })
        self.assertEqual(status, 400)
        self.assertIn("email", result["error"].lower())


if __name__ == "__main__":
    unittest.main()
