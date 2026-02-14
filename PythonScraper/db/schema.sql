-- BetSnipe.ai v2.0 Database Schema
-- PostgreSQL (Supabase compatible)

-- ============================================
-- REFERENCE TABLES
-- ============================================

-- Bookmakers reference table
CREATE TABLE IF NOT EXISTS bookmakers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    api_base_url TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sports reference table
CREATE TABLE IF NOT EXISTS sports (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    name_sr VARCHAR(50),  -- Serbian name
    is_active BOOLEAN DEFAULT true
);

-- Bet types reference table
CREATE TABLE IF NOT EXISTS bet_types (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    outcomes INT NOT NULL DEFAULT 2  -- 2 for two-way, 3 for three-way
);

-- Leagues/Competitions
CREATE TABLE IF NOT EXISTS leagues (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    name_normalized VARCHAR(255),
    sport_id INT REFERENCES sports(id),
    country VARCHAR(100),
    external_ids JSONB DEFAULT '{}',  -- {bookmaker_id: external_league_id}
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(name, sport_id)
);

-- ============================================
-- CORE TABLES
-- ============================================

-- Unified matches table (deduplicated across bookmakers)
CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    team1 VARCHAR(255) NOT NULL,
    team2 VARCHAR(255) NOT NULL,
    team1_normalized VARCHAR(255),
    team2_normalized VARCHAR(255),
    sport_id INT REFERENCES sports(id),
    league_id INT REFERENCES leagues(id),
    start_time TIMESTAMPTZ NOT NULL,
    external_ids JSONB DEFAULT '{}',  -- {bookmaker_id: external_match_id}
    status VARCHAR(20) DEFAULT 'upcoming',  -- upcoming, live, finished, cancelled
    metadata JSONB DEFAULT '{}',  -- Additional match info
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Odds snapshots (time-series data for historical analysis)
CREATE TABLE IF NOT EXISTS odds_history (
    id BIGSERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker_id INT REFERENCES bookmakers(id),
    bet_type_id INT REFERENCES bet_types(id),
    margin DECIMAL(5,2) DEFAULT 0,
    selection VARCHAR(50) DEFAULT '',  -- outcome identifier for multi-outcome markets
    odd1 DECIMAL(8,3),
    odd2 DECIMAL(8,3),
    odd3 DECIMAL(8,3),  -- NULL for two-way bets
    recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Current odds (latest snapshot for fast queries)
CREATE TABLE IF NOT EXISTS current_odds (
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    bookmaker_id INT REFERENCES bookmakers(id),
    bet_type_id INT REFERENCES bet_types(id),
    margin DECIMAL(5,2) DEFAULT 0,
    selection VARCHAR(50) DEFAULT '',  -- outcome identifier for multi-outcome markets
    odd1 DECIMAL(8,3),
    odd2 DECIMAL(8,3),
    odd3 DECIMAL(8,3),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (match_id, bookmaker_id, bet_type_id, margin, selection)
);

-- Arbitrage opportunities
CREATE TABLE IF NOT EXISTS arbitrage_opportunities (
    id SERIAL PRIMARY KEY,
    match_id INT REFERENCES matches(id) ON DELETE CASCADE,
    bet_type_id INT REFERENCES bet_types(id),
    margin DECIMAL(5,2) DEFAULT 0,
    profit_percentage DECIMAL(8,4) NOT NULL,
    best_odds JSONB NOT NULL,  -- [{bookmaker_id, outcome, odd, bookmaker_name}]
    stakes JSONB NOT NULL,     -- [stake1, stake2, stake3] for 100 unit bet
    total_stake DECIMAL(10,2) DEFAULT 100,
    arb_hash CHAR(32) UNIQUE,
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    notified_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,  -- When match starts
    is_active BOOLEAN DEFAULT true
);

-- Notification log
CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    arbitrage_id INT REFERENCES arbitrage_opportunities(id),
    channel VARCHAR(50) NOT NULL,  -- telegram, push, email
    status VARCHAR(20) DEFAULT 'pending',  -- pending, sent, failed
    message TEXT,
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES FOR PERFORMANCE
-- ============================================

-- Matches indexes
CREATE INDEX IF NOT EXISTS idx_matches_start_time ON matches(start_time);
CREATE INDEX IF NOT EXISTS idx_matches_sport ON matches(sport_id);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_sport_status ON matches(sport_id, status);
CREATE INDEX IF NOT EXISTS idx_matches_team1_norm ON matches(team1_normalized);
CREATE INDEX IF NOT EXISTS idx_matches_team2_norm ON matches(team2_normalized);
CREATE INDEX IF NOT EXISTS idx_matches_updated ON matches(updated_at DESC);

-- Odds history indexes (for time-series queries)
CREATE INDEX IF NOT EXISTS idx_odds_history_match ON odds_history(match_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_odds_history_time ON odds_history(recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_odds_history_bookmaker ON odds_history(bookmaker_id, recorded_at DESC);

-- Odds history selection index
CREATE INDEX IF NOT EXISTS idx_odds_history_selection ON odds_history(selection) WHERE selection != '';

-- Current odds indexes
CREATE INDEX IF NOT EXISTS idx_current_odds_match ON current_odds(match_id);
CREATE INDEX IF NOT EXISTS idx_current_odds_bookmaker ON current_odds(bookmaker_id);
CREATE INDEX IF NOT EXISTS idx_current_odds_updated ON current_odds(updated_at DESC);

-- Arbitrage indexes
CREATE INDEX IF NOT EXISTS idx_arbitrage_active ON arbitrage_opportunities(is_active, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrage_match ON arbitrage_opportunities(match_id);
CREATE INDEX IF NOT EXISTS idx_arbitrage_profit ON arbitrage_opportunities(profit_percentage DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrage_expires ON arbitrage_opportunities(expires_at);

-- Leagues indexes
CREATE INDEX IF NOT EXISTS idx_leagues_sport ON leagues(sport_id);
CREATE INDEX IF NOT EXISTS idx_leagues_name_norm ON leagues(name_normalized);

-- ============================================
-- SEED DATA
-- ============================================

-- Insert bookmakers
INSERT INTO bookmakers (id, name, display_name, is_active) VALUES
    (1, 'mozzart', 'Mozzart Bet', true),
    (2, 'meridian', 'Meridian Bet', true),
    (3, 'maxbet', 'MaxBet', true),
    (4, 'admiral', 'Admiral Bet', true),
    (5, 'soccerbet', 'Soccer Bet', true),
    (6, 'superbet', 'SuperBet', true),
    (7, 'merkur', 'Merkur', true),
    (8, '1xbet', '1xBet', true),
    (9, 'lvbet', 'LVBet', true),
    (10, 'topbet', 'TopBet', true),
    (11, 'pinnacle', 'Pinnacle', true)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    display_name = EXCLUDED.display_name,
    is_active = EXCLUDED.is_active;

-- Reset sequence to avoid conflicts
SELECT setval('bookmakers_id_seq', (SELECT MAX(id) FROM bookmakers));

-- Insert sports
INSERT INTO sports (id, name, name_sr, is_active) VALUES
    (1, 'football', 'Fudbal', true),
    (2, 'basketball', 'Kosarka', true),
    (3, 'tennis', 'Tenis', true),
    (4, 'hockey', 'Hokej', true),
    (5, 'table_tennis', 'Stoni Tenis', true),
    (6, 'volleyball', 'Odbojka', true),
    (7, 'handball', 'Rukomet', true),
    (8, 'esports', 'Esport', true)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    name_sr = EXCLUDED.name_sr,
    is_active = EXCLUDED.is_active;

-- Reset sequence
SELECT setval('sports_id_seq', (SELECT MAX(id) FROM sports));

-- Insert bet types
INSERT INTO bet_types (id, name, description, outcomes) VALUES
    (1, 'winner', 'Two-way result', 2),
    (2, '1x2', 'Three-way result', 3),
    (3, '1x2_h1', 'First half 1X2', 3),
    (4, '1x2_h2', 'Second half 1X2', 3),
    (5, 'total_over_under', 'Total O/U', 2),
    (6, 'total_h1', 'First half total O/U', 2),
    (7, 'total_h2', 'Second half total O/U', 2),
    (8, 'btts', 'Both teams to score', 2),
    (9, 'handicap', 'Asian handicap', 2),
    (10, 'total_points', 'Total points', 2),
    (11, 'spread', 'Point spread', 2),
    (12, 'moneyline', 'Moneyline', 2),
    (13, 'double_chance', 'Double chance (1X, 12, X2)', 3),
    (14, 'draw_no_bet', 'Draw no bet', 2),
    (15, 'odd_even', 'Odd/Even total goals', 2),
    (16, 'double_win', 'Both halves winner', 2),
    (17, 'win_to_nil', 'Win to nil', 2),
    (18, 'first_goal', 'First goal scorer team', 3),
    (19, 'half_with_more_goals', 'Half with more goals', 3),
    (20, 'double_chance_h1', 'First half double chance', 3),
    (21, 'draw_no_bet_h1', 'First half draw no bet', 2),
    (22, 'to_qualify', 'To qualify / advance', 2),
    (23, 'correct_score', 'Correct score', 1),
    (24, 'ht_ft', 'Halftime / Fulltime', 1),
    (25, 'total_goals_range', 'Total goals range', 1),
    (26, 'exact_goals', 'Exact number of goals', 1),
    (27, 'team1_goals', 'Team 1 total goals', 1),
    (28, 'team2_goals', 'Team 2 total goals', 1),
    (29, 'h1_total_goals_range', 'H1 total goals range', 1),
    (30, 'h2_total_goals_range', 'H2 total goals range', 1),
    (31, 'team1_goals_h1', 'Team 1 goals first half', 1),
    (32, 'team2_goals_h1', 'Team 2 goals first half', 1),
    (33, 'team1_goals_h2', 'Team 1 goals second half', 1),
    (34, 'team2_goals_h2', 'Team 2 goals second half', 1),
    (35, 'goals_h1_h2_combo', 'Goals H1 and H2 combination', 1),
    (36, 'first_goal_result', 'First goal + final result', 1),
    (37, 'ht_ft_double_chance', 'HT/FT double chance', 1),
    (38, 'result_total_goals', 'Result + total goals', 1),
    (39, 'result_combo', 'Result combinations', 1),
    (40, 'result_half_goals', 'Result + half with more goals', 1),
    (41, 'dc_total_goals', 'Double chance + total goals', 1),
    (42, 'dc_half_goals', 'DC + half with more goals', 1),
    (43, 'dc_combo', 'Double chance combinations', 1),
    (44, 'ht_ft_total_goals', 'HT/FT + total goals', 1),
    (45, 'ht_ft_combo', 'HT/FT combinations', 1),
    (46, 'btts_combo', 'BTTS combinations', 1),
    (47, 'mozzart_chance', 'Mozzart chance (proprietary)', 1),
    (48, 'team1_total_points', 'Team 1 total points O/U', 2),
    (49, 'team2_total_points', 'Team 2 total points O/U', 2),
    (50, 'handicap_h1', 'First half handicap', 2),
    (51, 'team1_total_h1', 'Team 1 first half total O/U', 2),
    (52, 'team2_total_h1', 'Team 2 first half total O/U', 2),
    (53, 'most_efficient_quarter_total', 'Most efficient quarter total O/U', 2),
    (54, 'quarter_most_points', 'Quarter with most points', 1),
    (55, 'h1_result_total', 'H1 result + H1 total', 1),
    -- Tennis-specific markets
    (56, 'handicap_sets', 'Set handicap', 2),
    (57, 'first_set_winner', 'First set winner', 2),
    (58, 'handicap_games_s1', 'First set game handicap', 2),
    (59, 'odd_even_s1', 'First set odd/even', 2),
    (60, 'tiebreak_s1', 'First set tiebreak yes/no', 2),
    (61, 'odd_even_s2', 'Second set odd/even', 2),
    (62, 'tiebreak_s2', 'Second set tiebreak yes/no', 2),
    (63, 'set_with_more_games', 'Set with more games', 3),
    (64, 'first_set_match_combo', 'First set + match result', 1),
    (65, 'exact_sets', 'Exact number of sets', 1),
    (66, 'games_range_s1', 'First set games range', 1),
    (67, 'games_range_s2', 'Second set games range', 1),
    (68, 'winner_total_games', 'Winner + total games combo', 1),
    (69, 'p1_win_games_s1', 'Player 1 wins + S1 games', 1),
    (70, 'p1_win_odd_even_s1', 'Player 1 wins + S1 odd/even', 2),
    (71, 'p2_win_games_s1', 'Player 2 wins + S1 games', 1),
    (72, 'p2_win_odd_even_s1', 'Player 2 wins + S1 odd/even', 2),
    (73, 'winner_set_more_games', 'Winner + set with more games', 1),
    -- Hockey-specific markets
    (74, 'h1_result_total_goals', 'H1/P1 result + total goals', 1)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    outcomes = EXCLUDED.outcomes;

-- Reset sequence
SELECT setval('bet_types_id_seq', (SELECT MAX(id) FROM bet_types));

-- ============================================
-- FUNCTIONS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for matches table
DROP TRIGGER IF EXISTS update_matches_updated_at ON matches;
CREATE TRIGGER update_matches_updated_at
    BEFORE UPDATE ON matches
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for current_odds table
DROP TRIGGER IF EXISTS update_current_odds_updated_at ON current_odds;
CREATE TRIGGER update_current_odds_updated_at
    BEFORE UPDATE ON current_odds
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to clean old data (run periodically)
CREATE OR REPLACE FUNCTION cleanup_old_data(days_to_keep INT DEFAULT 7)
RETURNS void AS $$
BEGIN
    -- Delete old odds history (keep last 7 days by default)
    DELETE FROM odds_history
    WHERE recorded_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    -- Mark old matches as finished
    UPDATE matches
    SET status = 'finished'
    WHERE start_time < NOW() - INTERVAL '4 hours'
    AND status = 'upcoming';

    -- Deactivate old arbitrage opportunities
    UPDATE arbitrage_opportunities
    SET is_active = false
    WHERE expires_at < NOW()
    AND is_active = true;

    -- Delete very old matches (older than 30 days)
    DELETE FROM matches
    WHERE start_time < NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- VIEWS
-- ============================================

-- View for active arbitrage with match details
CREATE OR REPLACE VIEW v_active_arbitrage AS
SELECT
    ao.id,
    ao.profit_percentage,
    ao.best_odds,
    ao.stakes,
    ao.detected_at,
    m.team1,
    m.team2,
    m.start_time,
    s.name as sport_name,
    s.name_sr as sport_name_sr,
    bt.name as bet_type_name,
    ao.margin
FROM arbitrage_opportunities ao
JOIN matches m ON ao.match_id = m.id
JOIN sports s ON m.sport_id = s.id
JOIN bet_types bt ON ao.bet_type_id = bt.id
WHERE ao.is_active = true
ORDER BY ao.profit_percentage DESC;

-- View for current odds with match details
CREATE OR REPLACE VIEW v_current_odds AS
SELECT
    co.match_id,
    m.team1,
    m.team2,
    m.start_time,
    s.name as sport_name,
    b.name as bookmaker_name,
    b.display_name as bookmaker_display,
    bt.name as bet_type_name,
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
-- ROW LEVEL SECURITY (Supabase)
-- ============================================

-- Enable RLS on tables (uncomment for Supabase)
-- ALTER TABLE matches ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE current_odds ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE arbitrage_opportunities ENABLE ROW LEVEL SECURITY;

-- Create policies for public read access
-- CREATE POLICY "Allow public read access" ON matches FOR SELECT USING (true);
-- CREATE POLICY "Allow public read access" ON current_odds FOR SELECT USING (true);
-- CREATE POLICY "Allow public read access" ON arbitrage_opportunities FOR SELECT USING (true);
