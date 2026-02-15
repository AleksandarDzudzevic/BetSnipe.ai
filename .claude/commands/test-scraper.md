Test a specific scraper without database. Usage: /test-scraper <scraper_name> [sport_id]

Examples:
- /test-scraper superbet
- /test-scraper admiral 1

```bash
cd PythonScraper && python test_scrapers.py --scraper $ARGUMENTS
```

Analyze the output:
1. How many matches and odds were scraped per sport
2. Check for any errors or warnings
3. Report avg odds/match and bet type distribution
4. Look for any "[Unmapped]" debug messages indicating missing market mappings
