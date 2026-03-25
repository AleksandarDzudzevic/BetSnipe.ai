-- ============================================================
-- BetSnipe.ai — Odds Database Schema (Hetzner PostgreSQL)
-- ============================================================
-- Purpose: matches, odds, arbitrage detection — write-heavy workload
-- User tables live in Supabase, NOT here
-- ============================================================

-- ============================================
-- REFERENCE TABLES (small, static)
-- ============================================

CREATE TABLE IF NOT EXISTS bookmakers (
    id           SMALLINT PRIMARY KEY,  -- hardcoded IDs (1-12)
    name         VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    is_active    BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS sports (
    id       SMALLINT PRIMARY KEY,  -- hardcoded IDs (1-8)
    name     VARCHAR(50) UNIQUE NOT NULL,
    name_sr  VARCHAR(50),
    is_active BOOLEAN DEFAULT true
);

CREATE TABLE IF NOT EXISTS bet_types (
    id          SMALLINT PRIMARY KEY,  -- hardcoded IDs (1-124)
    name        VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    outcomes    SMALLINT NOT NULL DEFAULT 2  -- 1=selection, 2=two-way, 3=three-way
);

CREATE TABLE IF NOT EXISTS leagues (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    name_normalized VARCHAR(255),
    sport_id        SMALLINT REFERENCES sports(id),
    country         VARCHAR(100),
    external_ids    JSONB DEFAULT '{}',
    UNIQUE(name_normalized, sport_id)
);

-- ============================================
-- CORE TABLES
-- ============================================

-- Deduplicated matches across all bookmakers (~5K active rows)
CREATE TABLE IF NOT EXISTS matches (
    id                 SERIAL PRIMARY KEY,
    team1              VARCHAR(255) NOT NULL,
    team2              VARCHAR(255) NOT NULL,
    team1_normalized   VARCHAR(255) NOT NULL,
    team2_normalized   VARCHAR(255) NOT NULL,
    sport_id           SMALLINT NOT NULL REFERENCES sports(id),
    league_id          INT REFERENCES leagues(id) ON DELETE SET NULL,
    start_time         TIMESTAMPTZ NOT NULL,
    external_ids       JSONB DEFAULT '{}',
    status             VARCHAR(20) DEFAULT 'upcoming',
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),

    -- ON CONFLICT target for bulk upsert deduplication
    CONSTRAINT uq_matches_dedup
        UNIQUE (team1_normalized, team2_normalized, sport_id, start_time)
);

-- Current odds snapshot (~4M rows, rebuilt every scrape cycle)
-- UNLOGGED: no WAL writes = ~2x faster bulk upserts
-- If server crashes, next scrape cycle repopulates in <60 seconds
CREATE UNLOGGED TABLE IF NOT EXISTS current_odds (
    match_id     INT          NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker_id SMALLINT     NOT NULL,
    bet_type_id  SMALLINT     NOT NULL,
    margin       NUMERIC(5,2) NOT NULL DEFAULT 0,
    selection    VARCHAR(50)  NOT NULL DEFAULT '',
    odd1         NUMERIC(8,3),
    odd2         NUMERIC(8,3),
    odd3         NUMERIC(8,3),
    updated_at   TIMESTAMPTZ  DEFAULT NOW(),

    PRIMARY KEY (match_id, bookmaker_id, bet_type_id, margin, selection)
);

-- Odds change history — only records when an odd CHANGES value, not every scrape
-- Kept for the lifetime of the match, cascade-deleted when match expires
-- UNLOGGED: display-only data, rebuilt naturally from scraper activity
CREATE UNLOGGED TABLE IF NOT EXISTS odds_history (
    id           BIGSERIAL PRIMARY KEY,
    match_id     INT          NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker_id SMALLINT     NOT NULL,
    bet_type_id  SMALLINT     NOT NULL,
    margin       NUMERIC(5,2) NOT NULL DEFAULT 0,
    selection    VARCHAR(50)  NOT NULL DEFAULT '',
    odd1         NUMERIC(8,3),
    odd2         NUMERIC(8,3),
    odd3         NUMERIC(8,3),
    recorded_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Detected arbitrage opportunities
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id                SERIAL PRIMARY KEY,
    match_id          INT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    bet_type_id       SMALLINT NOT NULL,
    margin            NUMERIC(5,2) DEFAULT 0,
    profit_percentage NUMERIC(8,4) NOT NULL,
    best_odds         JSONB NOT NULL,
    stakes            JSONB NOT NULL,
    arb_hash          CHAR(32) UNIQUE NOT NULL,
    is_active         BOOLEAN DEFAULT true,
    detected_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at        TIMESTAMPTZ DEFAULT NOW(),
    notified_at       TIMESTAMPTZ,
    expires_at        TIMESTAMPTZ
);

-- Notification log (telegram, push)
CREATE TABLE IF NOT EXISTS notifications (
    id           SERIAL PRIMARY KEY,
    arbitrage_id INT REFERENCES arbitrage_opportunities(id) ON DELETE SET NULL,
    channel      VARCHAR(20) NOT NULL,
    status       VARCHAR(20) DEFAULT 'pending',
    message      TEXT,
    sent_at      TIMESTAMPTZ,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES
-- ============================================
-- Principle: every index must serve a real query pattern.
-- No redundant indexes — they slow down bulk upserts.

-- matches: used by get_upcoming_matches(), arbitrage detection, API
-- The UNIQUE constraint already indexes (team1_normalized, team2_normalized, sport_id, start_time)
CREATE INDEX IF NOT EXISTS idx_matches_upcoming
    ON matches(sport_id, start_time)
    WHERE status = 'upcoming';

-- current_odds: PK index on (match_id, bookmaker_id, bet_type_id, margin, selection)
-- covers all lookup patterns. No additional indexes needed.

-- odds_history: for trends API — fetch history for a match ordered by time
CREATE INDEX IF NOT EXISTS idx_odds_history_match_time
    ON odds_history(match_id, recorded_at DESC);

-- arbitrage: for active arbitrage API endpoint
CREATE INDEX IF NOT EXISTS idx_arb_active
    ON arbitrage_opportunities(profit_percentage DESC)
    WHERE is_active = true;

-- arbitrage: for match cascade and deactivation queries
CREATE INDEX IF NOT EXISTS idx_arb_match
    ON arbitrage_opportunities(match_id);

-- notifications: for lookup by arbitrage_id
CREATE INDEX IF NOT EXISTS idx_notif_arb
    ON notifications(arbitrage_id);

-- leagues: UNIQUE on (name_normalized, sport_id) already covers lookups

-- ============================================
-- TRIGGERS
-- ============================================

-- Auto-update updated_at on matches (only table that needs it)
-- current_odds sets updated_at explicitly in bulk upsert — no trigger needed
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_matches_updated_at ON matches;
CREATE TRIGGER trg_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================
-- ODDS HISTORY TRIGGER
-- ============================================
-- Automatically records odds changes into odds_history when current_odds is updated.
-- Only fires on UPDATE (not INSERT), and only when odd values actually change.
-- Uses IS DISTINCT FROM to handle NULLs correctly (odd2/odd3 can be NULL).

CREATE OR REPLACE FUNCTION record_odds_change()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.odd1 IS DISTINCT FROM NEW.odd1
       OR OLD.odd2 IS DISTINCT FROM NEW.odd2
       OR OLD.odd3 IS DISTINCT FROM NEW.odd3 THEN
        INSERT INTO odds_history (
            match_id, bookmaker_id, bet_type_id, margin, selection,
            odd1, odd2, odd3
        ) VALUES (
            NEW.match_id, NEW.bookmaker_id, NEW.bet_type_id,
            NEW.margin, NEW.selection,
            NEW.odd1, NEW.odd2, NEW.odd3
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_odds_history ON current_odds;
CREATE TRIGGER trg_odds_history
    BEFORE UPDATE ON current_odds
    FOR EACH ROW
    EXECUTE FUNCTION record_odds_change();

-- ============================================
-- CLEANUP FUNCTION
-- ============================================

-- Deletes expired matches in batches — CASCADE handles current_odds, odds_history, arbitrage
-- Batched to avoid long locks that block scraper upserts
-- Call periodically: SELECT cleanup_expired_matches(4);
CREATE OR REPLACE FUNCTION cleanup_expired_matches(
    hours_after_start INT DEFAULT 4,
    batch_size INT DEFAULT 50
)
RETURNS INT AS $$
DECLARE
    deleted_count INT := 0;
    batch_count INT;
BEGIN
    LOOP
        DELETE FROM matches
        WHERE id IN (
            SELECT id FROM matches
            WHERE start_time < NOW() - (hours_after_start || ' hours')::INTERVAL
            LIMIT batch_size
        );
        GET DIAGNOSTICS batch_count = ROW_COUNT;
        deleted_count := deleted_count + batch_count;
        EXIT WHEN batch_count = 0;
        -- Brief pause between batches to let scraper upserts through
        PERFORM pg_sleep(0.1);
    END LOOP;

    -- Clean old notifications (keep 7 days)
    DELETE FROM notifications
    WHERE created_at < NOW() - INTERVAL '7 days';

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEWS
-- ============================================

-- Active arbitrage with match details (used by API)
CREATE OR REPLACE VIEW v_active_arbitrage AS
SELECT
    ao.id,
    ao.profit_percentage,
    ao.best_odds,
    ao.stakes,
    ao.detected_at,
    ao.margin,
    m.team1,
    m.team2,
    m.start_time,
    s.name AS sport_name,
    s.name_sr AS sport_name_sr,
    bt.name AS bet_type_name
FROM arbitrage_opportunities ao
JOIN matches m ON ao.match_id = m.id
JOIN sports s ON m.sport_id = s.id
JOIN bet_types bt ON ao.bet_type_id = bt.id
WHERE ao.is_active = true
ORDER BY ao.profit_percentage DESC;

-- Current odds with match details (used by API)
CREATE OR REPLACE VIEW v_current_odds AS
SELECT
    co.match_id,
    m.team1,
    m.team2,
    m.start_time,
    s.name AS sport_name,
    b.name AS bookmaker_name,
    b.display_name AS bookmaker_display,
    bt.name AS bet_type_name,
    co.margin,
    co.selection,
    co.odd1,
    co.odd2,
    co.odd3,
    co.updated_at
FROM current_odds co
JOIN matches m ON co.match_id = m.id
JOIN sports s ON m.sport_id = s.id
JOIN bookmakers b ON co.bookmaker_id = b.id
JOIN bet_types bt ON co.bet_type_id = bt.id
WHERE m.status = 'upcoming'
ORDER BY m.start_time, m.id, b.name;

-- ============================================
-- SEED DATA
-- ============================================

-- Bookmakers
INSERT INTO bookmakers (id, name, display_name, is_active) VALUES
    (1,  'mozzart',   'Mozzart Bet',  true),
    (2,  'meridian',  'Meridian Bet', false),
    (3,  'maxbet',    'MaxBet',       true),
    (4,  'admiral',   'Admiral Bet',  true),
    (5,  'soccerbet', 'Soccer Bet',   true),
    (6,  'superbet',  'SuperBet',     true),
    (7,  'merkur',    'Merkur',       true),
    (10, 'topbet',    'TopBet',       true),
    (12, 'balkanbet', 'BalkanBet',    true)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    display_name = EXCLUDED.display_name,
    is_active = EXCLUDED.is_active;

-- Sports
INSERT INTO sports (id, name, name_sr, is_active) VALUES
    (1, 'football',     'Fudbal',      true),
    (2, 'basketball',   'Kosarka',     true),
    (3, 'tennis',       'Tenis',       true),
    (4, 'hockey',       'Hokej',       true),
    (5, 'table_tennis', 'Stoni Tenis', true)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    name_sr = EXCLUDED.name_sr,
    is_active = EXCLUDED.is_active;

-- Bet types (all 124)
INSERT INTO bet_types (id, name, description, outcomes) VALUES
    (1,   'winner',                    'Two-way result',                          2),
    (2,   '1x2',                       'Three-way result',                        3),
    (3,   '1x2_h1',                    'First half 1X2',                          3),
    (4,   '1x2_h2',                    'Second half 1X2',                         3),
    (5,   'total_over_under',          'Total O/U',                               2),
    (6,   'total_h1',                  'First half total O/U',                    2),
    (7,   'total_h2',                  'Second half total O/U',                   2),
    (8,   'btts',                      'Both teams to score',                     2),
    (9,   'handicap',                  'Asian handicap',                          2),
    (10,  'total_points',              'Total points',                            2),
    (11,  'spread',                    'Point spread',                            2),
    (12,  'moneyline',                 'Moneyline',                               2),
    (13,  'double_chance',             'Double chance (1X, 12, X2)',              3),
    (14,  'draw_no_bet',              'Draw no bet',                             2),
    (15,  'odd_even',                  'Odd/Even total goals',                    2),
    (16,  'double_win',               'Both halves winner',                      2),
    (17,  'win_to_nil',               'Win to nil',                              2),
    (18,  'first_goal',               'First goal scorer team',                  3),
    (19,  'half_with_more_goals',     'Half with more goals',                    3),
    (20,  'double_chance_h1',         'First half double chance',                3),
    (21,  'draw_no_bet_h1',           'First half draw no bet',                  2),
    (22,  'to_qualify',               'To qualify / advance',                    2),
    (23,  'correct_score',            'Correct score',                           1),
    (24,  'ht_ft',                    'Halftime / Fulltime',                     1),
    (25,  'total_goals_range',        'Total goals range',                       1),
    (26,  'exact_goals',              'Exact number of goals',                   1),
    (27,  'team1_goals',              'Team 1 total goals',                      1),
    (28,  'team2_goals',              'Team 2 total goals',                      1),
    (29,  'h1_total_goals_range',     'H1 total goals range',                    1),
    (30,  'h2_total_goals_range',     'H2 total goals range',                    1),
    (31,  'team1_goals_h1',           'Team 1 goals first half',                 1),
    (32,  'team2_goals_h1',           'Team 2 goals first half',                 1),
    (33,  'team1_goals_h2',           'Team 1 goals second half',                1),
    (34,  'team2_goals_h2',           'Team 2 goals second half',                1),
    (35,  'goals_h1_h2_combo',        'Goals H1 and H2 combination',             1),
    (36,  'first_goal_result',        'First goal + final result',               1),
    (37,  'ht_ft_double_chance',      'HT/FT double chance',                     1),
    (38,  'result_total_goals',       'Result + total goals',                    1),
    (39,  'result_combo',             'Result combinations',                     1),
    (40,  'result_half_goals',        'Result + half with more goals',           1),
    (41,  'dc_total_goals',           'Double chance + total goals',             1),
    (42,  'dc_half_goals',            'DC + half with more goals',               1),
    (43,  'dc_combo',                 'Double chance combinations',              1),
    (44,  'ht_ft_total_goals',        'HT/FT + total goals',                    1),
    (45,  'ht_ft_combo',              'HT/FT combinations',                     1),
    (46,  'btts_combo',               'BTTS combinations',                      1),
    (47,  'mozzart_chance',           'Mozzart chance (proprietary)',            1),
    (48,  'team1_total_points',       'Team 1 total points O/U',                2),
    (49,  'team2_total_points',       'Team 2 total points O/U',                2),
    (50,  'handicap_h1',              'First half handicap',                     2),
    (51,  'team1_total_h1',           'Team 1 first half total O/U',            2),
    (52,  'team2_total_h1',           'Team 2 first half total O/U',            2),
    (53,  'most_efficient_quarter_total', 'Most efficient quarter total O/U',   2),
    (54,  'quarter_most_points',      'Quarter with most points',               1),
    (55,  'h1_result_total',          'H1 result + H1 total',                   1),
    (56,  'handicap_sets',            'Set handicap',                            2),
    (57,  'first_set_winner',         'First set winner',                        2),
    (58,  'handicap_games_s1',        'First set game handicap',                 2),
    (59,  'odd_even_s1',              'First set odd/even',                      2),
    (60,  'tiebreak_s1',              'First set tiebreak yes/no',               2),
    (61,  'odd_even_s2',              'Second set odd/even',                     2),
    (62,  'tiebreak_s2',              'Second set tiebreak yes/no',              2),
    (63,  'set_with_more_games',      'Set with more games',                     3),
    (64,  'first_set_match_combo',    'First set + match result',                1),
    (65,  'exact_sets',               'Exact number of sets',                    1),
    (66,  'games_range_s1',           'First set games range',                   1),
    (67,  'games_range_s2',           'Second set games range',                  1),
    (68,  'winner_total_games',       'Winner + total games combo',              1),
    (69,  'p1_win_games_s1',          'Player 1 wins + S1 games',               1),
    (70,  'p1_win_odd_even_s1',       'Player 1 wins + S1 odd/even',            2),
    (71,  'p2_win_games_s1',          'Player 2 wins + S1 games',               1),
    (72,  'p2_win_odd_even_s1',       'Player 2 wins + S1 odd/even',            2),
    (73,  'winner_set_more_games',    'Winner + set with more games',            1),
    (74,  'h1_result_total_goals',    'H1/P1 result + total goals',             1),
    (75,  'double_chance_h2',         'Second half double chance',               3),
    (76,  'draw_no_bet_h2',           'Second half draw no bet',                 2),
    (77,  'odd_even_h1',              'First half odd/even',                     2),
    (78,  'odd_even_h2',              'Second half odd/even',                    2),
    (79,  'correct_score_h1',         'First half correct score',                1),
    (80,  'handicap_3way',            'European handicap (3-way)',               3),
    (81,  'team1_total_h2',           'Team 1 second half total O/U',           2),
    (82,  'team2_total_h2',           'Team 2 second half total O/U',           2),
    (83,  'btts_h1',                  'Both teams to score first half',          2),
    (84,  'btts_h2',                  'Both teams to score second half',         2),
    (85,  'handicap_h2',              'Second half handicap',                    2),
    (86,  'team1_clean_sheet',        'Team 1 clean sheet',                      2),
    (87,  'team2_clean_sheet',        'Team 2 clean sheet',                      2),
    (88,  'race_to_goals',            'Race to N goals',                         1),
    (89,  'last_goal',                'Last goal team',                          3),
    (90,  'total_corners',            'Total corners O/U',                       2),
    (91,  'total_cards',              'Total cards O/U',                         2),
    (92,  'corners_handicap',         'Corners handicap',                        2),
    (93,  'cards_handicap',           'Cards handicap',                          2),
    (94,  'team1_corners',            'Team 1 corners O/U',                      2),
    (95,  'team2_corners',            'Team 2 corners O/U',                      2),
    (96,  'first_corner',             'First corner',                            2),
    (97,  'last_corner',              'Last corner',                             2),
    (98,  'total_offsides',           'Total offsides O/U',                      2),
    (99,  'total_throw_ins',          'Total throw-ins O/U',                     2),
    (100, 'total_fouls',              'Total fouls O/U',                         2),
    (101, 'total_shots',              'Total shots O/U',                         2),
    (102, 'total_shots_on_target',    'Total shots on target O/U',              2),
    (103, 'total_goal_kicks',         'Total goal kicks O/U',                    2),
    (104, 'first_card',               'First card team',                         2),
    (105, 'penalty_awarded',          'Penalty awarded yes/no',                  2),
    (106, 'red_card_shown',           'Red card shown yes/no',                   2),
    (107, 'corners_odd_even',         'Corners odd/even',                        2),
    (108, 'result_btts',              'Result + BTTS combo',                     1),
    (109, 'dc_btts',                  'Double chance + BTTS combo',              1),
    (110, 'total_goals_exact_range',  'Total goals exact range',                 1),
    (111, 'multi_goal',               'Multi-goal range',                        1),
    (112, 'highest_scoring_half',     'Highest scoring half',                    3),
    (113, 'half_btts',                'Half + BTTS combo',                       1),
    (114, 'goal_range_h1',            'First half goal range',                   1),
    (115, 'goal_range_h2',            'Second half goal range',                  1),
    (116, 'team1_exact_goals',        'Team 1 exact goals',                      1),
    (117, 'team2_exact_goals',        'Team 2 exact goals',                      1),
    (118, 'winning_margin',           'Winning margin',                          1),
    (119, 'team1_goals_odd_even',     'Team 1 goals odd/even',                   2),
    (120, 'team2_goals_odd_even',     'Team 2 goals odd/even',                   2),
    (121, 'h1_total_exact_range',     'H1 total exact range',                    1),
    (122, 'h2_total_exact_range',     'H2 total exact range',                    1),
    (123, 'result_total_exact',       'Result + total exact combo',              1),
    (124, 'dc_total_exact',           'DC + total exact combo',                  1)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    outcomes = EXCLUDED.outcomes;

-- ============================================
-- SCHEDULED CLEANUP
-- ============================================
-- Run periodically via cron or pg_cron:
--   SELECT cleanup_expired_matches(4);
-- This deletes matches that started 4+ hours ago.
-- CASCADE automatically removes their current_odds, odds_history, and arbitrage rows.
