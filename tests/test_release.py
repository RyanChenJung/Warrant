import json
import shutil
import sqlite3
import stat

import pytest

from warrant.data.release import (
    ChecksumMismatch,
    ForeignKey,
    Release,
    fetch,
    load_database,
)

REVISION = "0123456789abcdef0123456789abcdef01234567"
RELEASE = Release(dataset="birdsql/example", revision=REVISION, databases=("shop",))


@pytest.fixture
def remote(tmp_path):
    """A tiny release as the remote serves it: one database, its column meanings and knowledge base."""
    root = tmp_path / "remote" / "shop"
    root.mkdir(parents=True)
    con = sqlite3.connect(root / "shop_template.sqlite")
    con.executescript(
        """
        CREATE TABLE customers (custkey INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE orders (
            orderid INTEGER PRIMARY KEY,
            custref INTEGER REFERENCES customers (custkey),
            total REAL
        );
        CREATE TABLE orderlines (
            lineid INTEGER PRIMARY KEY,
            orderid INTEGER REFERENCES orders (orderid),
            amount REAL
        );
        INSERT INTO customers VALUES (1, 'Ada'), (2, 'Grace');
        INSERT INTO orders VALUES (10, 1, 30.0), (11, 2, 5.0);
        INSERT INTO orderlines VALUES (100, 10, 10.0), (101, 10, 20.0), (102, 11, 5.0);
        """
    )
    con.commit()
    con.close()
    meanings = {
        "shop|customers|custkey": "Full name: 'Customer Key'.",
        "shop|customers|name": "Full name: 'Customer Name'.",
        "shop|orders|custref": "Full name: 'Customer Reference'.",
        "shop|orders|total": "Full name: 'Order Total'.",
    }
    (root / "shop_column_meaning_base.json").write_text(json.dumps(meanings))
    kb = [
        {"id": 0, "knowledge": "Large order", "definition": "An order whose total is over 25."},
        {"id": 1, "knowledge": "Repeat customer", "definition": "A customer with two or more orders."},
    ]
    (root / "shop_kb.jsonl").write_text("".join(json.dumps(e) + "\n" for e in kb))
    return tmp_path / "remote"


@pytest.fixture
def download(remote):
    """A fake downloader serving the tiny release; it records every URL it is asked for."""

    def fake(url, dest):
        fake.urls.append(url)
        relative = url.split(f"/resolve/{REVISION}/", 1)[1]
        shutil.copyfile(remote / relative, dest)

    fake.urls = []
    return fake


def test_fetching_the_same_revision_twice_gives_identical_checksums(tmp_path, download):
    first = fetch(RELEASE, tmp_path / "a", download=download)
    second = fetch(RELEASE, tmp_path / "b", download=download)
    assert first == second
    assert len(first) == 3


def test_fetch_asks_only_for_the_three_per_database_files_at_the_pinned_revision(tmp_path, download):
    fetch(RELEASE, tmp_path / "data", download=download)
    prefix = f"https://huggingface.co/datasets/birdsql/example/resolve/{REVISION}/"
    assert sorted(download.urls) == [
        prefix + "shop/shop_column_meaning_base.json",
        prefix + "shop/shop_kb.jsonl",
        prefix + "shop/shop_template.sqlite",
    ]


def test_fetch_rejects_a_file_whose_checksum_differs_from_the_record(tmp_path, download):
    recorded = fetch(RELEASE, tmp_path / "a", download=download)
    tampered = dict(recorded, **{"shop/shop_kb.jsonl": "0" * 64})
    with pytest.raises(ChecksumMismatch, match="shop/shop_kb.jsonl"):
        fetch(RELEASE, tmp_path / "b", expected=tampered, download=download)


def test_fetch_skips_files_that_already_match_the_record(tmp_path, download):
    recorded = fetch(RELEASE, tmp_path / "data", download=download)
    download.urls.clear()
    fetch(RELEASE, tmp_path / "data", expected=recorded, download=download)
    assert download.urls == []


def test_clean_copy_is_read_only_after_fetch(tmp_path, download):
    fetch(RELEASE, tmp_path / "data", download=download)
    mode = (tmp_path / "data" / "shop" / "shop_template.sqlite").stat().st_mode
    assert stat.S_IMODE(mode) & 0o222 == 0


def test_loader_returns_declared_foreign_keys_including_pairs_whose_names_differ(tmp_path, download):
    fetch(RELEASE, tmp_path / "data", download=download)
    db = load_database(tmp_path / "data", "shop")
    assert sorted(db.foreign_keys) == [
        ForeignKey("orderlines", "orderid", "orders", "orderid"),
        ForeignKey("orders", "custref", "customers", "custkey"),
    ]


def test_loader_returns_every_column_meaning_and_knowledge_base_entry(tmp_path, download, remote):
    fetch(RELEASE, tmp_path / "data", download=download)
    db = load_database(tmp_path / "data", "shop")
    assert db.column_meanings == json.loads((remote / "shop" / "shop_column_meaning_base.json").read_text())
    assert [e["knowledge"] for e in db.knowledge_base] == ["Large order", "Repeat customer"]


def test_loading_leaves_the_clean_copy_unchanged(tmp_path, download):
    fetch(RELEASE, tmp_path / "data", download=download)
    clean = tmp_path / "data" / "shop" / "shop_template.sqlite"
    before = clean.read_bytes()
    load_database(tmp_path / "data", "shop")
    assert clean.read_bytes() == before


def test_a_databases_clean_copy_is_its_template_file_in_the_fetched_release(tmp_path, monkeypatch):
    monkeypatch.setenv("WARRANT_DATA_DIR", str(tmp_path))
    assert RELEASE.template("shop") == RELEASE.local_dir() / "shop" / "shop_template.sqlite"
