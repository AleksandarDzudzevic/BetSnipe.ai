Run the cross-bookmaker audit for sport ID $ARGUMENTS (1=Football, 2=Basketball, 3=Tennis, 4=Hockey, 5=Table Tennis).

```bash
cd PythonScraper && python audit_scrapers.py --sport $ARGUMENTS --match-detail --match-limit 5
```

Analyze the output and report:
1. Coverage per bookmaker (matches, total odds, avg/match, bet types)
2. Any cross-bookmaker key mismatches (different bet_type_id/selection/margin for same real-world bet)
3. Any unmapped markets showing in debug logs

Compare results against COVERAGE_AUDIT.md to see if coverage has improved.
