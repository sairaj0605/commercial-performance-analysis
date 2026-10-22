-- name: category_margin
SELECT p.category, SUM(t.units) AS units,
 SUM(t.units * t.unit_price_paise) / 100.0 AS revenue_inr,
 SUM(t.units * t.unit_cost_paise) / 100.0 AS cost_inr,
 SUM(t.units * (t.unit_price_paise-t.unit_cost_paise)) / 100.0 AS gross_margin_inr,
 100.0 * SUM(t.units * (t.unit_price_paise-t.unit_cost_paise)) /
 NULLIF(SUM(t.units * t.unit_price_paise),0) AS gross_margin_pct
FROM transactions t JOIN products p USING(sku)
WHERE sale_date <= date(:as_of) GROUP BY p.category ORDER BY revenue_inr DESC;

-- name: monthly_revenue
WITH monthly AS (
 SELECT substr(sale_date,1,7) AS month, SUM(units*unit_price_paise)/100.0 AS revenue_inr
 FROM transactions WHERE sale_date <= date(:as_of) GROUP BY substr(sale_date,1,7)
), previous AS (
 SELECT *, LAG(revenue_inr) OVER(ORDER BY month) AS prior_revenue_inr FROM monthly
)
SELECT *, 100.0*(revenue_inr-prior_revenue_inr)/NULLIF(prior_revenue_inr,0) AS change_pct,
 SUM(revenue_inr) OVER(ORDER BY month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue_inr
FROM previous ORDER BY month;

-- name: customer_concentration
WITH totals AS (
 SELECT c.customer_id,c.region,SUM(t.units*t.unit_price_paise)/100.0 AS revenue_inr
 FROM transactions t JOIN customers c USING(customer_id)
 WHERE sale_date <= date(:as_of) GROUP BY c.customer_id,c.region
)
SELECT *, DENSE_RANK() OVER(ORDER BY revenue_inr DESC) AS revenue_rank,
 100.0*revenue_inr/SUM(revenue_inr) OVER() AS revenue_share_pct
FROM totals ORDER BY revenue_inr DESC, customer_id;

-- name: below_cost_lines
SELECT line_id,sku,customer_id,sale_date,units,unit_price_paise,unit_cost_paise,
 units*(unit_cost_paise-unit_price_paise)/100.0 AS below_cost_gap_inr
FROM transactions WHERE unit_price_paise < unit_cost_paise AND sale_date <= date(:as_of)
ORDER BY below_cost_gap_inr DESC;
