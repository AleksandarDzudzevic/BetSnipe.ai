Expand coverage for bookmaker $ARGUMENTS. Follow these steps:

1. **Discover unmapped markets**: Run the scraper with DEBUG logging and grep for unmapped markets
2. **Understand the API**: Check if markets have inline labels or need external config endpoints
3. **Map to existing bet_type_ids**: Use config.py BET_TYPES (IDs 1-124). Only create new IDs if no existing one fits
4. **Implement parsers**: Add market entries to the scraper's dispatch maps
5. **Normalize selections**: Ensure selection format matches the standard (H1:/H2: prefixes, H/A for teams, &/|// separators)
6. **Verify cross-bookmaker consistency**: Run `/audit 1` and check the new markets match other bookmakers

Key files:
- Scraper: `PythonScraper/core/scrapers/<bookmaker>.py`
- Config: `PythonScraper/core/config.py`
- Audit: `PythonScraper/audit_scrapers.py`
- Reference: `COVERAGE_AUDIT.md`

Standard conventions:
- positive margin = home advantage
- Selection format: H1:/H2: for halves, H/A for teams, FT: for full-time in combos
- Separators: & for combo, | for OR, / for HT/FT (never dash)
- Use `PythonScraper/claude_test/` for any temporary test scripts
