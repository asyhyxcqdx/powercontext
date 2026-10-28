"""Existing behavior that MiniMax is required to preserve."""

from workshop.inventory import filter_products


PRODUCTS = [
    {"sku": "A", "category": "Tools", "stock": 1},
    {"sku": "B", "category": "Books", "stock": 0},
    {"sku": "C", "category": "Tools", "stock": 3},
]


def ids(rows):
    return [row["sku"] for row in rows]


def test_no_filter_keeps_all_in_order():
    assert ids(filter_products(PRODUCTS)) == ["A", "B", "C"]


def test_category_match_is_case_insensitive():
    assert ids(filter_products(PRODUCTS, category="tOoLs")) == ["A", "C"]


def test_unknown_category_is_empty():
    assert filter_products(PRODUCTS, category="Unknown") == []


def test_return_value_is_new_list():
    assert filter_products(PRODUCTS) is not PRODUCTS


def test_inputs_not_mutated():
    before = [dict(row) for row in PRODUCTS]
    filter_products(PRODUCTS, category="Tools")
    assert PRODUCTS == before


def test_new_filter_must_still_not_mutate_inputs():
    before = [dict(row) for row in PRODUCTS]
    result = filter_products(PRODUCTS, min_stock=2)
    assert PRODUCTS == before
    assert result is not PRODUCTS
