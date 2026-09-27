-- Daily health check of the fraud scorer. Replace PROJECT.fraud with your project and dataset.
-- Save in BigQuery as a scheduled query, or open it in Looker Studio for a dashboard.

-- 1. How many decisions of each kind per day, and are they near the planned capacity?
--    Planned shares: STEP-UP 2.8%, HOLD 0.8%, BLOCK 0.4% of traffic.
SELECT DATE(decided_at) AS day, action, COUNT(*) AS decisions,
       ROUND(100 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY DATE(decided_at)), 2) AS pct_of_day
FROM `PROJECT.fraud.decisions`
GROUP BY day, action
ORDER BY day DESC, action;

-- 2. Speed: 95th percentile latency per day (the payment system needs an answer fast)
SELECT DATE(decided_at) AS day, APPROX_QUANTILES(latency_ms, 100)[OFFSET(95)] AS p95_ms, COUNT(*) AS n
FROM `PROJECT.fraud.decisions`
GROUP BY day ORDER BY day DESC;

-- 3. Drift in the mini LLM: is normal wording changing? (a rising average means retrain the mini LLM)
SELECT DATE(decided_at) AS day, ROUND(AVG(llm_surprise_bits), 2) AS avg_surprise,
       COUNTIF(llm_surprise_bits > 4) AS very_surprising
FROM `PROJECT.fraud.decisions`
GROUP BY day ORDER BY day DESC;

-- 4. Are HOLDs worth the analysts' time? Share of reviewed HOLDs that were real fraud, per week.
--    Analysts' verdicts live in their own table (streamed rows cannot be updated straight away).
SELECT DATE_TRUNC(DATE(d.decided_at), WEEK) AS week, COUNT(*) AS reviewed,
       ROUND(100 * COUNTIF(o.analyst_decision = 'FRAUD') / COUNT(*), 1) AS pct_fraud
FROM `PROJECT.fraud.decisions` AS d
JOIN `PROJECT.fraud.outcomes` AS o USING (decision_id)
WHERE d.action = 'HOLD'
GROUP BY week ORDER BY week DESC;
