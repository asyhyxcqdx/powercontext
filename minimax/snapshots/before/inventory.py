"""Inventory search for a small retail service."""

from __future__ import annotations


def filter_products(products: list[dict], category: str | None = None,
                    min_stock: int | None = None) -> list[dict]:
    """Return the matching products in input order without mutating inputs.

    `min_stock` is an accepted but not yet implemented business requirement.
    """
    result = []
    for product in products:
        if category is not None and product["category"].lower() != category.lower():
            continue
        result.append(product)
    return result
