-- BetSnipe.ai v4 Migration: Selection-based markets
-- Adds selection column to current_odds and odds_history for multi-outcome markets
-- Backward compatible: all existing data has selection=''

-- ============================================
-- Step 1: Add selection column to current_odds
-- ============================================

ALTER TABLE current_odds ADD COLUMN IF NOT EXISTS selection VARCHAR(50) DEFAULT '';

-- Drop old PK, create new one including selection
ALTER TABLE current_odds DROP CONSTRAINT current_odds_pkey;
ALTER TABLE current_odds ADD PRIMARY KEY (match_id, bookmaker_id, bet_type_id, margin, selection);

-- ============================================
-- Step 2: Add selection column to odds_history
-- ============================================

ALTER TABLE odds_history ADD COLUMN IF NOT EXISTS selection VARCHAR(50) DEFAULT '';

-- Index for querying selection-based markets
CREATE INDEX IF NOT EXISTS idx_odds_history_selection ON odds_history(selection) WHERE selection != '';

-- ============================================
-- Step 3: Add new bet types (15-47)
-- ============================================

INSERT INTO bet_types (id, name, description, outcomes) VALUES
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
ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, description = EXCLUDED.description, outcomes = EXCLUDED.outcomes;

SELECT setval('bet_types_id_seq', (SELECT MAX(id) FROM bet_types));
