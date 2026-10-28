"""Inventory search for a small retail service."""

from __future__ import annotations


def filter_products(products: list[dict], category: str | None = None,
                    min_stock: int | None = None) -> list[dict]:
    """Return matching products in input order without mutating inputs.

    ``min_stock`` is an inclusive minimum stock threshold when supplied.
    """
    result = []
    for product in products:
        if category is not None and product["category"].lower() != category.lower():
            continue
        if min_stock is not None and product["stock"] < min_stock:
            continue
        result.append(product)
    return result
