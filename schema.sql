CREATE TABLE customers (customer_id INTEGER PRIMARY KEY, region TEXT NOT NULL);
CREATE TABLE products (sku TEXT PRIMARY KEY, category TEXT NOT NULL);
CREATE TABLE transactions (
 line_id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
 sku TEXT NOT NULL REFERENCES products(sku), sale_date TEXT NOT NULL,
 units INTEGER NOT NULL CHECK(units > 0), unit_price_paise INTEGER NOT NULL CHECK(unit_price_paise >= 0),
 unit_cost_paise INTEGER NOT NULL CHECK(unit_cost_paise >= 0)
);
CREATE INDEX transaction_date ON transactions(sale_date);
