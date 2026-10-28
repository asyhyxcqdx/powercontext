"""The unchanged target tests must FAIL for the baseline business defect."""

from workshop.inventory import filter_products


PRODUCTS = [
    {"sku": "A1", "category": "Tools", "stock": 0},
    {"sku": "B2", "category": "Books", "stock": 2},
    {"sku": "C3", "category": "Tools", "stock": 5},
    {"sku": "D4", "category": "Tools", "stock": 2},
]


def ids(rows):
    return [row["sku"] for row in rows]


def test_min_stock_inclusive_boundary():
    assert ids(filter_products(PRODUCTS, min_stock=2)) == ["B2", "C3", "D4"]


def test_min_stock_zero_is_a_real_threshold():
    # Negative stock represents outstanding backorders; zero is NOT equivalent to None.
    backorders = [
        {"sku": "N", "category": "Tools", "stock": -1},
        {"sku": "Z", "category": "Tools", "stock": 0},
    ]
    assert ids(filter_products(backorders, min_stock=0)) == ["Z"]


def test_category_combines_with_stock_threshold():
    assert ids(filter_products(PRODUCTS, category="TOOLS", min_stock=2)) == ["C3", "D4"]


def test_stock_threshold_larger_than_every_item():
    assert filter_products(PRODUCTS, min_stock=99) == []
