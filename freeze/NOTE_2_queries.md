# Clean-copy queries of the second freeze's design searches (#149)

Read-only queries run by sub-agents on 2026-10-28 on the clean copies, as each recorded them, translated into English where needed. They are disclosed with `freeze/NOTE_2.md`; none ran on an injected copy. Data derived from LiveSQLBench-Base-Lite, CC BY-SA 4.0.

`<scratch>` below is the design session's scratch directory. It is not in the repo. Every copy queried had the SHA-256 given in `release.sha256.<db>` of `freeze/write_line_2.yaml` and was opened read-only.

## The lever-B search: coverage cuts the battery would settle

### Not recommended (the best of the crypto date cuts, still fails): orders keeps only orders created on 2025-02-19 UTC, cut with its child tables (today-orders)

Finder:

All run with python3 -I through sqlite3.connect('file:<scratch>/vm61/crypto_clean.sqlite?mode=ro', uri=True). No query on alien_clean.sqlite. Before the queries, both copies were checked with shasum -a 256; both match freeze/write_line.yaml:20-21.
1. SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name
2. SELECT timecode, createspot, updatespot, timespan, orderflow, exchspot, mktnote, orderstamp, ordertune, dealedge, orderbase, clientmark FROM orders LIMIT 5
3. SELECT expirespot, cancelnote, exectune FROM orderexecutions LIMIT 5
4. SELECT fundspot FROM marketstats LIMIT 5
5. SELECT lastupdnote, seqcode, wsstate FROM systemmonitoring LIMIT 5
6. SELECT substr(quote_depth_snapshot,1,300) FROM marketdata LIMIT 2
7. SELECT substr(market_sentiment_indicators,1,300) FROM analyticsindicators LIMIT 2
8. SELECT substr(risk_margin_profile,1,300) FROM riskandmargin LIMIT 2
9. SELECT COUNT(*), COUNT(DISTINCT timecode), MIN(timecode), MAX(timecode) FROM orders
10. SELECT COUNT(*), COUNT(createspot), COUNT(DISTINCT createspot), MIN(createspot), MAX(createspot) FROM orders
11. Same as 10, with the column changed to updatespot (FROM orders)
12. Same as 10, with the column changed to expirespot (FROM orderexecutions)
13. Same as 10, with the column changed to fundspot (FROM marketstats)
14. SELECT substr(createspot,1,10) d, COUNT(*) FROM orders GROUP BY d ORDER BY d
15. SELECT substr(expirespot,1,10) d, COUNT(*) FROM orderexecutions GROUP BY d ORDER BY d
16. SELECT fundspot, COUNT(*) FROM marketstats GROUP BY 1 ORDER BY 1
17. SELECT timecode=updatespot, COUNT(*) FROM orders GROUP BY 1
18–23. Run once for each of (marketdata, quote_depth_snapshot), (analyticsindicators, market_sentiment_indicators) and (riskandmargin, risk_margin_profile): SELECT <col> FROM <t> LIMIT 1; SELECT COUNT(*) FROM <t> WHERE <col> GLOB '*20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]*'
24. SELECT MIN(json_extract(quote_depth_snapshot,'$.metadata.timetrack')), MAX(...), COUNT(DISTINCT ...) FROM marketdata
25. SELECT timecode, COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC LIMIT 5
26. SELECT COUNT(*) FROM (SELECT userlink FROM orders GROUP BY userlink HAVING COUNT(*)>1)
27. SELECT COUNT(DISTINCT orderslink), COUNT(*) FROM fees
28. SELECT COUNT(DISTINCT ordersmark), COUNT(*) FROM orderexecutions
29. SELECT COUNT(DISTINCT ordervault), COUNT(*) FROM riskandmargin
30. SELECT (SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM fees f WHERE f.orderslink=o.recordvault)), (the same with orderexecutions.ordersmark), (the same with riskandmargin.ordervault)
31. SELECT COUNT(*), COUNT(DISTINCT timecode), COUNT(DISTINCT updatespot), MIN(createspot), MAX(createspot) FROM orders WHERE createspot >= '2025-02-19 00:00:00'
32. SELECT MAX(n)*1.0/SUM(n) FROM (SELECT timecode, COUNT(*) n FROM orders WHERE createspot >= '2025-02-19 00:00:00' GROUP BY 1)
33. SELECT COUNT(*), COUNT(DISTINCT timecode), COUNT(DISTINCT updatespot) FROM orders WHERE NOT (createspot >= '2025-02-19 00:00:00')
34. SELECT (SELECT COUNT(*) FROM orderexecutions WHERE ordersmark IN (SELECT recordvault FROM orders WHERE createspot >= '2025-02-19 00:00:00')), (the same with fees.orderslink), (the same with riskandmargin.ordervault)
35. SELECT recordvault FROM orders WHERE recordvault IN (SELECT orderslink FROM fees GROUP BY 1 HAVING COUNT(*)>1)
36. SELECT createspot FROM orders WHERE recordvault IN (SELECT orderslink FROM fees GROUP BY 1 HAVING COUNT(*)>1)
37. SELECT (SELECT COUNT(*) FROM users WHERE userstamp NOT IN (SELECT userlink FROM orders WHERE createspot >= '2025-02-19 00:00:00'))
38. SELECT substr(createspot,12,2) h, COUNT(*) FROM orders GROUP BY substr(createspot,1,13) ORDER BY substr(createspot,1,13)
39. SELECT COUNT(*) FROM marketdata m JOIN orders o ON o.orderspivot = m.marketdatanode AND trim(o.exchspot)=trim(json_extract(m.quote_depth_snapshot,'$.metadata.exchnote')) AND o.mktnote=json_extract(m.quote_depth_snapshot,'$.metadata.mktcombo')
40. SELECT COUNT(DISTINCT trim(json_extract(quote_depth_snapshot,'$.metadata.exchnote'))||'|'||json_extract(quote_depth_snapshot,'$.metadata.mktcombo')) FROM marketdata
41. SELECT MIN(orderspivot), MAX(orderspivot), MIN(marketdatanode), MAX(marketdatanode) FROM orders, (SELECT MIN(marketdatanode) marketdatanode FROM marketdata)
42. SELECT o.orderflow, COUNT(*), ROUND(AVG(a.frozensum),2), SUM(a.frozensum=0) FROM orders o JOIN accountbalances a ON a.usertag=o.userlink GROUP BY 1
43. SELECT substr(o.createspot,1,10), COUNT(*), ROUND(AVG(a.frozensum),2) FROM orders o JOIN accountbalances a ON a.usertag=o.userlink GROUP BY 1
44. SELECT COUNT(*) FROM orders a JOIN orders b ON b.orderspivot = a.orderspivot + 1 WHERE b.createspot > a.createspot
45. SELECT COUNT(*) FROM orders a JOIN orders b ON b.orderspivot = a.orderspivot + 1
46. SELECT MIN(orderspivot), MAX(orderspivot) FROM orders WHERE createspot >= '2025-02-19 00:00:00'
47. SELECT orderflow, COUNT(*) FROM orders WHERE createspot >= '2025-02-19 00:00:00' GROUP BY 1
48. SELECT orderflow, COUNT(*) FROM orders WHERE createspot < '2025-02-19 00:00:00' GROUP BY 1
49. SELECT ROUND(SUM(f.feetotal),6), COUNT(*) FROM fees f JOIN orders o ON o.recordvault=f.orderslink WHERE o.createspot < '2025-02-19 00:00:00'
50. Same as 49, with the condition changed to >= '2025-02-19 00:00:00'
51. SELECT ROUND(SUM(notionsum),3) FROM orders WHERE createspot < '2025-02-19 00:00:00'
52. Same as 51, with the condition changed to >= '2025-02-19 00:00:00'
53. SELECT ROUND(SUM(notionsum),3) FROM orders
54. SELECT substr(createspot,1,13), COUNT(*) FROM orders WHERE createspot < '2025-02-19' GROUP BY 1 ORDER BY 2 DESC LIMIT 3
55. SELECT COUNT(*) FROM orders WHERE createspot >= '2025-02-18 20:00:00'
56. SELECT COUNT(*) FROM orders WHERE createspot >= '2025-02-19 04:00:00'

Read-only actions that are not SQL:
- Read docs/research/clean-scan.json and results/thin/2026-10-24-66a86cb.jsonl.
- Read the release's crypto_column_meaning_base.json (in ~/.cache/warrant/livesqlbench-base-lite/0664a2f.../crypto/).
No file written, no copy made, no battery or model run, and no git, GitHub, AWS or MCP use.

Verifier:

All run with python3 -I through sqlite3.connect('file:<scratch>/vm61/crypto_clean.sqlite?mode=ro', uri=True). Before the queries, both copies were checked with shasum -a 256; both match freeze/write_line.yaml:20-21. No query on alien_clean.sqlite.

Q0. List the schema and the foreign keys: SELECT name FROM sqlite_master WHERE type='table' ORDER BY name; for each table, SELECT COUNT(*), PRAGMA table_info, PRAGMA foreign_key_list
Q1. SELECT COUNT(*), COUNT(createspot), COUNT(DISTINCT createspot), MIN(createspot), MAX(createspot) FROM orders
Q2. SELECT substr(createspot,1,10) d, COUNT(*) FROM orders GROUP BY d ORDER BY d
Q3. SELECT COUNT(*), COUNT(DISTINCT timecode), COUNT(DISTINCT updatespot), MIN(timecode), MAX(timecode), MIN(updatespot), MAX(updatespot) FROM orders
Q4. SELECT COUNT(*), COUNT(DISTINCT timecode), COUNT(DISTINCT updatespot), COUNT(DISTINCT userlink), MIN(createspot), MAX(createspot) FROM orders WHERE createspot >= '2025-02-19 00:00:00'
Q5. SELECT COUNT(*) FROM orders WHERE createspot IS NULL OR createspot = ''
Q6. For each of the three child tables, SELECT COUNT(*) ... WHERE <fk> IN (SELECT recordvault FROM orders WHERE createspot < '2025-02-19 00:00:00')
Q7. For each of the three child tables, SELECT COUNT(*) ... WHERE <fk> NOT IN (SELECT recordvault FROM orders)
Q8. SELECT COUNT(DISTINCT <fk>), once each for fees, orderexecutions and riskandmargin
Q9-11. SELECT <fk>, COUNT(*) FROM <child table> GROUP BY 1 HAVING COUNT(*)>1, once for each of the three tables
Q12. SELECT recordvault, createspot FROM orders WHERE recordvault IN (SELECT orderslink FROM fees GROUP BY 1 HAVING COUNT(*)>1)
Q13. SELECT COUNT(*) FROM users WHERE userstamp NOT IN (SELECT userlink FROM orders WHERE createspot >= '2025-02-19 00:00:00')
Q14. SELECT COUNT(*) FROM users WHERE userstamp NOT IN (SELECT userlink FROM orders)
Q15. For each of the three child tables, SELECT COUNT(*) FROM orders o WHERE createspot >= '2025-02-19 00:00:00' AND NOT EXISTS (SELECT 1 FROM <child table> f WHERE f.<fk>=o.recordvault)
Q17-24. Run twice on each of orders, fees, orderexecutions and riskandmargin (once without a condition, once with the keep condition): SELECT COUNT(*), and for each column COUNT(DISTINCT "c") and SUM("c" IS NULL OR "c"='') FROM <t> [WHERE createspot >= '2025-02-19 00:00:00'; for the child tables, <fk> IN (SELECT recordvault FROM orders WHERE createspot >= '2025-02-19 00:00:00')]
Q25. SELECT substr(quote_depth_snapshot,1,400) FROM marketdata LIMIT 1
Q26. SELECT MIN(orderspivot), MAX(orderspivot), (SELECT MIN(marketdatanode) FROM marketdata), (SELECT MAX(marketdatanode) FROM marketdata) FROM orders
Q27. SELECT COUNT(*) FROM marketdata m JOIN orders o ON o.orderspivot = m.marketdatanode AND trim(o.exchspot)=trim(json_extract(m.quote_depth_snapshot,'$.metadata.exchnote')) AND o.mktnote=json_extract(m.quote_depth_snapshot,'$.metadata.mktcombo')
Q28. SELECT COUNT(*) FROM marketdata m JOIN orders o ON o.orderspivot = m.marketdatanode
Q29. SELECT COUNT(DISTINCT trim(json_extract(quote_depth_snapshot,'$.metadata.exchnote'))||'|'||json_extract(quote_depth_snapshot,'$.metadata.mktcombo')) FROM marketdata
Q30. SELECT MIN/MAX/COUNT(DISTINCT json_extract(quote_depth_snapshot,'$.metadata.timetrack')) FROM marketdata
Q31. SELECT COUNT(*) FROM marketdata m JOIN orders o ON o.orderspivot = m.marketdatanode WHERE json_extract(m.quote_depth_snapshot,'$.metadata.timetrack') = o.timecode
Q32. SELECT marketdatanode FROM marketdata WHERE marketdatanode NOT IN (SELECT orderspivot FROM orders)
Q33. SELECT COUNT(*) FROM marketdata m WHERE m.marketdatanode IN (SELECT orderspivot FROM orders WHERE createspot >= '2025-02-19 00:00:00')
Q34. SELECT substr(risk_margin_profile,1,400) FROM riskandmargin LIMIT 1
Q35. SELECT substr(market_sentiment_indicators,1,300) FROM analyticsindicators LIMIT 1
Q36-38. SELECT COUNT(*) FROM <t> WHERE <json column> GLOB '*20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]*', once each for riskandmargin, analyticsindicators and marketdata
Q39. SELECT fundspot, COUNT(*) FROM marketstats GROUP BY 1 ORDER BY 1
Q40. SELECT lastupdnote, seqcode FROM systemmonitoring LIMIT 3
Q41. SELECT orderstamp, clientmark, exchspot FROM orders LIMIT 3
Q42. Same as Q31, but with replace(timetrack,'T',' ') applied before the comparison
Q43. SELECT COUNT(*) FROM orders WHERE createspot >= '2025-02-18 20:00:00'
Q44. SELECT COUNT(*) FROM orders WHERE createspot >= '2025-02-18 00:00:00' AND createspot < '2025-02-19 00:00:00'
Q45. Same as Q44, with the upper bound changed to '2025-02-18 20:00:00'
Q46. SELECT orderflow, COUNT(*) FROM orders WHERE createspot >= '2025-02-19 00:00:00' GROUP BY 1 ORDER BY 1
Q47. Same as Q46, with the condition changed to < '2025-02-19 00:00:00'
Q48. SELECT ROUND(SUM(f.feetotal),6), COUNT(*) FROM fees f JOIN orders o ON o.recordvault=f.orderslink WHERE o.createspot < '2025-02-19 00:00:00'
Q49. Same as Q48, with the condition changed to >=
Q50. SELECT ROUND(SUM(notionsum),3) FROM orders WHERE createspot < '2025-02-19 00:00:00'
Q51. Same as Q50, with the condition changed to >=
Q52. SELECT ROUND(SUM(notionsum),3) FROM orders
Q53. SELECT substr(createspot,1,13), COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT 4
Q54. Same as Q53, plus WHERE createspot >= '2025-02-19 00:00:00'
Q55. Same as Q53, plus WHERE createspot >= '2025-02-18 20:00:00' (LIMIT 3)
Q56. SELECT ROUND(100.0*COUNT(DISTINCT userlink)/(SELECT COUNT(*) FROM users),2) FROM orders
Q57. Same as Q56, plus WHERE createspot >= '2025-02-19 00:00:00'
Q58. SELECT COUNT(*) FROM orders WHERE createspot >= '2025-02-18 08:29:46'
Q59. SELECT ROUND(SUM(f.feetotal),6) FROM fees f JOIN orders o ON o.recordvault=f.orderslink
Q60. SELECT COUNT(*) FROM orders WHERE orderflow='Cancelled' AND createspot >= '2025-02-19 00:00:00'
Q61. SELECT COUNT(*), SUM(frozensum>0), MIN(frozensum) FROM accountbalances
Q62. SELECT o.orderflow, COUNT(*), ROUND(AVG(a.frozensum),2), SUM(a.frozensum=0) FROM orders o JOIN accountbalances a ON a.usertag=o.userlink GROUP BY 1 ORDER BY 1
Q63. Same as Q62, but grouped by kept or cut (createspot >= '2025-02-19 00:00:00')
Q64. SELECT COUNT(*) FROM orders a JOIN orders b ON b.orderspivot = a.orderspivot + 1 WHERE b.createspot > a.createspot
Q65. Same as Q64, without the WHERE
Q66. SELECT MIN(orderspivot), MAX(orderspivot) FROM orders WHERE createspot >= '2025-02-19 00:00:00'
Q67. SELECT COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE e.expirespot < o.createspot
Q68. SELECT MIN(e.expirespot), MAX(e.expirespot) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE o.createspot >= '2025-02-19 00:00:00'
Q69. SELECT COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE e.expirespot < '2025-02-19 08:29:46' AND o.orderflow IN ('New','PartiallyFilled')
Q70. SELECT o.orderflow, e.cancelnote IS NULL, COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark GROUP BY 1,2 ORDER BY 1,2
Q71. SELECT COUNT(*) FROM orders WHERE createspot > timecode
Q72. SELECT acctscope, COUNT(*) FROM users WHERE userstamp NOT IN (SELECT userlink FROM orders WHERE createspot >= '2025-02-19 00:00:00') GROUP BY 1 ORDER BY 1
Q73. SELECT u.acctscope, COUNT(*) FROM orders o JOIN users u ON u.userstamp=o.userlink WHERE o.createspot >= '2025-02-19 00:00:00' GROUP BY 1 ORDER BY 1
Q74. SELECT MIN(n), MAX(n), COUNT(*) FROM (SELECT substr(createspot,1,13) h, COUNT(*) n FROM orders GROUP BY 1)
Q75. SELECT substr(createspot,1,13) h, COUNT(*) n FROM orders GROUP BY 1 ORDER BY 2 LIMIT 3

Read-only actions that are not SQL:
- Read the crypto findings in docs/research/clean-scan.json.
- Read the confident crypto samples in results/thin/2026-10-24-66a86cb.jsonl.
- Read ~/.cache/warrant/livesqlbench-base-lite/0664a2f28555faa0dd2947c8c23288df79bcc06b/crypto/crypto_column_meaning_base.json.
- Read the repo code and the design files in `<scratch>`.

No file written, no copy made, no battery, DuckDB or model run, and no git, GitHub, AWS or MCP use.

### orderexecutions-api-cut: orderexecutions loses the fills of orders placed through the API (cut by the order channel orders.orderbase)

Finder:

All run with sqlite3 'file:<scratch>/vm61/crypto_clean.sqlite?mode=ro' (a first attempt with the -uri flag was refused and ran no query). No query on alien. The hashes were also checked with shasum.
(0) .schema
(1) SELECT acctscope, COUNT(*) FROM users GROUP BY 1 ORDER BY 2 DESC;
(2) SELECT orderbase, COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC;
(3) SELECT COUNT(DISTINCT exchspot), MIN(exchspot), MAX(exchspot) FROM orders;
(4) SELECT exchspot, COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC LIMIT 15;
(6) SELECT COUNT(*), COUNT(DISTINCT ordersmark) FROM orderexecutions;
(7) SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM orderexecutions e WHERE e.ordersmark = o.recordvault);
(8) SELECT o.orderbase, COUNT(*) AS exec_rows, COUNT(DISTINCT e.ordersmark) AS orders_ref FROM orderexecutions e JOIN orders o ON e.ordersmark = o.recordvault GROUP BY 1 ORDER BY 1;
(9) SELECT recordvault, orderbase, orderflow, userlink FROM orders WHERE TRIM(recordvault) = 'OB102450';
(10) SELECT orderbase, orderflow, COUNT(*) FROM orders GROUP BY 1,2 ORDER BY 1,2;
(11) SELECT o.orderbase, e.exectune, COUNT(*) FROM orderexecutions e JOIN orders o ON e.ordersmark=o.recordvault GROUP BY 1,2 ORDER BY 1,2;
(12) SELECT COUNT(*) AS n, COUNT(DISTINCT fillcount) AS fc, COUNT(DISTINCT remaincount) AS rc, COUNT(DISTINCT fillquote) AS fq, COUNT(DISTINCT fillsum) AS fs, COUNT(DISTINCT expirespot) AS ex, COUNT(DISTINCT cancelnote) AS cn, COUNT(DISTINCT exectune) AS et, COUNT(DISTINCT ordersmark) AS om FROM orderexecutions;
(13) SELECT COUNT(*) AS n, COUNT(DISTINCT fillcount) AS fc, COUNT(DISTINCT remaincount) AS rc, COUNT(DISTINCT fillquote) AS fq, COUNT(DISTINCT fillsum) AS fs, COUNT(DISTINCT expirespot) AS ex, COUNT(DISTINCT ordersmark) AS om FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API');
(14) SELECT cancelnote, COUNT(*) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API') GROUP BY 1 ORDER BY 2 DESC, 1;
(15) SELECT exectune, COUNT(*) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API') GROUP BY 1 ORDER BY 2 DESC, 1;
(16) SELECT expirespot FROM orderexecutions LIMIT 5;
(17) SELECT COUNT(*) AS fee_rows, COUNT(DISTINCT f.orderslink) AS orders, SUM(f.feetotal > 0) AS positive_fee, MIN(f.feetotal) AS min_fee FROM fees f JOIN orders o ON o.recordvault = f.orderslink WHERE o.orderbase = 'API';
(18) SELECT COUNT(*) AS risk_rows, COUNT(DISTINCT r.ordervault) AS orders FROM riskandmargin r JOIN orders o ON o.recordvault = r.ordervault WHERE o.orderbase = 'API';
(19) SELECT o.orderflow, COUNT(*) AS n, SUM(e.fillcount > 0) AS with_fill, ROUND(AVG(e.fillcount),3) AS avg_fill FROM orderexecutions e JOIN orders o ON o.recordvault = e.ordersmark GROUP BY 1 ORDER BY 1;
(20) SELECT SUM(ABS(f.feetotal - f.feerate * e.fillsum) < 0.01) AS holds, COUNT(*) AS n FROM fees f JOIN orderexecutions e ON e.orderexecmark = f.feesnode;
(21) SELECT SUM(ABS(f.feetotal - f.feerate * e.fillsum) < 0.01) AS holds, COUNT(*) AS n FROM fees f JOIN orderexecutions e ON e.ordersmark = f.orderslink;
(22) SELECT o.orderbase, ROUND(SUM(f.feetotal),6) AS fees, COUNT(*) AS fee_rows FROM fees f JOIN orders o ON o.recordvault = f.orderslink GROUP BY 1 ORDER BY 1;
(23) SELECT o.orderbase, ROUND(SUM(e.fillcount),4) AS fillqty, ROUND(SUM(e.fillsum),3) AS fillnotional, SUM(e.exectune='Taker') AS taker, SUM(e.exectune='Maker') AS maker, SUM(e.exectune IS NULL) AS untagged FROM orderexecutions e JOIN orders o ON o.recordvault = e.ordersmark GROUP BY 1 ORDER BY 1;
(24) SELECT ROUND(SUM(fillcount),4) AS fillqty_all, ROUND(SUM(fillsum),3) AS notional_all, SUM(exectune='Maker') AS maker_all, SUM(exectune='Taker') AS taker_all FROM orderexecutions;
(25) SELECT u.acctscope, o.orderbase, COUNT(*) FROM orders o JOIN users u ON u.userstamp = o.userlink GROUP BY 1,2 ORDER BY 1,2;
(26) SELECT COUNT(*) AS orders_unreferenced FROM (SELECT DISTINCT recordvault FROM orders) m WHERE m.recordvault NOT IN (SELECT ordersmark FROM orderexecutions WHERE ordersmark IS NOT NULL AND ordersmark <> '' AND ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase = 'API'));
(27) SELECT ROUND(SUM(fillcount),4) AS fillqty_non_api, SUM(exectune='Maker') AS maker_non_api, COUNT(*) AS rows_non_api, ROUND(AVG(CASE WHEN o.orderbase='Web' THEN fillcount END),4) AS avg_web_fill FROM orderexecutions e JOIN orders o ON o.recordvault = e.ordersmark WHERE o.orderbase <> 'API';
(28) SELECT MIN(walletsum), MIN(availsum + frozensum) FROM accountbalances;
(29) SELECT u.acctscope, COUNT(*) AS bal_rows FROM accountbalances a JOIN users u ON u.userstamp = a.usertag GROUP BY 1 ORDER BY 1;
(30) SELECT COUNT(*) FROM orderexecutions WHERE ordersmark IS NULL OR ordersmark = '';
(31) SELECT MIN(orderexecmark), MAX(orderexecmark), COUNT(*) FROM orderexecutions;
(32) SELECT COUNT(*) AS rows_cut, COUNT(DISTINCT ordersmark) AS orders_cut FROM orderexecutions WHERE orderexecmark > 766;
(33) SELECT COUNT(*) FROM (SELECT DISTINCT recordvault FROM orders) m WHERE m.recordvault NOT IN (SELECT ordersmark FROM orderexecutions WHERE orderexecmark <= 766);
(34) SELECT cancelnote, COUNT(*) FROM orderexecutions WHERE orderexecmark <= 766 GROUP BY 1 ORDER BY 2 DESC, 1;
(35) SELECT exectune, COUNT(*) FROM orderexecutions WHERE orderexecmark <= 766 GROUP BY 1 ORDER BY 2 DESC, 1;
(36) SELECT SUM(e.orderexecmark = f.feesnode AND e.ordersmark = f.orderslink) AS aligned, COUNT(*) FROM orderexecutions e JOIN fees f ON f.feesnode = e.orderexecmark;
(37) SELECT COUNT(*) AS maker_rows, COUNT(DISTINCT ordersmark) AS maker_orders FROM orderexecutions WHERE exectune = 'Maker';
(38) SELECT ROUND(SUM(f.feetotal),6) AS tail_fees FROM fees f WHERE f.orderslink NOT IN (SELECT ordersmark FROM orderexecutions WHERE orderexecmark <= 766);
(39) SELECT COUNT(*) AS api_taker_kept_under_tail FROM orderexecutions e JOIN orders o ON o.recordvault = e.ordersmark WHERE o.orderbase = 'API' AND e.exectune = 'Taker' AND e.orderexecmark <= 766;
(40) SELECT COUNT(*) AS api_orders_in_tail FROM orders o WHERE o.orderbase = 'API' AND o.recordvault NOT IN (SELECT ordersmark FROM orderexecutions WHERE orderexecmark <= 766);

Verifier:

All on crypto, run with sqlite3 'file:<scratch>/vm61/crypto_clean.sqlite?mode=ro'; the Python part used sqlite3.connect(the same URI, uri=True). No query on alien.
The hash was checked with shasum -a 256 before and after the run. Both times it was 49103c15…a5e1, which matches write_line.yaml:20, and no -wal or -shm file appeared.
Some further things to disclose:
- I wrote a helper script, <scratch>/c61_rule_probe.py. It is a new file, not an edit of an existing one.
- I called warrant.freeze.validate.reference_claim_problems with python -I. It is a pure function and does not touch the database.
- I read docs/research/clean-scan.json and results/thin/2026-10-24-66a86cb.jsonl.
No git, no injection, no battery or predict run, and no model, AWS or MCP call.

V0 .schema
V1 SELECT orderbase, COUNT(*) FROM orders GROUP BY 1 ORDER BY 2 DESC;
V2 SELECT COUNT(*), COUNT(DISTINCT recordvault), COUNT(DISTINCT TRIM(recordvault)) FROM orders;
V3 SELECT COUNT(*), COUNT(DISTINCT ordersmark) FROM orderexecutions;
V4 SELECT o.orderbase, COUNT(*) AS exec_rows, COUNT(DISTINCT e.ordersmark) AS orders_ref FROM orderexecutions e JOIN orders o ON e.ordersmark = o.recordvault GROUP BY 1 ORDER BY 1;
V5 SELECT COUNT(*) FROM orders o WHERE NOT EXISTS (SELECT 1 FROM orderexecutions e WHERE e.ordersmark = o.recordvault);
V6 SELECT ordersmark, COUNT(*) FROM orderexecutions GROUP BY 1 HAVING COUNT(*)>1;
V7 SELECT orderslink, COUNT(*) FROM fees GROUP BY 1 HAVING COUNT(*)>1; SELECT ordervault, COUNT(*) FROM riskandmargin GROUP BY 1 HAVING COUNT(*)>1;
V8 SELECT COUNT(*) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders);
V9 SELECT COUNT(*) AS kept, COUNT(DISTINCT ordersmark) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API');
V10 SELECT orderbase, orderflow, COUNT(*) FROM orders WHERE orderbase='API' GROUP BY 1,2 ORDER BY 1,2;
V11 SELECT COUNT(*) AS fee_rows, SUM(f.feetotal > 0) AS pos, MIN(f.feetotal) FROM fees f JOIN orders o ON o.recordvault=f.orderslink WHERE o.orderbase='API';
V12 SELECT COUNT(*) FROM riskandmargin r JOIN orders o ON o.recordvault=r.ordervault WHERE o.orderbase='API';
V13 SELECT SUM(ABS(f.feetotal - f.feerate*e.fillsum) < 0.01) AS holds, SUM(e.orderexecmark=f.feesnode AND e.ordersmark=f.orderslink) AS aligned, COUNT(*) FROM fees f JOIN orderexecutions e ON e.orderexecmark=f.feesnode;
V14 SELECT SUM(ABS(e.fillsum - e.fillcount*e.fillquote) < 0.01), SUM(ABS(e.fillcount + e.remaincount - o.dealcount) < 0.0001), SUM(ABS(e.fillquote - o.dealquote) < 0.001), COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark;
V15 SELECT SUM(ABS(o.notionsum - o.dealquote*o.dealcount) < 0.01), SUM(ABS(o.notionsum - e.fillsum) < 0.01), COUNT(*) FROM orders o JOIN orderexecutions e ON o.recordvault=e.ordersmark;
V16 SELECT ROUND(MIN(rebrate),5), ROUND(MAX(rebrate),5), ROUND(MIN(feerate),5), ROUND(MAX(feerate),5), SUM(ABS(rebtotal - rebrate*feetotal/feerate) < 0.01) FROM fees;
V17 SELECT e.exectune, COUNT(*), ROUND(AVG(f.feerate),6), ROUND(AVG(f.rebrate),6), SUM(f.rebrate>0), f2.feerange FROM orderexecutions e JOIN fees f ON f.feesnode=e.orderexecmark LEFT JOIN (SELECT NULL AS feerange) f2 GROUP BY 1 ORDER BY 1;
V18 SELECT e.exectune, f.feerange, COUNT(*) FROM orderexecutions e JOIN fees f ON f.feesnode=e.orderexecmark GROUP BY 1,2 ORDER BY 1,2;
V19 SELECT o.orderflow, COUNT(*), SUM(e.fillcount>0), SUM(e.remaincount>0), SUM(e.cancelnote IS NOT NULL) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark GROUP BY 1 ORDER BY 1;
V20 SELECT o.ordertune, e.exectune, COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark GROUP BY 1,2 ORDER BY 1,2;
V21 SELECT COUNT(DISTINCT expirespot), MIN(expirespot), MAX(expirespot), SUM(expirespot IS NULL OR expirespot='') FROM orderexecutions;
V22 SELECT expirespot, COUNT(*) FROM orderexecutions GROUP BY 1 ORDER BY 2 DESC LIMIT 5;
V23 SELECT typeof(fillcount), typeof(remaincount), typeof(fillquote), typeof(fillsum), typeof(orderexecmark), COUNT(*) FROM orderexecutions GROUP BY 1,2,3,4,5;
V24 SELECT SUM(fillcount<0), SUM(remaincount<0), SUM(fillquote<0), SUM(fillsum<0), SUM(fillcount=0), SUM(remaincount=0), SUM(fillsum=0) FROM orderexecutions;
V25 SELECT COUNT(DISTINCT fillcount), COUNT(DISTINCT remaincount), COUNT(DISTINCT fillquote), COUNT(DISTINCT fillsum), COUNT(DISTINCT expirespot) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API');
PY (c61_rule_probe.py), three queries: SELECT orderexecmark, fillcount, remaincount, fillquote, fillsum FROM orderexecutions WHERE {1=1 | ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API') | orderexecmark <= 766}. Then, in Python, it searches the 2-term and 3-term combinations the way rule.py does, with a tolerance of 0.005, on the rows whose target is not 0. The helper only ran the SELECT statements listed above; its code is in the section "Helper scripts".
V26 SELECT cancelnote, COUNT(*) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API') GROUP BY 1 ORDER BY 2 DESC, 1;
V27 Same as V26, but on exectune.
V28 SELECT ROUND(100.0*SUM(cancelnote IS NULL OR cancelnote='')/COUNT(*),1), ROUND(100.0*SUM(exectune IS NULL OR exectune='')/COUNT(*),1) FROM orderexecutions WHERE ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API');
V29 Same as V28, plus COUNT(*) and COUNT(DISTINCT ordersmark), with the condition changed to WHERE orderexecmark <= 766.
V30 SELECT cancelnote, COUNT(*) FROM orderexecutions WHERE orderexecmark <= 766 GROUP BY 1 ORDER BY 2 DESC, 1;
V31 Same as V30, but on exectune.
V32 SELECT MIN(orderexecmark), MAX(orderexecmark), COUNT(*), COUNT(DISTINCT orderexecmark) FROM orderexecutions;
V33 SELECT COUNT(*) FROM (SELECT DISTINCT recordvault FROM orders) m WHERE m.recordvault NOT IN (SELECT ordersmark FROM orderexecutions WHERE orderexecmark <= 766);
V34-V39: B takes API, Web, Mobile and Bot in turn, and K = "ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='B')"
 V34 SELECT COUNT(DISTINCT ordersmark) FROM orderexecutions WHERE K;
 V35 SELECT ROUND(COALESCE(SUM(feetotal),0),6) FROM fees WHERE orderslink NOT IN (SELECT ordersmark FROM orderexecutions WHERE K);
 V36 SELECT COUNT(*), COUNT(DISTINCT e.ordersmark) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE K AND o.orderbase='API' AND e.exectune='Taker';
 V37 SELECT ROUND(SUM(fillcount),4) FROM orderexecutions WHERE K;
 V38 SELECT COUNT(*) FROM orders WHERE orderbase='API' AND recordvault NOT IN (SELECT ordersmark FROM orderexecutions WHERE K);
 V39 SELECT COUNT(*), COUNT(DISTINCT ordersmark) FROM orderexecutions WHERE K AND exectune='Maker';
V40 SELECT (SELECT COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE o.orderbase='API' AND e.exectune='Taker'), (SELECT ROUND(SUM(fillcount),4) FROM orderexecutions), (SELECT COUNT(*) FROM orderexecutions WHERE exectune='Maker'), (SELECT COUNT(DISTINCT ordersmark) FROM orderexecutions WHERE exectune='Maker');
V41 SELECT riskandmarginpivot, ordervault, risk_margin_profile FROM riskandmargin LIMIT 2;
V42 SELECT SUM(r.riskandmarginpivot = e.orderexecmark AND r.ordervault = e.ordersmark), COUNT(*) FROM riskandmargin r JOIN orderexecutions e ON e.orderexecmark = r.riskandmarginpivot;
V43 SELECT orderspivot, recordvault, timecode, exchspot, mktnote, orderstamp, userlink, dealquote, dealcount, notionsum, orderflow, orderbase, clientmark, createspot, updatespot FROM orders LIMIT 2;
V44 SELECT e.orderexecmark, e.fillcount, e.remaincount, e.fillquote, e.fillsum, o.dealcount, o.dealquote, o.notionsum, json_extract(r.risk_margin_profile,'$.position.poscount'), json_extract(...'$.position.possum'), json_extract(...'$.iceberg.viscount'), json_extract(...'$.iceberg.icebcount'), json_extract(...'$.margin_thresholds.inithold') FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark JOIN riskandmargin r ON r.riskandmarginpivot=e.orderexecmark LIMIT 4;
V45 SELECT SUM(ABS(inithold - o.notionsum) < 0.01), SUM(ABS(poscount - e.fillcount) < 0.001), SUM(ABS(possum - e.fillsum) < 0.01), SUM(ABS(viscount + icebcount - o.dealcount) < 0.001), SUM(ABS(viscount - e.fillcount) < 0.001), COUNT(*), with the same join as V44 (each column taken out with json_extract).
V46 SELECT u.acctscope, SUM(o.orderbase='API'), COUNT(*) FROM orders o JOIN users u ON u.userstamp=o.userlink GROUP BY 1 ORDER BY 1;
V47 SELECT o.ordertune, SUM(o.orderbase='API'), COUNT(*) FROM orders o GROUP BY 1;
V48 SELECT o.timespan, SUM(o.orderbase='API'), COUNT(*) FROM orders o GROUP BY 1;
V49 SELECT f.feecoin, f.feerange, SUM(o.orderbase='API'), COUNT(*) FROM fees f JOIN orders o ON o.recordvault=f.orderslink GROUP BY 1,2 ORDER BY 1,2;
V50 SELECT MIN(e.orderexecmark), MAX(e.orderexecmark) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE o.orderbase='API';
V51 SELECT SUM(e.orderexecmark = o.orderspivot), COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark;
V52 SELECT ROUND(SUM(f.feetotal),6) FROM fees f WHERE f.orderslink NOT IN (SELECT ordersmark FROM orderexecutions WHERE orderexecmark <= 766);
V53 SELECT COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE o.orderbase='API' AND e.exectune='Taker' AND e.orderexecmark <= 766;
V54 SELECT COUNT(*) FROM orders o WHERE o.orderbase='API' AND o.recordvault NOT IN (SELECT ordersmark FROM orderexecutions WHERE orderexecmark <= 766);
V55 SELECT SUM(ABS(f.feetotal - f.feerate*e.fillsum) < 0.01), COUNT(*) FROM fees f JOIN orderexecutions e ON e.ordersmark=f.orderslink;
V56 SELECT o.orderbase, SUM(ABS(f.feetotal - f.feerate*e.fillsum) < 0.01), COUNT(*) FROM fees f JOIN orderexecutions e ON e.orderexecmark=f.feesnode JOIN orders o ON o.recordvault=e.ordersmark GROUP BY 1;
V57 SELECT o.orderflow, SUM(o.orderbase<>'API'), SUM(o.orderbase='API') FROM orders o GROUP BY 1;
V58 SELECT COUNT(*) FROM orderexecutions e JOIN orders o ON o.recordvault=e.ordersmark WHERE o.orderflow='Filled' AND e.remaincount>0 AND o.orderbase<>'API';

### C1 (recommended): a tail date window on alien observationalconditions; rows with obsdate >= 2023-01-01 are cut (the table stops at the end of 2022, like a satellite table that stopped being updated)

Finder:

All run with sqlite3 -readonly 'file:<scratch>/vm61/alien_clean.sqlite?mode=ro'; crypto was not touched:
(1) .schema
(2) SELECT signalref, obstime, obsdate, obsdurhrs FROM observationalconditions LIMIT 5;
(3) SELECT signalregistry, timemark FROM signals LIMIT 5;
(4) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT obsdate), COUNT(DISTINCT substr(obsdate,1,7)), SUM(obsdate IS NULL) FROM observationalconditions;
(5) SELECT COUNT(*), MIN(timemark), MAX(timemark), SUM(timemark IS NULL) FROM signals;
(6) SELECT COUNT(DISTINCT obstime), MIN(obstime), MAX(obstime) FROM observationalconditions;
(7) SELECT COUNT(*) FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry;
(8) SELECT SUM(o.obsdate < substr(s.timemark,1,10)), SUM(o.obsdate = substr(s.timemark,1,10)), SUM(o.obsdate > substr(s.timemark,1,10)) FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry;
(9) SELECT SUM(o.obsdate < '2023-01-01' AND s.timemark < '2023-01-01'), SUM(o.obsdate < '2023-01-01' AND s.timemark >= '2023-01-01'), SUM(o.obsdate >= '2023-01-01' AND s.timemark < '2023-01-01'), SUM(o.obsdate >= '2023-01-01' AND s.timemark >= '2023-01-01') FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry;
(10) SELECT ROUND(AVG(ABS(julianday(o.obsdate) - julianday(substr(s.timemark,1,10)))),0), MIN(julianday(o.obsdate) - julianday(substr(s.timemark,1,10))), MAX(julianday(o.obsdate) - julianday(substr(s.timemark,1,10))) FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry;
(11)–(17) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)) FROM observationalconditions WHERE …, where the WHERE is, in turn, obsdate < '2023-01-01', < '2024-01-01', < '2022-01-01', < '2023-07-01', >= '2018-01-01', >= '2019-01-01' and >= '2020-01-01';
(18) SELECT substr(obsdate,1,4) y, COUNT(*) FROM observationalconditions GROUP BY y;
(19) SELECT substr(timemark,1,4) y, COUNT(*) FROM signals GROUP BY y;
(20) SELECT m.name, p.name FROM sqlite_master m, pragma_table_info(m.name) p WHERE m.type='table' AND (upper(p.name) LIKE '%DATE%' OR upper(p.name) LIKE '%START%' OR upper(p.name) LIKE '%FINISH%' OR upper(p.name) LIKE '%REPORT%' OR upper(p.name) LIKE '%ARRIVE%');
(21) SELECT COUNT(*), SUM(obsdurhrs IS NULL), COUNT(DISTINCT obsdurhrs), MIN(obsdurhrs), MAX(obsdurhrs), ROUND(AVG(obsdurhrs),4), ROUND(SUM(obsdurhrs),2) FROM observationalconditions;
(22) SELECT COUNT(*), SUM(obsdurhrs IS NULL), COUNT(DISTINCT obsdurhrs), ROUND(AVG(obsdurhrs),4), ROUND(SUM(obsdurhrs),2) FROM observationalconditions WHERE obsdate < '2023-01-01';
(23) SELECT ROUND(AVG(obsdurhrs),4), ROUND(SUM(obsdurhrs),2), MAX(obsdurhrs) FROM observationalconditions WHERE obsdate >= '2023-01-01';
(24) SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM observationalconditions WHERE obsdate < '2023-01-01');
(25) SELECT COUNT(*) FROM signals s WHERE s.timemark >= '2023-01-01' AND s.signalregistry NOT IN (SELECT signalref FROM observationalconditions WHERE obsdate < '2023-01-01');
(26) SELECT COUNT(*), MIN(o.obsdate), MAX(o.obsdate), COUNT(DISTINCT substr(o.obsdate,1,7)) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE s.timemark < '2023-01-01';
(27) Same as (26), WHERE s.timemark >= '2018-01-01';
(28) The same four-cell cross count as (9), with the boundary changed to '2018-01-01';
(29) SELECT COUNT(*) FROM signals WHERE timemark < '2018-01-01';
(30) SELECT COUNT(*) FROM signals WHERE timemark >= '2023-01-01';
(31) SELECT ROUND(SUM(obsdurhrs),2), ROUND(AVG(obsdurhrs),4) FROM observationalconditions WHERE obsdate < '2018-01-01';
(32) Same as (31), WHERE obsdate >= '2018-01-01';
(33) WITH oc AS (SELECT * FROM observationalconditions WHERE obsdate < '2023-01-01') SELECT (SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT COUNT(*) FROM oc WHERE obsdate >= '2023-01-01'), (SELECT 1.0*COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)) / (SELECT COUNT(*) FROM signals), (SELECT COUNT(*) FROM oc WHERE obsdate >= '2022-01-01') + (SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT COUNT(*) FROM oc WHERE obsdate >= '2022-01-01'), (SELECT COUNT(*) FROM signals WHERE timemark >= '2023-01-01' AND signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT ROUND(SUM(obsdurhrs),2) FROM oc), (SELECT substr(obsdate,1,4) FROM oc GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1);
(34) WITH oc AS (SELECT * FROM observationalconditions WHERE obsdate >= '2018-01-01') SELECT (SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT COUNT(*) FROM oc WHERE obsdate < '2018-01-01'), (SELECT COUNT(*) FROM oc WHERE obsdate < '2019-01-01') + (SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT COUNT(*) FROM oc WHERE obsdate < '2019-01-01'), (SELECT MIN(obsdate)||' '||MAX(obsdate)||' '||COUNT(DISTINCT substr(obsdate,1,7))||' '||COUNT(*) FROM oc);
(35) SELECT COUNT(*), COUNT(DISTINCT obsdate), COUNT(DISTINCT obsdurhrs) FROM observationalconditions WHERE obsdate < '2023-01-01';
(36) Same as (35), WHERE obsdate >= '2018-01-01';
(37) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)) FROM observationalconditions WHERE obsdate >= '2017-01-01';
(38) SELECT COUNT(*) FROM observationalconditions WHERE obsdate < '2018-07-01';

Read-only reads that are not SQL: docs/research/clean-scan.json, results/thin/2026-10-24-66a86cb.jsonl, ~/.cache/warrant/…/alien/alien_column_meaning_base.json, and a grep of alien_kb.jsonl (no match).

Verifier:

All run with python3 -I through sqlite3.connect('file:<scratch>/vm61/alien_clean.sqlite?mode=ro', uri=True). The SHA-256 was first checked with shasum: e160643c…, which matches freeze/write_line.yaml:21. Crypto was not touched, and nothing was written.
(1) SELECT name, sql FROM sqlite_master WHERE type='table' AND name IN ('observationalconditions','signals')
(2) SELECT m.name, p."from", p."table", p."to" FROM sqlite_master m, pragma_foreign_key_list(m.name) p WHERE m.type='table'
(3) SELECT m.name, COUNT(*) FROM sqlite_master m, pragma_table_info(m.name) p WHERE m.type='table' GROUP BY m.name
(4) SELECT name FROM sqlite_master WHERE type='table'
(5) SELECT m.name, group_concat(p.name || ':' || p.type, ', ') FROM sqlite_master m, pragma_table_info(m.name) p WHERE m.type='table' GROUP BY m.name
(6) SELECT signalref, obstime, obsdate, obsdurhrs, typeof(obsdate), typeof(obsdurhrs) FROM observationalconditions LIMIT 5
(7) SELECT signalregistry, timemark, typeof(timemark) FROM signals LIMIT 5
(8) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT obsdate), COUNT(DISTINCT substr(obsdate,1,7)), SUM(obsdate IS NULL), SUM(obsdate=''), COUNT(DISTINCT obsdurhrs), COUNT(DISTINCT obstime), SUM(obsdurhrs IS NULL), SUM(obstime IS NULL) FROM observationalconditions
(9) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT obsdate), COUNT(DISTINCT substr(obsdate,1,7)), COUNT(DISTINCT obsdurhrs), COUNT(DISTINCT obstime), SUM(obsdurhrs IS NULL) FROM observationalconditions WHERE obsdate < '2023-01-01'
(10) SELECT COUNT(*), SUM(length(obsdate)<>10), SUM(obsdate NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]') FROM observationalconditions
(11) SELECT COUNT(*), MIN(timemark), MAX(timemark), SUM(timemark IS NULL) FROM signals
(12) SELECT typeof(obsdurhrs), COUNT(*) FROM observationalconditions GROUP BY 1
(13) SELECT COUNT(*) FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry
(14) SELECT SUM(o.obsdate < substr(s.timemark,1,10)), SUM(o.obsdate = substr(s.timemark,1,10)), SUM(o.obsdate > substr(s.timemark,1,10)) FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry
(15) SELECT SUM(o.obsdate < '2023-01-01' AND s.timemark < '2023-01-01'), SUM(o.obsdate < '2023-01-01' AND s.timemark >= '2023-01-01'), SUM(o.obsdate >= '2023-01-01' AND s.timemark < '2023-01-01'), SUM(o.obsdate >= '2023-01-01' AND s.timemark >= '2023-01-01') FROM observationalconditions o JOIN signals s ON o.signalref = s.signalregistry
(16) SELECT substr(obsdate,1,4) y, COUNT(*) FROM observationalconditions GROUP BY y
(17) SELECT substr(timemark,1,4) y, COUNT(*) FROM signals GROUP BY y
(18) SELECT ROUND(SUM(obsdurhrs),2), ROUND(AVG(obsdurhrs),4) FROM observationalconditions
(19) Same as (18), WHERE obsdate < '2023-01-01'
(20) SELECT ROUND(AVG(obsdurhrs),4), COUNT(*) FROM observationalconditions WHERE obsdate >= '2024-01-01' AND obsdate < '2025-01-01'
(21) SELECT COUNT(*) FROM observationalconditions WHERE obsdate >= '2022-01-01' AND obsdate < '2023-01-01'
(22)–(25) SELECT '<label>', COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)), 1000-COUNT(*), COUNT(DISTINCT obsdate), COUNT(DISTINCT obsdurhrs) FROM observationalconditions WHERE …, where the WHERE is, in turn: obsdate < '2024-01-01'; obsdate < '2022-01-01'; obsdate >= '2018-01-01'; signalref NOT IN (SELECT signalregistry FROM signals WHERE timemark >= '2023-01-01')
(26) SELECT 'to2022H2', COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)) FROM observationalconditions WHERE obsdate < '2022-12-29'
(27) Same as (26), WHERE obsdate <= '2022-12-28'
(28) SELECT obsdate, COUNT(*) FROM observationalconditions WHERE obsdate >= '2022-12-01' AND obsdate < '2023-02-01' GROUP BY 1
(29) WITH oc AS (SELECT * FROM observationalconditions WHERE obsdate < '2023-01-01') SELECT (SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT COUNT(*) FROM oc WHERE obsdate >= '2023-01-01'), (SELECT 1.0*COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc))/(SELECT COUNT(*) FROM signals), (SELECT COUNT(*) FROM oc WHERE obsdate >= '2022-01-01') + (SELECT COUNT(*) FROM signals WHERE signalregistry NOT IN (SELECT signalref FROM oc)), (SELECT COUNT(*) FROM oc WHERE obsdate >= '2022-01-01'), (SELECT ROUND(SUM(obsdurhrs),2) FROM oc), (SELECT substr(obsdate,1,4) FROM oc GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1)
(30) SELECT (SELECT COUNT(*) FROM signals WHERE timemark >= '2023-01-01'), (SELECT COUNT(*) FROM signals WHERE timemark >= '2022-01-01'), (SELECT 1.0*COUNT(*)/1000 FROM signals WHERE timemark >= '2023-01-01'), (SELECT substr(timemark,1,4) FROM signals GROUP BY 1 ORDER BY COUNT(*) DESC LIMIT 1)
(31) WITH oc AS (…obsdate < '2023-01-01') SELECT ROUND(AVG(o.obsdurhrs),4), COUNT(*) FROM oc o JOIN signals s ON s.signalregistry=o.signalref WHERE s.timemark >= '2024-01-01' AND s.timemark < '2025-01-01'
(32) WITH oc AS (…obsdate < '2023-01-01') SELECT COUNT(*), SUM(s.timemark >= '2023-01-01') FROM signals s WHERE s.signalregistry NOT IN (SELECT signalref FROM oc)
(33) SELECT MIN(obsdurhrs), MAX(obsdurhrs), SUM(obsdurhrs <= 0) FROM observationalconditions
(34) SELECT COUNT(*), MIN(s.timemark), MAX(s.timemark), SUM(s.timemark >= '2024-01-01') FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE o.obsdate < '2023-01-01' AND s.timemark >= '2023-01-01'
(35) SELECT substr(s.timemark,1,4), COUNT(*) FROM signals s WHERE s.signalregistry NOT IN (SELECT signalref FROM observationalconditions WHERE obsdate < '2023-01-01') GROUP BY 1
(36)–(38) SELECT COUNT(*) FROM researchprocess; FROM signaldynamics; FROM sourceproperties
(39) SELECT COUNT(*) FROM signals s WHERE NOT EXISTS (…researchprocess…) OR NOT EXISTS (…signaldecoding…) OR NOT EXISTS (…signalclassification…) OR NOT EXISTS (…signalprobabilities…) OR NOT EXISTS (…signaladvancedphenomena…) OR NOT EXISTS (…signaldynamics…) OR NOT EXISTS (…sourceproperties…), where each subquery's condition is x.signalref = s.signalregistry
The query tool was <scratch>/c1verify/q.py, which opens the file with mode=ro only. The helper only ran the SELECT statements listed above; its code is in the section "Helper scripts".

Read-only reads that are not SQL:
- Repo code and docs: predict.py, gloss/detect/*.py, probe.py, battery/run.py, normalise.py, data/export.py, defects/audit.py, freeze/validate.py, write_line/run.py, scoring/classify.py, agent/write_claims.py and confidence.py.
- freeze/write_line.yaml, freeze/NOTE.md, CONTEXT.md, CONTRIBUTING.md, ADR 0002/0003/0011 and configs/write_line_thin.yaml.
- docs/research/clean-scan.json and results/thin/2026-10-24-66a86cb.jsonl.
- The design session's notes on the #61 decisions and the 2026-10-25 lever study (scratch files, not in the repo).

No injection, no copy made, no battery or predict run, no model call, and no git, GitHub, AWS or MCP action.

### C2 (alternative): a head date window on alien observationalconditions; rows with obsdate < 2018-01-01 are cut (conditions before 2018 removed by retention)

Finder:

Shares one list with C1 (all read-only, run on vm61/alien_clean.sqlite). C2 used (4), the two queries of (11)–(17) with >= '2018-01-01' and >= '2019-01-01', (18), (19), (21), (27), (28), (29), (31), (32), (34), (36) and (37). It also ran one extra query, (38): SELECT COUNT(*) FROM observationalconditions WHERE obsdate < '2018-07-01'. The result was 340, and it was not used.

Verifier:

All run read-only with python sqlite3.connect('file:<scratch>/vm61/alien_clean.sqlite?mode=ro', uri=True). Before the run, shasum gave the hash e160643c…46ed, which matches freeze/write_line.yaml:21. The queries ran through a helper script I made new in the scratch directory, <scratch>/c2_q.py, which opens a read-only connection only. No repo file or existing file was changed, and no model, git, AWS or MCP was called.

(1) SELECT sql FROM sqlite_master WHERE name IN ('observationalconditions','signals')
(2) SELECT m.name, p.* FROM sqlite_master m, pragma_foreign_key_list(m.name) p WHERE m.type='table'
(3) SELECT m.name, group_concat(p.name || ':' || p.type, ', ') FROM sqlite_master m, pragma_table_info(m.name) p WHERE m.type='table' GROUP BY m.name
(4) SELECT name, (SELECT 1) FROM sqlite_master WHERE type='table'
(5) SELECT * FROM observationalconditions LIMIT 5
(6) SELECT signalregistry, timemark FROM signals LIMIT 5
(7) SELECT COUNT(*), COUNT(DISTINCT signalref), COUNT(DISTINCT obstime), COUNT(DISTINCT obsdate), COUNT(DISTINCT obsdurhrs), MIN(obsdate), MAX(obsdate), SUM(obsdate IS NULL), SUM(obsdurhrs IS NULL), SUM(obstime IS NULL) FROM observationalconditions
(8) SELECT obstime, COUNT(*) FROM observationalconditions GROUP BY 1
(9) SELECT COUNT(*), MIN(timemark), MAX(timemark), COUNT(DISTINCT timemark) FROM signals
(10) SELECT typeof(obsdate), typeof(obsdurhrs), typeof(obstime), COUNT(*) FROM observationalconditions GROUP BY 1,2,3
(11) SELECT substr(obsdate,1,4) y, COUNT(*) FROM observationalconditions GROUP BY 1 ORDER BY 1
(12) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)), COUNT(DISTINCT obsdate), COUNT(DISTINCT obsdurhrs) FROM observationalconditions WHERE obsdate >= '2018-01-01'
(13) Same as (12), with the condition changed to obsdate >= '2019-01-01'
(14) Same as (12), with the condition changed to obsdate >= '2017-01-01'
(15) Same as (12), with the condition changed to obsdate < '2023-01-01'
(16) SELECT COUNT(*) FROM observationalconditions WHERE obsdate < '2018-01-01'
(17) SELECT COUNT(*) FROM observationalconditions WHERE obsdate NOT GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'
(18) SELECT (o.obsdate < '2018-01-01') AS obs_pre, (s.timemark < '2018-01-01') AS det_pre, COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry = o.signalref GROUP BY 1,2 ORDER BY 1,2
(19) SELECT COUNT(*) FROM signals WHERE timemark < '2018-01-01'
(20) SELECT COUNT(*), MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)) FROM observationalconditions WHERE signalref NOT IN (SELECT signalregistry FROM signals WHERE timemark < '2018-01-01')
(21) SELECT COUNT(*) FROM observationalconditions o LEFT JOIN signals s ON s.signalregistry=o.signalref WHERE s.signalregistry IS NULL
(22) SELECT ROUND(SUM(obsdurhrs),2), ROUND(SUM(CASE WHEN obsdate >= '2018-01-01' THEN obsdurhrs END),2), ROUND(AVG(CASE WHEN substr(obsdate,1,4)='2016' THEN obsdurhrs END),3), MIN(obsdurhrs), MAX(obsdurhrs) FROM observationalconditions
(23) SELECT SUM(obsdate < substr(s.timemark,1,10)), SUM(obsdate = substr(s.timemark,1,10)), SUM(obsdate > substr(s.timemark,1,10)) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref
(24) SELECT COUNT(*) FROM researchprocess WHERE notesmemo GLOB '*20[0-9][0-9]*'
(25) SELECT notesmemo FROM researchprocess WHERE notesmemo IS NOT NULL LIMIT 3
(26) SELECT 'researchprocess', COUNT(*) FROM researchprocess UNION ALL ... (one part each for signaldecoding, signaldynamics, signalclassification, signalprobabilities, sourceproperties and signaladvancedphenomena)
(27) SELECT observstation, sidereallocal FROM observatories LIMIT 3
(28) SELECT COUNT(*) FROM signals s JOIN observationalconditions o ON o.signalref=s.signalregistry WHERE s.sigdursec > o.obsdurhrs*3600
(29) SELECT SUM(timemark < '2019-01-01'), SUM(substr(timemark,1,4)='2017'), SUM(substr(timemark,1,4)='2018') FROM signals
(30) SELECT substr(s.timemark,1,4) y, COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE o.obsdate < '2018-01-01' GROUP BY 1 ORDER BY 1
(31) SELECT COUNT(*) FROM observationalconditions WHERE obsdate < '2019-01-01'

The helper only ran the SELECT statements listed above; its code is in the section "Helper scripts".

No query on crypto_clean.sqlite. I also read docs/research/clean-scan.json, predictions/9cfd501f2182-write_line/27f88c60…jsonl and results/thin/2026-10-24-66a86cb.jsonl; these three were file reads, not SQL.

### Rejected near-miss: no non-date cut on alien qualifies

Finder:

All read-only on <scratch>/vm61/alien_clean.sqlite (sqlite3 -readonly CLI once; otherwise python sqlite3 'file:...?mode=ro', uri=True); none on crypto. 1) .schema; 2) SELECT name FROM sqlite_master WHERE type='table' ORDER BY name; 3) SELECT COUNT(*) FROM "<t>" for each of the 11 tables; 4) SELECT signalregistry, timemark, telescref, detectinstr FROM signals ORDER BY rowid LIMIT 5; 5) SELECT telescregistry, observstation FROM telescopes ORDER BY rowid LIMIT 5; 6) SELECT observstation FROM observatories ORDER BY rowid LIMIT 3; 7) SELECT MIN(timemark), MAX(timemark), COUNT(DISTINCT substr(timemark,1,4)) FROM signals; 8) SELECT n, COUNT(*) FROM (SELECT telescref, COUNT(*) n FROM signals GROUP BY telescref) GROUP BY n; 9) SELECT n, COUNT(*) FROM (SELECT observstation, COUNT(*) n FROM telescopes GROUP BY observstation) GROUP BY n; 10) SELECT COUNT(*) FROM telescopes WHERE telescregistry NOT IN (SELECT telescref FROM signals); 11) SELECT COUNT(*) FROM (SELECT telescref FROM signals GROUP BY telescref HAVING COUNT(DISTINCT detectinstr)>1); 12) SELECT COUNT(DISTINCT observstation) FROM telescopes; 13) SELECT detectinstr, COUNT(*) FROM signals GROUP BY 1 ORDER BY 2 DESC; 14) PRAGMA table_info("<t>") for every table (run twice); 15) SELECT COUNT(DISTINCT obstime), COUNT(DISTINCT obsdate), COUNT(DISTINCT obsdurhrs), SUM(obsdurhrs IS NULL), SUM(obsdate IS NULL) FROM observationalconditions; 16) SELECT s.detectinstr, COUNT(*), MIN(o.obsdate), MAX(o.obsdate), COUNT(DISTINCT substr(o.obsdate,1,7)) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref GROUP BY 1; 17) the same MIN/MAX/month count WHERE s.detectinstr <> 'Radio Telescope'; 18) SELECT COUNT(*) FROM telescopes t WHERE NOT EXISTS (SELECT 1 FROM signals s WHERE s.telescref=t.telescregistry AND s.detectinstr <> 'Quantum Detector'); 19) SELECT COUNT(DISTINCT "<col>") FROM "<t>" for every column, then SELECT "<col>", COUNT(*) FROM "<t>" GROUP BY 1 for every column with 2-50 distinct values; 20) SELECT MIN(rowid), MAX(rowid), COUNT(*) FROM observationalconditions; 21) SELECT SUM(o.rowid = s.rowid), COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry = o.signalref; 22) SELECT MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)), COUNT(DISTINCT obsdurhrs), COUNT(*) FROM observationalconditions WHERE rowid <= 800; 23) SELECT rowid, obsdate FROM observationalconditions WHERE obsdate IN ((SELECT MIN(obsdate) FROM observationalconditions),(SELECT MAX(obsdate) FROM observationalconditions)); 24) SELECT s.detectinstr, COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE o.rowid > 800 GROUP BY 1 ORDER BY 1; 25) SELECT MIN(obsdurhrs), MAX(obsdurhrs), ROUND(AVG(obsdurhrs),3), ROUND(SUM(obsdurhrs),2) FROM observationalconditions; 26) SELECT ROUND(SUM(obsdurhrs),2), SUM(obsdurhrs > 12) FROM observationalconditions WHERE rowid <= 800; 27) SELECT SUM(obsdurhrs > 12) FROM observationalconditions; 28) SELECT MIN(obsdate), MAX(obsdate), COUNT(DISTINCT substr(obsdate,1,7)), COUNT(DISTINCT obsdurhrs), COUNT(*), ROUND(SUM(obsdurhrs),2), SUM(obsdurhrs > 12) FROM observationalconditions WHERE rowid <= 700; 29) SELECT s.detectinstr FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE o.rowid IN (600, 711); 30) SELECT COUNT(DISTINCT obsdurhrs), COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE s.detectinstr <> 'Radio Telescope'. No files edited, no injection, no battery run, no model, git, GitHub, AWS or MCP calls.

Verifier:

All queries were read-only, on <scratch>/vm61/alien_clean.sqlite, opened with python sqlite3 'file:...?mode=ro', uri=True. Its sha256 is e160643c..., which matches freeze/write_line.yaml:21. No query ran on crypto. The helper script <scratch>/v61cov_q.py, written to the scratch directory, only runs SELECT queries on that mode=ro connection.

1) SELECT name FROM sqlite_master WHERE type='table' ORDER BY name; then for each table SELECT COUNT(*), PRAGMA table_info, PRAGMA foreign_key_list
2) SELECT * FROM observationalconditions ORDER BY rowid LIMIT 3
3) SELECT signalregistry,timemark,telescref,detectinstr FROM signals ORDER BY rowid LIMIT 3
4) SELECT COUNT(DISTINCT obstime),COUNT(DISTINCT obsdate),COUNT(DISTINCT obsdurhrs),SUM(obsdurhrs IS NULL),SUM(obsdate IS NULL),SUM(obsdate=''),SUM(signalref IS NULL) FROM observationalconditions
5) SELECT MIN(obsdate),MAX(obsdate),COUNT(DISTINCT substr(obsdate,1,7)),MIN(length(obsdate)),MAX(length(obsdate)) FROM observationalconditions
6) SELECT detectinstr,COUNT(*) FROM signals GROUP BY 1 ORDER BY 2 DESC
7) SELECT SUM(o.rowid=s.rowid),COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref
8) SELECT rowid,obsdate FROM observationalconditions WHERE obsdate IN ((SELECT MIN(obsdate) FROM observationalconditions),(SELECT MAX(obsdate) FROM observationalconditions))
9) SELECT o.rowid,s.detectinstr FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE o.rowid IN (600,711)
10) SELECT MIN(o.obsdate),MAX(o.obsdate),COUNT(DISTINCT substr(o.obsdate,1,7)),COUNT(DISTINCT o.obsdurhrs),COUNT(DISTINCT o.obsdate),COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE s.detectinstr<>'Radio Telescope'
11) the same columns FROM observationalconditions WHERE rowid<=800
12) the same columns plus ROUND(SUM(obsdurhrs),2),SUM(obsdurhrs>12) WHERE rowid<=700
13) SELECT s.detectinstr,COUNT(*),MIN(o.obsdate),MAX(o.obsdate),COUNT(DISTINCT substr(o.obsdate,1,7)) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref GROUP BY 1
14) SELECT MIN(obsdurhrs),MAX(obsdurhrs),ROUND(AVG(obsdurhrs),3),ROUND(SUM(obsdurhrs),2),SUM(obsdurhrs>12) FROM observationalconditions
15) SELECT MIN(rowid),MAX(rowid),COUNT(*) FROM observationalconditions
16) the same query on signals
17) SELECT n,COUNT(*) FROM (SELECT telescref,COUNT(*) n FROM signals GROUP BY telescref) GROUP BY n
18) SELECT COUNT(*) FROM telescopes WHERE telescregistry NOT IN (SELECT telescref FROM signals)
19) SELECT COUNT(*) FROM (SELECT telescref FROM signals GROUP BY telescref HAVING COUNT(DISTINCT detectinstr)>1)
20) SELECT COUNT(*) FROM telescopes t WHERE NOT EXISTS (SELECT 1 FROM signals s WHERE s.telescref=t.telescregistry AND s.detectinstr<>'Quantum Detector')
21) SELECT COUNT(*) FROM observatories WHERE observstation NOT IN (SELECT observstation FROM telescopes)
22) SELECT decodestat,COUNT(*) FROM signaldecoding GROUP BY 1
23) SELECT followstat,COUNT(*) FROM researchprocess GROUP BY 1
24) SELECT celestobj,COUNT(*) FROM sourceproperties GROUP BY 1 ORDER BY 2 DESC LIMIT 6
25) SELECT SUM(substr(o.obsdate,1,10)<>substr(s.timemark,1,10)),COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref
26) for each of the 8 child tables, UNION ALL: SELECT COUNT(DISTINCT signalref),SUM(signalref NOT IN (SELECT signalregistry FROM signals)) FROM <t>
27) SELECT COUNT(*) FROM observationalconditions WHERE obsdate<'2015-02-25' OR obsdate>'2025-02-08'
28) SELECT obsdate,COUNT(*) FROM observationalconditions WHERE obsdate IN ('2015-02-25','2025-02-08') GROUP BY 1
29) SELECT s.detectinstr,COUNT(*) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE o.rowid>700 GROUP BY 1 ORDER BY 1
30) PRAGMA table_info for every table, column names filtered for DATE/START/FINISH/REPORT/ARRIVE
31) SELECT CASE WHEN rowid>700 THEN 'gt700' ELSE 'le700' END,MIN(timemark),MAX(timemark),COUNT(*) FROM signals GROUP BY 1
32) the same grouping with MIN(signalregistry),MAX(signalregistry)
33) SELECT COUNT(*) FROM signals WHERE instr(signalregistry,char(160))>0 OR instr(timemark,char(160))>0
34) SELECT COUNT(*) FROM observationalconditions WHERE instr(signalref,char(160))>0
35) SELECT COUNT(*),ROUND(SUM(o.obsdurhrs),2),SUM(o.obsdurhrs>12) FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref WHERE s.detectinstr<>'Radio Telescope'
36) SELECT COUNT(*) FROM (SELECT s.telescref,substr(o.obsdate,1,10) d FROM observationalconditions o JOIN signals s ON s.signalregistry=o.signalref GROUP BY 1,2 HAVING COUNT(*)>1)
37) SELECT COUNT(DISTINCT polarmode),SUM(polarmode='Unknown') FROM signals

The helper only ran the SELECT statements listed above; its code is in the section "Helper scripts".

Besides these I read files: the repo code, docs/research/clean-scan.json and results/thin/2026-10-24-66a86cb.jsonl (through python json). I did no injection, ran no battery, called no model, and made no git, GitHub, AWS or MCP calls. No repository file was edited.

## The formula search: partial sum relations

### exec-throttle (refined baseline): exectimespan = apilatmark + queueline, plus a deterministic token-bucket wait on the rateremain <= 100 snapshots

Finder:

All opened with sqlite3 on "file:<scratch>/vm61/crypto_clean.sqlite?mode=ro"; alien was not touched:
1 .tables
2 SELECT name FROM sqlite_master WHERE type='table'; for each table, PRAGMA table_info(t) and SELECT count(*) FROM t
3 SELECT * FROM systemmonitoring LIMIT 5; SELECT * FROM marketstats LIMIT 4; SELECT * FROM fees LIMIT 5; SELECT * FROM orderexecutions LIMIT 5; SELECT orderspivot,dealquote,dealcount,notionsum,orderflow,timespan,ordertune,dealedge,orderbase FROM orders LIMIT 5
4 SELECT wsstate,count(*) FROM systemmonitoring GROUP BY 1
5 SELECT min/max of apireqtotal,apierrtotal,apilatmark,rateremain,exectimespan,queueline,slipratio,mkteffect,priceeffect FROM systemmonitoring
6 SELECT sum(x IS NULL) for apierrtotal,apilatmark,queueline,exectimespan,rateremain,slipratio,mkteffect,priceeffect, sum(exectimespan=0) FROM systemmonitoring; SELECT count(*) FROM systemmonitoring WHERE rateremain<=100
7 SELECT count(*) FROM systemmonitoring WHERE apierrtotal*1.0/apireqtotal>0.2
8 SELECT (apierrtotal*100/apireqtotal)/5*5 b,count(*) FROM systemmonitoring GROUP BY 1 ORDER BY 1 LIMIT 20
9 SELECT count(*) FROM systemmonitoring WHERE apierrtotal*20>=apireqtotal; ... WHERE apierrtotal=0; ... WHERE rateremain=0
10 SELECT count(*) FROM systemmonitoring WHERE apierrtotal>apireqtotal; SELECT (rateremain/50)*50 b,count(*) FROM systemmonitoring WHERE rateremain<=200 GROUP BY 1
11 SELECT sum(totsupply>=circtotal), sum(maxsupply>=totsupply), count(*) FROM marketstats
12 SELECT sum(abs(fillsum-fillcount*fillquote)<0.01*fillsum), sum(abs(fillsum-fillcount*fillquote)<0.005) FROM orderexecutions
13 SELECT sum(abs(notionsum-dealquote*dealcount)<0.01*notionsum) FROM orders
14 SELECT count(*) FROM orderexecutions e JOIN orders o ON trim(e.ordersmark)=trim(o.recordvault) WHERE abs(o.dealcount-(e.fillcount+e.remaincount))<0.0001
15b SELECT count(*) FROM fees f JOIN orders o ON trim(f.orderslink)=trim(o.recordvault) WHERE abs(f.feetotal - f.feerate*o.notionsum)<0.01
16 WITH h AS (SELECT *, apilatmark+queueline + CASE WHEN rateremain<=100 THEN 10*(110-rateremain) ELSE 0 END AS t FROM systemmonitoring) SELECT count(*), sum(abs(t-(apilatmark+queueline))<0.005), sum(t<(apilatmark+queueline)-0.005), min/max extra on rateremain<=100, min(t), max(t) FROM h
15 WITH h AS (SELECT *, 10*(110-rateremain) AS x FROM systemmonitoring WHERE rateremain<=100) SELECT sum(abs(x-col)<0.005) for apireqtotal, apierrtotal, rateremain, systemmonitoringpivot, cast(lastupdnote AS real), cast(seqcode AS real), apilatmark, queueline FROM h
17 WITH h AS (... + CASE WHEN apierrtotal*20>=apireqtotal THEN apilatmark+200 ELSE 0 END AS t ...) SELECT count(*), sum(abs(t-(apilatmark+queueline))<0.005) FROM h
19 SELECT count(*) FROM systemmonitoring WHERE rateremain<=100 AND apierrtotal*20>=apireqtotal
23 SELECT sum(abs(slipratio-(mkteffect+priceeffect))<0.005), sum(abs(mkteffect-(slipratio+priceeffect))<0.005), sum(slipratio<>0), sum(mkteffect<>0) FROM systemmonitoring
20 WITH h (true variant) SELECT round(avg(t),2), round(avg(apilatmark+queueline),2), (SELECT round(avg(exectimespan),2) FROM systemmonitoring), sum(t>apilatmark+queueline), round(sum(t-(apilatmark+queueline)),0), round(avg(CASE WHEN rateremain<=100 THEN t-(apilatmark+queueline) END),2) FROM h
21 WITH h (true variant) SELECT wsstate, round(avg(t),2), sum(t>apilatmark+queueline) FROM h GROUP BY 1
18 SELECT sum(exectimespan > apilatmark+queueline), sum(abs(exectimespan-(apilatmark+queueline))<0.005) FROM systemmonitoring; WITH h (true variant) SELECT count(*) FROM h WHERE t>2000
22 WITH h (f-retry variant) SELECT round(avg(t),2), sum(t>apilatmark+queueline), round(avg(CASE WHEN rateremain<=100 THEN t-(apilatmark+queueline) END),2), round(sum(t-(apilatmark+queueline)),0) FROM h
Other reads (not SQL): rule.py, validate.py, predict.py, run.py, freeze/*, the design notes in `<scratch>`, clean-scan.json, the results/thin jsonl, and the release's crypto_column_meaning_base.json.

Verifier:

All opened with sqlite3 on "file:<scratch>/vm61/crypto_clean.sqlite?mode=ro"; alien was not touched:
A1 PRAGMA table_info(systemmonitoring); SELECT * FROM systemmonitoring LIMIT 3;
A2 SELECT count(*), sum(apilatmark IS NULL), sum(queueline IS NULL), sum(rateremain IS NULL), sum(exectimespan IS NULL), sum(rateremain<=100), min(rateremain), max(rateremain), typeof(exectimespan), min/max(queueline), min/max(apilatmark) FROM systemmonitoring;
A3 WITH h AS (SELECT *, apilatmark+queueline + CASE WHEN rateremain<=100 THEN 10*(110-rateremain) ELSE 0 END AS t FROM systemmonitoring) SELECT count(*), sum(t<>0), sum(abs(t-(apilatmark+queueline))<0.005), sum(t<(apilatmark+queueline)-0.005), min(t), max(t), sum(t-(apilatmark+queueline)), round(avg(t),2), sum(t>apilatmark+queueline), typeof(t) FROM h;
A4 WITH h AS (SELECT *, 10*(110-rateremain) x FROM systemmonitoring WHERE rateremain<=100) SELECT round(avg(x),2), min(x), max(x), sum(abs(x-col)<0.005) for col in apireqtotal, apierrtotal, rateremain, systemmonitoringpivot, cast(lastupdnote as real), cast(seqcode as real), apilatmark, queueline, slipratio, mkteffect, priceeffect FROM h;
A5 SELECT round(avg(exectimespan),2), sum(exectimespan>apilatmark+queueline), sum(abs(exectimespan-(apilatmark+queueline))<0.005) FROM systemmonitoring; SELECT sum(rateremain<=100 AND apierrtotal*20>=apireqtotal) FROM systemmonitoring;
A6 SELECT sum(rateremain=100), sum(rateremain<100), sum(lastupdnote GLOB '*[^0-9]*'), sum(seqcode GLOB '*[^0-9]*'), max(exectimespan), min(exectimespan) FROM systemmonitoring; SELECT round(sum(max(exectimespan-(apilatmark+queueline),0)),2), round(avg(CASE WHEN rateremain<100 THEN exectimespan-(apilatmark+queueline) END),2) FROM systemmonitoring;
A7 The f-retry variant: WITH h AS (... + CASE WHEN apierrtotal*20>=apireqtotal THEN apilatmark+200 ELSE 0 END AS t ...) SELECT count(*), sum(abs(t-(apilatmark+queueline))<0.005), round(avg(t),2), sum(t>apilatmark+queueline), round(sum(t-(apilatmark+queueline)),0), round(avg(CASE WHEN rateremain<=100 THEN t-(apilatmark+queueline) END),2) FROM h;
A8 The true variant, split by wsstate: SELECT wsstate, round(avg(t),2), sum(t>apilatmark+queueline) FROM h GROUP BY 1;
A9 SELECT sum(abs(slipratio)<0.005), sum(abs(mkteffect)<0.005), sum(abs(priceeffect)<0.005), sum(apierrtotal=0) FROM systemmonitoring;

Other reads (not SQL):
- warrant/battery/gloss/detect/rule.py:1-227 (the path given in the task, warrant/battery/rule.py, does not exist)
- warrant/battery/gloss/detect/__init__.py:34-54
- warrant/write_line/predict.py:90-150
- warrant/freeze/validate.py:51-125
- freeze/write_line.yaml:40-80
- docs/research/clean-scan.json (identity_relations)
- the design session's notes on the #61 decisions (a scratch file, not in the repo)
- section (1) of the 2026-10-25 lever study's question (a scratch file, not in the repo)
- the release's crypto_column_meaning_base.json

No injection, no battery run, no model call, no file changed, and no git use.

### REJECTED near-miss, do not rank: alien signals sigstrdb := snrratio + noisefloordbm (out of the identity search's reach)

Finder:

All on file:<scratch>/vm61/alien_clean.sqlite?mode=ro via sqlite3: (1) SELECT name, count of columns FROM sqlite_master type='table'; (2) per table: SELECT count(*) FROM <t>; SELECT cid||':'||name||':'||type FROM pragma_table_info('<t>'); (3) SELECT * FROM signals LIMIT 4; (4) SELECT min/max of sigstrdb, freqmhz, centerfreqmhz, carrierfreqmhz, doppshifthz, freqdrifthzs, snrratio, noisefloordbm, plus null counts of sigstrdb/snrratio/noisefloordbm FROM signals; (5) SELECT * LIMIT 5 FROM signalprobabilities; SELECT analysisprio, count(*) FROM researchprocess GROUP BY 1; SELECT * LIMIT 3 FROM telescopes, signaldecoding, observatories, signalclassification, sourceproperties, observationalconditions; (6) SELECT group_concat(name) of numeric-declared columns of signals in cid order; (7) SELECT sum(abs(sigstrdb-(snrratio+noisefloordbm))<0.005) FROM signals -> 0; (8) SELECT rfistat, interflvl, count(*) FROM signals GROUP BY 1,2; (9) SELECT atmointerf, count(*) FROM signals GROUP BY 1; (10) SELECT sum(timemark GLOB '[0-9]*'), sum(signalregistry GLOB '[0-9]*'), sum(telescref GLOB '[0-9]*') FROM signals. No query on crypto_clean.sqlite.

Verifier:

All opened with sqlite3 on file:<scratch>/vm61/alien_clean.sqlite?mode=ro:
(1) SELECT cid||':'||name||':'||type FROM pragma_table_info('signals');
(2) SELECT count(*), sum(abs(sigstrdb-(snrratio+noisefloordbm))<0.005), sum(rfistat='Contaminated' AND interflvl='High'), sum(rfistat='Contaminated') FROM signals; result 1000|0|73|331
(3) For each column c of the 15 numeric columns: SELECT sum(c IS NOT NULL AND c<>''), sum(typeof(c) IN ('real','integer')) FROM signals; every column gives 1000|1000
(4) SELECT timemark, signalregistry, telescref, detectinstr, signalclass, modtype, polarmode FROM signals LIMIT 3;
No query on crypto_clean.sqlite.


## The value-meaning draft's and fact-check's queries

These are the design-time queries of the `pnl-sign` slot (`accountbalances.realline`), on crypto only.

### The draft (Q1 to Q17, R5, R6, R13)

All via the `sqlite3` CLI with `file:<scratch>/vm61/crypto_clean.sqlite?mode=ro`. "V" below is `(SELECT -realline AS r, -unrealline AS u, usertag FROM accountbalances)`.

- Q1: `SELECT sql FROM sqlite_master WHERE name='accountbalances'`
- Q2: `SELECT typeof(realline), typeof(unrealline), COUNT(*) FROM accountbalances GROUP BY 1,2`
- Q3: `SELECT COUNT(*), COUNT(DISTINCT realline), COUNT(DISTINCT unrealline), SUM(realline IS NULL), SUM(unrealline IS NULL), SUM(realline=0), SUM(unrealline=0) FROM accountbalances`
- Q4: `SELECT COUNT(DISTINCT -realline), COUNT(DISTINCT -unrealline) FROM accountbalances`
- Q4b: `SELECT realline, unrealline FROM accountbalances LIMIT 5`
- Q5/Q6: `SELECT col<0, COUNT(*), MIN(CAST(col AS TEXT)), MIN(col), MAX(col) FROM accountbalances GROUP BY 1`, for realline and for unrealline
- Q7: `SELECT MIN(CAST(-col AS TEXT)) FROM accountbalances WHERE col<0` (and `col>0`), for both columns
- Q8: the identity search, a `UNION ALL` of `SUM(abs(T-(A+B[+C]))<0.005)` over the 195 combinations involving a negated realline or unrealline, as target or operand (section "Identity search" below); maximum 0
- Q9-Q14, on V:
  - `SUM(r>0), SUM(r<0)`
  - `-SUM(r), SUM(r)`
  - `SUM(r) WHERE r>0`, `-SUM(r) WHERE r<0`
  - the two ratios
  - `SUM(r>10000), SUM(r<-10000)`
  - `-AVG(r), AVG(r)`
  - `MAX(r), -MIN(r)`
  - top three by `abs(r)` with their usertag
  - `COUNT(DISTINCT TRIM(usertag))`
- Schema list via `pragma_table_info`; `SELECT risk_margin_profile FROM riskandmargin LIMIT 1`; the orders-to-accountbalances join count
- Q15: `SELECT o.dealedge, a.realline<0, COUNT(*) FROM orders o JOIN accountbalances a ON TRIM(a.usertag)=TRIM(o.userlink) GROUP BY 1,2`
- Q16: `SUM((realline<0)=(unrealline<0))`
- Q17: the Pearson correlation of realline with walletsum
- R5: `SELECT usertag, realline, -realline, length(usertag) FROM accountbalances WHERE TRIM(usertag)='U458616'`
- R6: `SELECT COUNT(*), COUNT(DISTINCT TRIM(usertag)), COUNT(DISTINCT usertag), SUM(usertag IS NULL) FROM accountbalances`
- R13: `SELECT MIN(walletsum), MIN(availsum), MIN(frozensum), MIN(margsum), SUM(walletsum<0)+SUM(availsum<0)+SUM(frozensum<0)+SUM(margsum<0) FROM accountbalances`

### The fact-check (R1 to R13)

All through `sqlite3` on `file:<scratch>/vm61/crypto_clean.sqlite?mode=ro`. V is `(SELECT -realline AS r, -unrealline AS u, usertag FROM accountbalances)`.

- R1: `shasum -a 256` of the file (not SQL)
- R2: Q1, Q2, Q3, Q4, Q5/Q6, and the four Q7 queries, as in the draft
- R3: the draft's identity search (section "Identity search" below), unchanged (195 combinations, maximum 0)
- R4, on V:
  - `SUM(r>0), SUM(r<0)`
  - `-SUM(r), SUM(r)`
  - `SUM(r) WHERE r>0`, `-SUM(r) WHERE r<0`
  - both ratios
  - `SUM(r>10000), SUM(r<-10000)`
- R5: `SELECT usertag, realline, -realline, length(usertag) … WHERE TRIM(usertag)='U458616'`
- R6: `SELECT COUNT(*), COUNT(DISTINCT TRIM(usertag)), COUNT(DISTINCT usertag), SUM(usertag IS NULL)`
- R7: `SUM(realline)`
- R8: `SUM((realline<0)=(unrealline<0))`
- R9: the Pearson correlation of realline with walletsum, from averages
- R10: `SELECT sql FROM sqlite_master WHERE name='orders'`
- R11: `SELECT o.dealedge, a.realline<0, COUNT(*) FROM orders o JOIN accountbalances a ON TRIM(a.usertag)=TRIM(o.userlink) GROUP BY 1,2` and its join count
- R12: `SELECT COUNT(*) FROM sqlite_master WHERE type='table'`; tables whose SQL names accountbalances (none)
- R13: `SELECT MIN(walletsum), MIN(availsum), MIN(frozensum), MIN(margsum), <sum of negative counts>`

Not SQL: an in-memory run of the validator's `_defect` and `_disjoint` (see `val_draft.py` below), and a read of the first-run claims in `results/thin/2026-10-24-66a86cb.jsonl`.

### The note section's check

All were run through `sqlite3` on `file:<scratch>/vm61/crypto_clean.sqlite?mode=ro`, plus `shasum -a 256` of the file (not SQL).

- `SELECT name, sql FROM sqlite_master WHERE name IN ('users','accountbalances')`
- `SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%REFERENCES users%'`
- `SELECT acctscope, COUNT(*) FROM users GROUP BY 1 ORDER BY 1`
- `SELECT COUNT(*), COUNT(DISTINCT userstamp), COUNT(DISTINCT TRIM(userstamp)), MAX(length(userstamp)), MIN(length(userstamp)) FROM users`
- `SELECT COUNT(*), SUM(u.userstamp IS NOT NULL) FROM accountbalances a LEFT JOIN users u ON u.userstamp = a.usertag`, and the same with `TRIM` on both sides
- `SELECT u.acctscope, COUNT(*) FROM accountbalances a JOIN users u ON u.userstamp = a.usertag GROUP BY 1`
- `SELECT a.usertag, u.acctscope, a.realline FROM accountbalances a LEFT JOIN users u ON u.userstamp = a.usertag WHERE TRIM(a.usertag)='U458616'`
- `SELECT COUNT(*), COUNT(DISTINCT usertag) FROM accountbalances`
- On `V = (SELECT -a.realline AS r, a.usertag, us.acctscope FROM accountbalances a JOIN users us ON us.userstamp = a.usertag)`:
  - `COUNT(*), SUM(r>0), SUM(r<0)`;
  - grouped by `acctscope='Margin'`: `COUNT(*)`, `SUM(r>0)`, `SUM(r<0)`, `-SUM(r)`, `SUM(r)`, `SUM(r) WHERE r>0`, `-SUM(r) WHERE r<0`, `SUM(r>10000)`, `SUM(r<-10000)`;
  - both profit-to-loss ratios, over all rows and over `acctscope<>'Margin'`.
- `SELECT typeof(realline), typeof(unrealline), COUNT(*) FROM accountbalances GROUP BY 1,2`
- `SELECT COUNT(*), COUNT(DISTINCT realline), COUNT(DISTINCT unrealline), SUM(realline IS NULL), SUM(unrealline IS NULL), SUM(realline=0), SUM(unrealline=0), COUNT(DISTINCT -realline), COUNT(DISTINCT -unrealline) FROM accountbalances`
- `SELECT col<0, COUNT(*), MIN(CAST(col AS TEXT)), MIN(CAST(-col AS TEXT)) FROM accountbalances GROUP BY 1`, for realline and for unrealline
- On `(SELECT -realline AS r, usertag FROM accountbalances)`: `SUM(r>0)`, `SUM(r<0)`, `-SUM(r)`, `SUM(r)`, `SUM(r) WHERE r>0`, `-SUM(r) WHERE r<0`, `SUM(r>10000)`, `SUM(r<-10000)`
- `SELECT usertag, -realline, length(usertag) FROM accountbalances WHERE TRIM(usertag)='U458616'`
- `SELECT SUM((realline<0)=(unrealline<0)), MIN(walletsum), MIN(availsum), MIN(frozensum), MIN(margsum) FROM accountbalances`

## Identity search

The draft's Q8 and the fact-check's R3. It is one SELECT: a `UNION ALL` of 195 parts, one per combination, that counts the rows on which the sum holds and keeps the top five (`ORDER BY 2 DESC LIMIT 5`). The file `<scratch>/vm61/idsearch.sql` was one line; here a line break is added before each `UNION ALL`, and nothing else changes. It was run with `sqlite3` on `file:<scratch>/vm61/crypto_clean.sqlite?mode=ro`. The maximum was 0.

```sql
SELECT 'walletsum='||'availsum+unrealline', SUM(abs(walletsum-(availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+realline', SUM(abs(walletsum-(availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+unrealline', SUM(abs(walletsum-(frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+realline', SUM(abs(walletsum-(frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'margsum+unrealline', SUM(abs(walletsum-(margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'margsum+realline', SUM(abs(walletsum-(margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'unrealline+realline', SUM(abs(walletsum-((-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'unrealline+accountbalancesnode', SUM(abs(walletsum-((-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'realline+accountbalancesnode', SUM(abs(walletsum-((-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+frozensum+unrealline', SUM(abs(walletsum-(availsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+frozensum+realline', SUM(abs(walletsum-(availsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+margsum+unrealline', SUM(abs(walletsum-(availsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+margsum+realline', SUM(abs(walletsum-(availsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+unrealline+realline', SUM(abs(walletsum-(availsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+unrealline+accountbalancesnode', SUM(abs(walletsum-(availsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'availsum+realline+accountbalancesnode', SUM(abs(walletsum-(availsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+margsum+unrealline', SUM(abs(walletsum-(frozensum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+margsum+realline', SUM(abs(walletsum-(frozensum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+unrealline+realline', SUM(abs(walletsum-(frozensum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+unrealline+accountbalancesnode', SUM(abs(walletsum-(frozensum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'frozensum+realline+accountbalancesnode', SUM(abs(walletsum-(frozensum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'margsum+unrealline+realline', SUM(abs(walletsum-(margsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'margsum+unrealline+accountbalancesnode', SUM(abs(walletsum-(margsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'margsum+realline+accountbalancesnode', SUM(abs(walletsum-(margsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'walletsum='||'unrealline+realline+accountbalancesnode', SUM(abs(walletsum-((-unrealline)+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+unrealline', SUM(abs(availsum-(walletsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+realline', SUM(abs(availsum-(walletsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+unrealline', SUM(abs(availsum-(frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+realline', SUM(abs(availsum-(frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'margsum+unrealline', SUM(abs(availsum-(margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'margsum+realline', SUM(abs(availsum-(margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'unrealline+realline', SUM(abs(availsum-((-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'unrealline+accountbalancesnode', SUM(abs(availsum-((-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'realline+accountbalancesnode', SUM(abs(availsum-((-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+frozensum+unrealline', SUM(abs(availsum-(walletsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+frozensum+realline', SUM(abs(availsum-(walletsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+margsum+unrealline', SUM(abs(availsum-(walletsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+margsum+realline', SUM(abs(availsum-(walletsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+unrealline+realline', SUM(abs(availsum-(walletsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+unrealline+accountbalancesnode', SUM(abs(availsum-(walletsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'walletsum+realline+accountbalancesnode', SUM(abs(availsum-(walletsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+margsum+unrealline', SUM(abs(availsum-(frozensum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+margsum+realline', SUM(abs(availsum-(frozensum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+unrealline+realline', SUM(abs(availsum-(frozensum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+unrealline+accountbalancesnode', SUM(abs(availsum-(frozensum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'frozensum+realline+accountbalancesnode', SUM(abs(availsum-(frozensum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'margsum+unrealline+realline', SUM(abs(availsum-(margsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'margsum+unrealline+accountbalancesnode', SUM(abs(availsum-(margsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'margsum+realline+accountbalancesnode', SUM(abs(availsum-(margsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'availsum='||'unrealline+realline+accountbalancesnode', SUM(abs(availsum-((-unrealline)+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+unrealline', SUM(abs(frozensum-(walletsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+realline', SUM(abs(frozensum-(walletsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+unrealline', SUM(abs(frozensum-(availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+realline', SUM(abs(frozensum-(availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'margsum+unrealline', SUM(abs(frozensum-(margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'margsum+realline', SUM(abs(frozensum-(margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'unrealline+realline', SUM(abs(frozensum-((-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'unrealline+accountbalancesnode', SUM(abs(frozensum-((-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'realline+accountbalancesnode', SUM(abs(frozensum-((-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+availsum+unrealline', SUM(abs(frozensum-(walletsum+availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+availsum+realline', SUM(abs(frozensum-(walletsum+availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+margsum+unrealline', SUM(abs(frozensum-(walletsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+margsum+realline', SUM(abs(frozensum-(walletsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+unrealline+realline', SUM(abs(frozensum-(walletsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+unrealline+accountbalancesnode', SUM(abs(frozensum-(walletsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'walletsum+realline+accountbalancesnode', SUM(abs(frozensum-(walletsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+margsum+unrealline', SUM(abs(frozensum-(availsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+margsum+realline', SUM(abs(frozensum-(availsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+unrealline+realline', SUM(abs(frozensum-(availsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+unrealline+accountbalancesnode', SUM(abs(frozensum-(availsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'availsum+realline+accountbalancesnode', SUM(abs(frozensum-(availsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'margsum+unrealline+realline', SUM(abs(frozensum-(margsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'margsum+unrealline+accountbalancesnode', SUM(abs(frozensum-(margsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'margsum+realline+accountbalancesnode', SUM(abs(frozensum-(margsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'frozensum='||'unrealline+realline+accountbalancesnode', SUM(abs(frozensum-((-unrealline)+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+unrealline', SUM(abs(margsum-(walletsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+realline', SUM(abs(margsum-(walletsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+unrealline', SUM(abs(margsum-(availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+realline', SUM(abs(margsum-(availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'frozensum+unrealline', SUM(abs(margsum-(frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'frozensum+realline', SUM(abs(margsum-(frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'unrealline+realline', SUM(abs(margsum-((-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'unrealline+accountbalancesnode', SUM(abs(margsum-((-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'realline+accountbalancesnode', SUM(abs(margsum-((-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+availsum+unrealline', SUM(abs(margsum-(walletsum+availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+availsum+realline', SUM(abs(margsum-(walletsum+availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+frozensum+unrealline', SUM(abs(margsum-(walletsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+frozensum+realline', SUM(abs(margsum-(walletsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+unrealline+realline', SUM(abs(margsum-(walletsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+unrealline+accountbalancesnode', SUM(abs(margsum-(walletsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'walletsum+realline+accountbalancesnode', SUM(abs(margsum-(walletsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+frozensum+unrealline', SUM(abs(margsum-(availsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+frozensum+realline', SUM(abs(margsum-(availsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+unrealline+realline', SUM(abs(margsum-(availsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+unrealline+accountbalancesnode', SUM(abs(margsum-(availsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'availsum+realline+accountbalancesnode', SUM(abs(margsum-(availsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'frozensum+unrealline+realline', SUM(abs(margsum-(frozensum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'frozensum+unrealline+accountbalancesnode', SUM(abs(margsum-(frozensum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'frozensum+realline+accountbalancesnode', SUM(abs(margsum-(frozensum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'margsum='||'unrealline+realline+accountbalancesnode', SUM(abs(margsum-((-unrealline)+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+availsum', SUM(abs((-unrealline)-(walletsum+availsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+frozensum', SUM(abs((-unrealline)-(walletsum+frozensum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+margsum', SUM(abs((-unrealline)-(walletsum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+realline', SUM(abs((-unrealline)-(walletsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+accountbalancesnode', SUM(abs((-unrealline)-(walletsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+frozensum', SUM(abs((-unrealline)-(availsum+frozensum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+margsum', SUM(abs((-unrealline)-(availsum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+realline', SUM(abs((-unrealline)-(availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+accountbalancesnode', SUM(abs((-unrealline)-(availsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'frozensum+margsum', SUM(abs((-unrealline)-(frozensum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'frozensum+realline', SUM(abs((-unrealline)-(frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'frozensum+accountbalancesnode', SUM(abs((-unrealline)-(frozensum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'margsum+realline', SUM(abs((-unrealline)-(margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'margsum+accountbalancesnode', SUM(abs((-unrealline)-(margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'realline+accountbalancesnode', SUM(abs((-unrealline)-((-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+availsum+frozensum', SUM(abs((-unrealline)-(walletsum+availsum+frozensum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+availsum+margsum', SUM(abs((-unrealline)-(walletsum+availsum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+availsum+realline', SUM(abs((-unrealline)-(walletsum+availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+availsum+accountbalancesnode', SUM(abs((-unrealline)-(walletsum+availsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+frozensum+margsum', SUM(abs((-unrealline)-(walletsum+frozensum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+frozensum+realline', SUM(abs((-unrealline)-(walletsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+frozensum+accountbalancesnode', SUM(abs((-unrealline)-(walletsum+frozensum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+margsum+realline', SUM(abs((-unrealline)-(walletsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+margsum+accountbalancesnode', SUM(abs((-unrealline)-(walletsum+margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'walletsum+realline+accountbalancesnode', SUM(abs((-unrealline)-(walletsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+frozensum+margsum', SUM(abs((-unrealline)-(availsum+frozensum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+frozensum+realline', SUM(abs((-unrealline)-(availsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+frozensum+accountbalancesnode', SUM(abs((-unrealline)-(availsum+frozensum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+margsum+realline', SUM(abs((-unrealline)-(availsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+margsum+accountbalancesnode', SUM(abs((-unrealline)-(availsum+margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'availsum+realline+accountbalancesnode', SUM(abs((-unrealline)-(availsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'frozensum+margsum+realline', SUM(abs((-unrealline)-(frozensum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'frozensum+margsum+accountbalancesnode', SUM(abs((-unrealline)-(frozensum+margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'frozensum+realline+accountbalancesnode', SUM(abs((-unrealline)-(frozensum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'unrealline='||'margsum+realline+accountbalancesnode', SUM(abs((-unrealline)-(margsum+(-realline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+availsum', SUM(abs((-realline)-(walletsum+availsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+frozensum', SUM(abs((-realline)-(walletsum+frozensum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+margsum', SUM(abs((-realline)-(walletsum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+unrealline', SUM(abs((-realline)-(walletsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+accountbalancesnode', SUM(abs((-realline)-(walletsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+frozensum', SUM(abs((-realline)-(availsum+frozensum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+margsum', SUM(abs((-realline)-(availsum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+unrealline', SUM(abs((-realline)-(availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+accountbalancesnode', SUM(abs((-realline)-(availsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'frozensum+margsum', SUM(abs((-realline)-(frozensum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'frozensum+unrealline', SUM(abs((-realline)-(frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'frozensum+accountbalancesnode', SUM(abs((-realline)-(frozensum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'margsum+unrealline', SUM(abs((-realline)-(margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'margsum+accountbalancesnode', SUM(abs((-realline)-(margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'unrealline+accountbalancesnode', SUM(abs((-realline)-((-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+availsum+frozensum', SUM(abs((-realline)-(walletsum+availsum+frozensum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+availsum+margsum', SUM(abs((-realline)-(walletsum+availsum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+availsum+unrealline', SUM(abs((-realline)-(walletsum+availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+availsum+accountbalancesnode', SUM(abs((-realline)-(walletsum+availsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+frozensum+margsum', SUM(abs((-realline)-(walletsum+frozensum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+frozensum+unrealline', SUM(abs((-realline)-(walletsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+frozensum+accountbalancesnode', SUM(abs((-realline)-(walletsum+frozensum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+margsum+unrealline', SUM(abs((-realline)-(walletsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+margsum+accountbalancesnode', SUM(abs((-realline)-(walletsum+margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'walletsum+unrealline+accountbalancesnode', SUM(abs((-realline)-(walletsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+frozensum+margsum', SUM(abs((-realline)-(availsum+frozensum+margsum))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+frozensum+unrealline', SUM(abs((-realline)-(availsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+frozensum+accountbalancesnode', SUM(abs((-realline)-(availsum+frozensum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+margsum+unrealline', SUM(abs((-realline)-(availsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+margsum+accountbalancesnode', SUM(abs((-realline)-(availsum+margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'availsum+unrealline+accountbalancesnode', SUM(abs((-realline)-(availsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'frozensum+margsum+unrealline', SUM(abs((-realline)-(frozensum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'frozensum+margsum+accountbalancesnode', SUM(abs((-realline)-(frozensum+margsum+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'frozensum+unrealline+accountbalancesnode', SUM(abs((-realline)-(frozensum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'realline='||'margsum+unrealline+accountbalancesnode', SUM(abs((-realline)-(margsum+(-unrealline)+accountbalancesnode))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+unrealline', SUM(abs(accountbalancesnode-(walletsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+realline', SUM(abs(accountbalancesnode-(walletsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+unrealline', SUM(abs(accountbalancesnode-(availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+realline', SUM(abs(accountbalancesnode-(availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'frozensum+unrealline', SUM(abs(accountbalancesnode-(frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'frozensum+realline', SUM(abs(accountbalancesnode-(frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'margsum+unrealline', SUM(abs(accountbalancesnode-(margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'margsum+realline', SUM(abs(accountbalancesnode-(margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'unrealline+realline', SUM(abs(accountbalancesnode-((-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+availsum+unrealline', SUM(abs(accountbalancesnode-(walletsum+availsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+availsum+realline', SUM(abs(accountbalancesnode-(walletsum+availsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+frozensum+unrealline', SUM(abs(accountbalancesnode-(walletsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+frozensum+realline', SUM(abs(accountbalancesnode-(walletsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+margsum+unrealline', SUM(abs(accountbalancesnode-(walletsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+margsum+realline', SUM(abs(accountbalancesnode-(walletsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'walletsum+unrealline+realline', SUM(abs(accountbalancesnode-(walletsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+frozensum+unrealline', SUM(abs(accountbalancesnode-(availsum+frozensum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+frozensum+realline', SUM(abs(accountbalancesnode-(availsum+frozensum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+margsum+unrealline', SUM(abs(accountbalancesnode-(availsum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+margsum+realline', SUM(abs(accountbalancesnode-(availsum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'availsum+unrealline+realline', SUM(abs(accountbalancesnode-(availsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'frozensum+margsum+unrealline', SUM(abs(accountbalancesnode-(frozensum+margsum+(-unrealline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'frozensum+margsum+realline', SUM(abs(accountbalancesnode-(frozensum+margsum+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'frozensum+unrealline+realline', SUM(abs(accountbalancesnode-(frozensum+(-unrealline)+(-realline)))<0.005) FROM accountbalances
UNION ALL SELECT 'accountbalancesnode='||'margsum+unrealline+realline', SUM(abs(accountbalancesnode-(margsum+(-unrealline)+(-realline)))<0.005) FROM accountbalances ORDER BY 2 DESC LIMIT 5;
```

### val_draft.py

The draft's in-memory run of the validator. It runs no SQL and opens no database.

```python
import sys
sys.dont_write_bytecode = True
from warrant.freeze.validate import _defect, reference_claim_problems
T = ["UPDATE accountbalances SET realline = -realline, unrealline = -unrealline"]
d = {
 "id": "pnl-sign", "database": "crypto",
 "slot": {"claim_kind": "value_meaning", "subject": "accountbalances.realline"},
 "touches": {"accountbalances": ["realline", "unrealline"]},
 "transformation": T,
 "reference_claim": "The realised profit and loss realline in accountbalances is signed from the exchange's side: a positive value is a realised loss for the account holder and a negative value is a realised profit.",
 "readings": [
  {"id": "positive-is-loss", "statement": "x", "form": "world_fixed", "transformation": T, "holds": True, "is_true": True},
  {"id": "positive-is-profit", "statement": "y", "form": "meaning_only", "kind": "convention", "transformation": [], "holds": False, "is_true": False},
 ],
 "drift_reading": {"reading": "positive-is-profit", "expected_drift_type": "convention",
   "reference_claim": "The realised profit and loss realline in accountbalances is signed from the account holder's side: a positive value is a realised profit and a negative value is a realised loss."},
}
print("two readings:", _defect(d, None))
extra = {"id": "counterparty-pnl", "statement": "z", "form": "meaning_only", "kind": "provenance", "transformation": [], "holds": True, "is_true": False}
d2 = dict(d, readings=d["readings"] + [extra])
print("with a holds:true meaning-only paraphrase:", _defect(d2, None))
w = dict(extra, id="as-released", form="world_fixed", transformation=[], holds=False); w.pop("kind")
d3 = dict(d, readings=d["readings"] + [w], drift_reading={"reading": "as-released", "expected_drift_type": "data_part"})
print("with clean world-fixed []:", _defect(d3, None))
```

## The review's check of the aligned row keys

Run on 2026-10-28 during the review, with `sqlite3 -readonly` on `file:<scratch>/trial149/clean/crypto.sqlite?mode=ro`, a clean copy whose SHA-256 matches `release.sha256.crypto`.

- `SELECT SUM(a.accountbalancesnode = u.usersnode), COUNT(*) FROM accountbalances a JOIN users u ON u.userstamp = a.usertag` gives 1000|1000.
- `SELECT SUM(o.orderspivot = u.usersnode), COUNT(*) FROM orders o JOIN users u ON u.userstamp = o.userlink` gives 999|999.

## Helper scripts

The searches above name four helper scripts. Each opens its clean copy with `mode=ro`. `c61_rule_probe.py` runs its own three SELECT statements; the other three run only the statements passed to them.

### c61_rule_probe.py

```python
# Read-only emulation of rule.py _best_combo on orderexecutions subsets (no battery run).
import sqlite3, itertools, sys
DB = "file:<scratch>/vm61/crypto_clean.sqlite?mode=ro"
con = sqlite3.connect(DB, uri=True)
pool = ["orderexecmark", "fillcount", "remaincount", "fillquote", "fillsum"]
subsets = {
    "clean": "1=1",
    "true_api_cut": "ordersmark NOT IN (SELECT recordvault FROM orders WHERE orderbase='API')",
    "tail_cut": "orderexecmark <= 766",
}
for name, where in subsets.items():
    rows = con.execute(f"SELECT {', '.join(pool)} FROM orderexecutions WHERE {where}").fetchall()
    best_overall = 0.0
    for ti, t in enumerate(pool):
        others = [i for i in range(len(pool)) if i != ti]
        nz = [r for r in rows if r[ti] is not None and r[ti] != 0]
        best = (0.0, None)
        for k in (2, 3):
            for combo in itertools.combinations(others, k):
                hits = sum(1 for r in nz if abs(r[ti] - sum((r[c] or 0) for c in combo)) < 0.005)
                share = hits / len(nz) if nz else 0
                if share > best[0]:
                    best = (share, [pool[c] for c in combo])
        best_overall = max(best_overall, best[0])
        print(name, t, "n_nonzero", len(nz), "best_share", round(best[0], 4), best[1])
    print(name, "max share", best_overall, "(rule.py threshold 0.80)")
```

### c1verify/q.py

```python
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
for i, q in enumerate(sys.stdin.read().split(";;")):
    q = q.strip()
    if not q:
        continue
    print("Q>", " ".join(q.split()))
    try:
        for row in con.execute(q).fetchall():
            print("  ", row)
    except Exception as e:
        print("  ERR", e)
```

### c2_q.py

```python
import sqlite3, sys
db = sys.argv[1]
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
for q in sys.argv[2:]:
    print("SQL>", q)
    try:
        for r in con.execute(q).fetchall():
            print("   ", r)
    except Exception as e:
        print("   ERR", e)
```

### v61cov_q.py

```python
import sqlite3, sys
c = sqlite3.connect('file:<scratch>/vm61/alien_clean.sqlite?mode=ro', uri=True)
qs = [l for l in sys.stdin.read().split(';;') if l.strip()]
for q in qs:
    q = q.strip()
    try:
        rows = c.execute(q).fetchall()
    except Exception as e:
        rows = [('ERR', str(e))]
    print('Q:', ' '.join(q.split()))
    for r in rows[:40]:
        print('   ', r)
    if len(rows) > 40: print('    ... %d rows' % len(rows))
```


## The design trial's scripts

Run with `uv run python <script> <scratch dir>` from the repo root, on scratch copies only.

### trial.py

```python
"""Battery-only design trial for the second freeze (#149). No model call. Scratch copies only."""
import json, shutil, sys, hashlib
from pathlib import Path
import yaml
from warrant.defects.inject import load_defect
from warrant.defects.build import build
from warrant.write_line.predict import predict, BatterySettings, record
from warrant.write_line.warrants import slot_warrants

S = Path(sys.argv[1]); out = S / "trial149" / "out"
if out.exists(): shutil.rmtree(out)
out.mkdir(parents=True)
clean_dir = S / "trial149" / "clean"; clean_dir.mkdir(exist_ok=True)
src = S / "vm61" / "crypto_clean.sqlite"
assert hashlib.sha256(src.read_bytes()).hexdigest().startswith("49103c15"), "clean copy hash"
dst = clean_dir / "crypto.sqlite"; shutil.copyfile(src, dst); dst.chmod(0o644)
frozen = yaml.safe_load(Path("freeze/write_line_2.yaml").read_text())
defects = [load_defect(d) for d in frozen["defects"]]
built = build(defects, {"crypto": dst}, out)
for a in built.audits: print("AUDIT", a.defect, a.rows, a.changed, len(a.recoding), a.relation, a.holds)
settings = BatterySettings.from_freeze({"global": frozen["global"]})
p = predict(defects, built, {"crypto": dst}, settings, out / "battery")
for d, c in p.claims.items():
    print("SLOT", d, c.outcome.value)
    for r in c.readings: print("   ", r.reading if hasattr(r,"reading") else r[0], "differs" if r.differs else "same", "holds" if r.holds else "fails")
print("KINDS", {k.value if hasattr(k,"value") else k: v.value for k, v in p.kinds.items()})
print("BRIDGE", {k: v.differs if hasattr(v,"differs") else v for k, v in p.bridge.items()})
print("WARRANTS", {k: str(v) for k, v in slot_warrants(defects, record(p, settings, {}, "")).items()})
injected = built.injected["crypto"]
Path(S / "trial149" / "injected_output.txt").write_bytes(p.outputs[injected])
print("INJECTED_OUTPUT_BYTES", len(p.outputs[injected]))
```

### diff.py

```python
"""Battery-only: the clean copy's battery output against the injected copy's (#149). No model call."""
import json, sys
from pathlib import Path
import yaml
from warrant.battery.normalise import normalise_database
from warrant.data.release import Database, foreign_keys
from warrant.write_line.predict import BatterySettings
S = Path(sys.argv[1]); clean = S / "trial149" / "clean" / "crypto.sqlite"
frozen = yaml.safe_load(Path("freeze/write_line_2.yaml").read_text())
settings = BatterySettings.from_freeze({"global": frozen["global"]})
work = S / "trial149" / "clean_battery"; work.mkdir(exist_ok=True)
out = normalise_database(Database("crypto", clean, foreign_keys(clean), {}, []), settings.fixed_date, work, settings.normalisation)
def items(b): return {(f["check"], f["subject"], f["statement"]) for f in (json.loads(l) for l in b.decode().splitlines() if l.strip())}
a, b = items(out), items((S / "trial149" / "injected_output.txt").read_bytes())
for x in sorted(a - b): print("ONLY CLEAN  ", x[0], x[1], "|", x[2][:160])
for x in sorted(b - a): print("ONLY INJECTED", x[0], x[1], "|", x[2][:160])
```
