# Data pull — exact queries

Everything in `data.json` comes from these four calls. They are reproduced verbatim
so the snapshot can be rebuilt or automated without re-deriving anything.

Store: `noro-arts.com` · admin handle `totem-poles` · `aa5f65-ed.myshopify.com`
Timezone EDT (UTC−4). All money USD.

---

## 1. Published products, publish dates, images

Admin GraphQL. Paginate — 58 products come back over two pages.

```graphql
query Published($first: Int!, $after: String) {
  products(first: $first, after: $after, query: "published_status:published", sortKey: PUBLISHED_AT) {
    nodes {
      title
      publishedAt
      featuredImage { url }
    }
    pageInfo { hasNextPage endCursor }
  }
}
```

Feeds `published`, `images`. Image URLs are stored without the `?v=` query string;
`generate.py` appends `?width=260`.

`E-Gift Card` is included in `published` and excluded from all maths.

## 2. Lifetime net revenue per product

Used only to compute the benchmark, which measures each product over its own
lifetime.

```
FROM sales
SHOW net_sales, net_items_sold
GROUP BY product_title
ORDER BY net_sales DESC
SINCE 2024-01-01 UNTIL today
LIMIT 250
```

Feeds `lifetime_net_sales`.

Note: one row comes back with an empty `product_title` and negative net_sales
(unattributed refunds). Discard it.

## 3. Trailing 90 days

```
FROM sales
SHOW net_sales, net_items_sold, returns, discounts
GROUP BY product_title
SINCE -90d UNTIL today
ORDER BY net_sales DESC
LIMIT 250
```

Feeds `d90`. `returns` and `discounts` come back negative; `generate.py` takes the
absolute value.

## 4. Trailing 30 days

```
FROM sales
SHOW net_sales, net_items_sold
GROUP BY product_title
SINCE -30d UNTIL today
ORDER BY net_sales DESC
LIMIT 250
```

Feeds `d30`. Used only for the Trend column.

## 5. Launch window

The 12 launches are the subset of `published` whose `publishedAt` falls between
2026-05-11 and 2026-07-29 inclusive. Their revenue and units *since launch* equal
their 90-day figures, because every one of them has been live under 90 days — verify
this still holds if the window moves.

```graphql
query Launches {
  products(first: 50, query: "published_at:>=2026-05-11 published_at:<=2026-07-29", sortKey: PUBLISHED_AT) {
    nodes { title publishedAt featuredImage { url } }
  }
}
```

Two traps, both documented in CONTEXT.md §5:

- A `published_at` range filter **cannot see products that were later unpublished**,
  because `publishedAt` becomes null. `Skeleton` is one such product.
- `published_at:<=YYYY-MM-DD` may resolve to midnight on that date, so widen the
  upper bound if anything is expected to land on the final day.

## 6. For automation

`shopifyqlQuery` exists on the Admin GraphQL `QueryRoot` (confirmed by schema
introspection), so queries 2–4 can run through the same endpoint as query 1 with a
custom-app token. No need to paginate orders and aggregate line items by hand.

```graphql
query Ql($q: String!) {
  shopifyqlQuery(query: $q) {
    __typename
    ... on TableResponse {
      tableData {
        columns { name dataType displayName }
        rowData
      }
    }
    parseErrors { code message range { start { line character } end { line character } } }
  }
}
```

Scopes to request on the custom app: `read_products`, `read_orders`, `read_reports`.
Confirm the exact analytics scope name in the app's scope picker — ShopifyQL access
is gated on the reports/analytics scope and the name has changed between API
versions.

## 7. Things checked and found unusable

- **Triple Whale MCP** returns *"This Triple Whale shop is not on a plan that
  includes MCP access."* No product-level traffic or attribution.
- **`FROM sessions ... GROUP BY product_title`** is not valid ShopifyQL — sessions
  cannot be grouped by product, so conversion rate per product is unavailable.
- **`ordered_product_quantity`** is not a column in `FROM sales`; the units metric is
  `net_items_sold`.
