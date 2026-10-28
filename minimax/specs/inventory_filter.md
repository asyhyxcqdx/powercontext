# Inventory filtering specification

Version: 1.0
Task: inventory-min-stock-2026
Symbol: filter_products

## Applicable requirement: SDD-STOCK-001 (NEW)

The function `filter_products(products, category=None, min_stock=None)` must support an optional
`min_stock` argument. If provided, retain only products whose integer `stock` is greater than
or equal to `min_stock` (inclusive). A threshold of zero is a meaningful supplied value.
If `min_stock` is `None`, do not apply a stock restriction.
No new arguments or return-format changes are allowed.

## Preservation requirement: SDD-COMPAT-002

Keep the existing optional `category` filter case-insensitive. If both filters are given,
apply both conditions (logical AND). Preserve input order; do not mutate input products,
product dictionaries, or the return type. Unknown categories return an empty list.
Without filters, return a new list with all products in their original order.

## Scope and verification

Change only `workshop/inventory.py` in the sample business project. Target tests are
`tests/test_feature_min_stock.py`; compatibility tests are `tests/test_regression.py`.
The very same tests must run against the before and after code.
