-- Tiny work-order fixture for the write-line tracer bullet (#27): 12 work orders, 4 of them open,
-- and their tasks. Built into a SQLite file by tests/conftest.py. The labour and parts costs (#35)
-- are 60 and 30 percent of the total, which also carries overhead, so it is not their sum.
CREATE TABLE workorders (
    wonum TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    site TEXT NOT NULL,
    reported_date TEXT NOT NULL,
    total_cost REAL NOT NULL,
    labor_cost REAL NOT NULL,
    parts_cost REAL NOT NULL
);
CREATE TABLE tasks (
    taskid INTEGER PRIMARY KEY,
    wonum TEXT NOT NULL REFERENCES workorders (wonum),
    description TEXT NOT NULL,
    hours REAL NOT NULL
);
INSERT INTO workorders VALUES
    ('WO-1001', 'CLOSED', 'NORTH', '2026-01-05', 420.0, 252.0, 126.0),
    ('WO-1002', 'OPEN',   'NORTH', '2026-01-09', 150.0, 90.0, 45.0),
    ('WO-1003', 'CLOSED', 'SOUTH', '2026-01-12', 980.5, 588.3, 294.15),
    ('WO-1004', 'CLOSED', 'SOUTH', '2026-02-02', 75.0, 45.0, 22.5),
    ('WO-1005', 'OPEN',   'NORTH', '2026-02-14', 310.0, 186.0, 93.0),
    ('WO-1006', 'CLOSED', 'NORTH', '2026-02-20', 1200.0, 720.0, 360.0),
    ('WO-1007', 'CLOSED', 'SOUTH', '2026-03-03', 64.25, 38.55, 19.28),
    ('WO-1008', 'OPEN',   'SOUTH', '2026-03-11', 505.0, 303.0, 151.5),
    ('WO-1009', 'CLOSED', 'NORTH', '2026-03-19', 230.0, 138.0, 69.0),
    ('WO-1010', 'CLOSED', 'SOUTH', '2026-04-01', 890.0, 534.0, 267.0),
    ('WO-1011', 'OPEN',   'NORTH', '2026-04-08', 45.0, 27.0, 13.5),
    ('WO-1012', 'CLOSED', 'NORTH', '2026-04-15', 615.75, 369.45, 184.73);
INSERT INTO tasks (wonum, description, hours) VALUES
    ('WO-1001', 'Inspect pump', 1.5),      ('WO-1001', 'Replace seal', 3.0),
    ('WO-1002', 'Inspect valve', 2.0),     ('WO-1002', 'Order parts', 0.5),
    ('WO-1003', 'Rewire panel', 6.0),      ('WO-1003', 'Test circuit', 1.0),   ('WO-1003', 'Clean up', 0.5),
    ('WO-1004', 'Lubricate bearing', 0.75),
    ('WO-1005', 'Diagnose leak', 2.5),     ('WO-1005', 'Patch pipe', 4.0),
    ('WO-1006', 'Replace motor', 8.0),     ('WO-1006', 'Align shaft', 2.0),
    ('WO-1007', 'Tighten fittings', 0.5),
    ('WO-1008', 'Survey roof', 3.0),       ('WO-1008', 'Seal gutter', 2.5),    ('WO-1008', 'Inspect drain', 1.0),
    ('WO-1009', 'Replace filter', 1.0),    ('WO-1009', 'Reset alarm', 0.25),
    ('WO-1010', 'Repair door', 5.0),       ('WO-1010', 'Paint frame', 2.0),
    ('WO-1011', 'Check thermostat', 0.75),
    ('WO-1012', 'Service boiler', 4.5),    ('WO-1012', 'Flush lines', 1.5);
