 SELECT
      (SELECT COUNT(*) FROM matches) AS matches,
      (SELECT COUNT(*) FROM current_odds) AS odds,
      (SELECT COUNT(*) FROM arbitrage_opportunities WHERE is_active = true) AS active_arbs;