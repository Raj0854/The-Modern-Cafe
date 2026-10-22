# The-Modern-Cafe
https://raj0854.github.io/The-Modern-Cafe/

## Local ordering backend and admin dashboard

The original static pages and their styling remain in place. A Python 3.10+
standard-library server now provides a persistent SQLite menu and order API,
and serves the existing site and admin dashboard from the same origin.

### Run locally

1. Install Python 3.10 or newer.
2. In the repository folder, create an administrator password:

   ```powershell
   py -3 server.py set-admin
   ```

   The password is stored as a salted PBKDF2-HMAC-SHA256 hash in the local
   database. There is no default administrator account or password.
3. Start the website and API:

   ```powershell
   py -3 server.py
   ```
4. Open `http://127.0.0.1:8000/` for the customer site and
   `http://127.0.0.1:8000/admin.html` for the admin dashboard.

The server creates `data/cafe.sqlite3` and seeds the existing menu on first
run. Set `CAFE_DB_PATH`, `CAFE_HOST`, or `CAFE_PORT` in the process environment
to override the database location, bind address, or port. The default bind
address is loopback-only. Set `CAFE_COOKIE_SECURE=1` when serving behind an
HTTPS reverse proxy.

### Included functionality

- The menu is loaded from SQLite. Products can be added, edited, archived,
  priced, marked available/unavailable, and assigned stock in the dashboard.
- New database products are rendered in their existing menu category using the
  site's current card styles. Product images must be existing image assets in
  `img/`.
- The cart persists between pages in the customer's browser. Customers can
  update quantities, remove items, enter contact details, and place an order.
- Checkout recalculates prices from the database, checks stock, and saves the
  order and its line-item price snapshots in a SQLite transaction.
- Admin login uses an HttpOnly, SameSite session cookie, CSRF tokens, a
  password hash, and a per-IP login-attempt limit. Admin routes enforce
  authentication on the server, not just in the dashboard.
- Staff can review recent orders, update supported statuses, and see a small
  summary of orders, revenue, products, and low stock. Cancelling an order
  restores stock; reopening a cancelled order checks and reserves stock again.

Run the backend tests with:

```powershell
py -3 -m unittest discover -s tests -v
```

### Deployment and current boundaries

GitHub Pages can host the original static pages, but it cannot run this Python
API or store SQLite data. Deploy the project on a Python-capable host with
persistent disk, and use HTTPS before exposing it to the public internet. The
default development server is not a production WSGI server; place a supported
production server and TLS reverse proxy in front of it for a public
deployment. Back up `data/cafe.sqlite3` regularly, with the application stopped
or using SQLite's online backup API.

This implementation is the first working ordering/admin slice, not every
feature in the supplied full-system brief. It does not yet include customer
accounts, payment gateway integration or payment tracking, tax/coupons, email,
file uploads, supplier/inventory history, reservations, analytics exports,
granular staff roles, or full CMS editing. No payment is collected; arrange
payment separately before fulfilling orders. Do not treat it as
production-ready for public deployment until the chosen hosting, HTTPS,
backups, operational logging, and remaining business requirements are
completed and tested.

🌟 Overall  Impression

Your website presents a clean, modern, and user-friendly café experience. It successfully captures the vibe of a real café while keeping everything simple and easy to navigate.

👍 Key Strengths

1. Attractive & Modern Design
The layout looks visually appealing with a nice café theme. It gives a warm and welcoming feel, which is perfect for a food-related website.

2. Clear Structure & Navigation
Sections like menu, about, and contact are well-organized. Users can easily explore the site without confusion.

3. Engaging Food Presentation
The dishes are showcased in a way that makes them look delicious and appealing—this is very important for a café website.

4. Good Use of Frontend Skills
The site demonstrates solid use of HTML, CSS, and styling. It shows your understanding of layout, spacing, and responsiveness.

5. Real-world Project Feel
It doesn’t look like just a practice project—it feels like a real café business website, which is great for your portfolio.

6. Smooth User Experience
The flow of the website is simple and intuitive, making it easy for users to browse and interact.
