# POS Billing & Inventory Management API

A Django REST Framework backend for a POS / billing / inventory system (built for a textile/retail business). JSON-only API, JWT auth, role-based access, transactional sales with automatic stock control, and reporting.

## Features
- JWT auth (access 30 min, refresh 1 day, rotation + blacklist on logout)
- Roles: `ADMIN`, `MANAGER`, `CASHIER`, `STAFF` with reusable permission classes
- Categories, brands, products (SKU/barcode unique, `Decimal` money), stock ledger, low-stock list
- Customers and sales with auto invoice numbers (`INV-YYYYMMDD-0001`), atomic stock deduction, cancel/refund with stock return
- Reports: dashboard, sales summary, daily, monthly, top products, payment summary
- Search, filtering, ordering, pagination (`page_size` default 20, max 100)
- Uniform error envelope: `{"success": false, "message": "...", "errors": {...}}`
- Django admin for all models; automated tests

## Stack
Python 3.12+, Django 5.2, DRF 3.16, SimpleJWT, django-filter, django-cors-headers, python-decouple, dj-database-url, SQLite (dev) / PostgreSQL (`psycopg`).

## Architecture
```
config/     settings, urls, pagination, exception handler + response helpers
accounts/   custom User, JWT views, permissions.py (role classes), user management
inventory/  Category, Brand, Product, StockTransaction; services.py holds stock logic
sales/      Customer, Sale, SaleItem; services.py holds create_sale / update_sale
reports/    read-only aggregation views (no models)
```
Views stay thin; stock and sale logic lives in `services.py` inside `transaction.atomic()` with `select_for_update()` (products locked in id order to avoid deadlocks).

## Setup (Windows CMD / PowerShell)
```cmd
cd /d D:\POS\Server
python -m venv env
env\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
python manage.py makemigrations accounts inventory sales reports
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```
Run tests: `python manage.py test`


## Roles
| Role | Can |
|---|---|
| ADMIN (and superusers) | Everything, incl. user management and reports |
| MANAGER | Products, inventory, customers, sales (incl. cancel/refund), reports |
| CASHIER | View products/inventory/customers, create customers, create sales, view **own** sales |
| STAFF | View products/inventory, limited customer info (id, name, city). No sales. |

Public `/register/` always creates a `STAFF` user; roles are assigned by admins via `/users/`.

## Endpoints
| Method | Endpoint | Auth | Role | Purpose |
|---|---|---|---|---|
| POST | /api/accounts/register/ | No | – | Register (STAFF) |
| POST | /api/accounts/login/ | No | – | Get tokens (username or email) |
| POST | /api/accounts/token/refresh/ | No | – | Rotate refresh token |
| POST | /api/accounts/logout/ | Yes | Any | Blacklist refresh token |
| GET/PUT/PATCH | /api/accounts/profile/ | Yes | Any | Own profile |
| POST | /api/accounts/change-password/ | Yes | Any | Change password |
| GET/POST | /api/accounts/users/ | Yes | ADMIN | List/create users |
| GET/PATCH/DELETE | /api/accounts/users/{id}/ | Yes | ADMIN | Manage a user |
| GET | /api/inventory/categories/, brands/, products/ (+ `{id}/`) | Yes | Any | Read |
| POST/PUT/PATCH/DELETE | same as above | Yes | ADMIN, MANAGER | Write |
| GET | /api/inventory/stock/ | Yes | ADMIN, MANAGER | Stock transaction history |
| POST | /api/inventory/stock/adjust/ | Yes | ADMIN, MANAGER | Adjust stock |
| GET | /api/inventory/low-stock/ | Yes | Any | Products at/below minimum |
| GET/POST | /api/sales/ | Yes | ADMIN, MANAGER, CASHIER | List (cashier: own) / create sale |
| GET | /api/sales/{id}/ | Yes | ADMIN, MANAGER, CASHIER | Sale detail |
| PATCH | /api/sales/{id}/ | Yes | ADMIN, MANAGER | Update status/notes (cancel/refund returns stock) |
| GET | /api/sales/invoice/{invoice_number}/ | Yes | ADMIN, MANAGER, CASHIER | Sale by invoice |
| GET | /api/sales/my-sales/ · today/ · recent/ | Yes | ADMIN, MANAGER, CASHIER | Filtered sale lists |
| GET | /api/sales/customers/ · {id}/ | Yes | Any (STAFF limited) | Customers |
| POST | /api/sales/customers/ | Yes | ADMIN, MANAGER, CASHIER | Create customer |
| PUT/PATCH/DELETE | /api/sales/customers/{id}/ | Yes | ADMIN, MANAGER | Edit/delete customer |
| GET | /api/sales/customers/{id}/sales/ | Yes | ADMIN, MANAGER, CASHIER | Customer sales history |
| GET | /api/reports/dashboard/ | Yes | ADMIN, MANAGER | Dashboard stats |
| GET | /api/reports/sales/ | Yes | ADMIN, MANAGER | Summary (`start_date`, `end_date`) |
| GET | /api/reports/daily-sales/ · monthly-sales/ | Yes | ADMIN, MANAGER | Grouped revenue |
| GET | /api/reports/top-products/ | Yes | ADMIN, MANAGER | By quantity sold (`limit`, dates) |
| GET | /api/reports/payment-summary/ | Yes | ADMIN, MANAGER | Per payment method |

Filters: products `search, category, brand, is_active, min_price, max_price, min_stock, max_stock, ordering`; sales `search, payment_method, payment_status, sale_status, cashier, customer, start_date, end_date, ordering`.

## Postman examples
Send `Content-Type: application/json`. For every protected endpoint add the header
`Authorization: Bearer ACCESS_TOKEN` (Postman → Authorization tab → Bearer Token).

1. **Register** `POST /api/accounts/register/`
   `{"username":"clerk","email":"clerk@example.com","first_name":"Clerk","password":"StrongPass#123","password2":"StrongPass#123"}`
2. **Login** `POST /api/accounts/login/` → `{"username":"admin","password":"..."}` (copy `access` and `refresh`)
3. **Refresh** `POST /api/accounts/token/refresh/` → `{"refresh":"REFRESH_TOKEN"}` (returns a new access **and** a new refresh; the old one is blacklisted)
4. **Category** `POST /api/inventory/categories/` → `{"name":"Shirts"}`
5. **Product** `POST /api/inventory/products/`
   `{"name":"Linen Shirt","sku":"LS-001","category":1,"cost_price":"500.00","selling_price":"899.00","stock_quantity":20,"minimum_stock":5,"unit":"PCS","tax_percentage":"5.00"}`
6. **Adjust stock** `POST /api/inventory/stock/adjust/` → `{"product":1,"quantity":20,"reason":"New stock received"}` (optional `transaction_type`: PURCHASE, RETURN, ADJUSTMENT, DAMAGE)
7. **Customer** `POST /api/sales/customers/` → `{"name":"Asha","phone":"9876543210","city":"Kochi"}`
8. **Sale** `POST /api/sales/`
   `{"customer":1,"payment_method":"CASH","discount_amount":50,"items":[{"product":1,"quantity":2},{"product":4,"quantity":1}]}`
   (`customer` optional for walk-ins; item-level `discount` optional)
9. **View sales** `GET /api/sales/?payment_method=CASH&ordering=-created_at`
10. **Dashboard** `GET /api/reports/dashboard/`
11. **Reports** `GET /api/reports/sales/?start_date=2026-09-01&end_date=2026-09-29`, `/daily-sales/`, `/monthly-sales/`, `/top-products/`, `/payment-summary/`

## Behaviour notes
- Sale totals: `subtotal` = Σ(line − line discount); `tax_amount` = Σ(taxable × product tax %); `total = subtotal + tax − discount_amount`.
- Insufficient stock → HTTP 409 and nothing is written. Any failure mid-sale rolls back the sale, items and stock transactions.
- Reports count only `COMPLETED` sales. Timezone is `Asia/Kolkata`.
- Product stock can't be edited through PATCH/PUT; use `/stock/adjust/` so every change is logged.
- Records with history (products with sales, users who made sales) can't be hard-deleted (409); deactivate instead.
- `select_for_update()` is a no-op on SQLite; row locking takes effect on PostgreSQL.

## Production notes
Use PostgreSQL via `DATABASE_URL`, set `DEBUG=False`, a strong `SECRET_KEY`, real `ALLOWED_HOSTS` and `CORS_ALLOWED_ORIGINS`, run behind HTTPS, `python manage.py collectstatic`, and serve with gunicorn/uvicorn plus a static file server. Consider throttling on `/login/` and `/register/`.
