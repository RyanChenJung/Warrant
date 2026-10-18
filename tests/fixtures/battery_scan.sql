-- Small shop fixture for the battery export and the clean scan (#30). Built into a SQLite file by
-- tests/conftest.py. Names are mixed-case and the declared keys join differently named columns, as
-- in LiveSQLBench-Base-Lite. Planted: Total = Net + Tax + Shipping on every order; one Fee stored as
-- 1e-05; order O24 references a customer that does not exist; customer C8 has no order; Note is ''
-- on four orders and NULL on four; Holidays is linked to nothing.
CREATE TABLE Customers (
    CustRegistry TEXT PRIMARY KEY,
    Region TEXT,
    Tier TEXT
);
CREATE TABLE Orders (
    OrderId TEXT PRIMARY KEY,
    CustRef TEXT REFERENCES Customers (CustRegistry),
    Status TEXT,
    Net REAL,
    Tax REAL,
    Shipping REAL,
    Total REAL,
    Fee REAL,
    Note TEXT
);
CREATE TABLE OrderLines (
    LineId INTEGER PRIMARY KEY,
    OrderRef TEXT REFERENCES Orders (OrderId),
    Qty INTEGER
);
CREATE TABLE Holidays (
    Day TEXT PRIMARY KEY,
    Label TEXT
);
INSERT INTO Customers
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 8)
SELECT 'C' || i, CASE i % 2 WHEN 0 THEN 'North' ELSE 'South' END, CASE i % 3 WHEN 0 THEN 'Gold' ELSE 'Basic' END
FROM n;
INSERT INTO Orders
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 24)
SELECT printf('O%02d', i),
       CASE WHEN i = 24 THEN 'C99' ELSE 'C' || (i % 7 + 1) END,
       CASE i % 4 WHEN 0 THEN 'Cancelled' ELSE 'Filled' END,
       10.0 * i + 3,
       0.5 * i + 0.25,
       2.0 + i,
       (10.0 * i + 3) + (0.5 * i + 0.25) + (2.0 + i),
       CASE WHEN i = 1 THEN 0.00001 ELSE 0.25 * i END,
       CASE WHEN i % 5 = 0 THEN '' WHEN i % 6 = 0 THEN NULL ELSE 'ok' END
FROM n;
INSERT INTO OrderLines
WITH RECURSIVE n (i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 48)
SELECT i, printf('O%02d', (i - 1) % 24 + 1), i % 5 + 1 FROM n;
INSERT INTO Holidays VALUES ('2026-01-01', 'New Year'), ('2026-05-01', 'Labour Day'), ('2026-12-25', 'Christmas');
