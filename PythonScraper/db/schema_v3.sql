-- BetSnipe.ai v3.0 Database Schema Extension
-- User Authentication & Personalization (Supabase Auth Integration)
-- Run AFTER schema.sql

-- ============================================
-- USER TABLES (Supabase Auth Integration)
-- ============================================

-- User preferences for notification and display settings
-- Links to Supabase auth.users via user_id (UUID)
CREATE TABLE IF NOT EXISTS user_preferences (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL UNIQUE,  -- References auth.users(id) in Supabase
    min_profit_percentage DECIMAL(5,2) DEFAULT 1.0,  -- Minimum arbitrage profit to notify
    sports INTEGER[] DEFAULT ARRAY[1,2,3,4,5],  -- Sport IDs to track
    bookmakers INTEGER[] DEFAULT ARRAY[1,2,3,4,5,6,7,10],  -- Bookmaker IDs to include
    notification_settings JSONB DEFAULT '{
        "arbitrage_alerts": true,
        "watchlist_odds_change": true,
        "match_start_reminder": false,
        "daily_summary": false,
        "quiet_hours_start": null,
        "quiet_hours_end": null
    }'::jsonb,
    display_settings JSONB DEFAULT '{
        "default_sport": 1,
        "odds_format": "decimal",
        "theme": "system"
    }'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User watchlist for tracking specific matches
CREATE TABLE IF NOT EXISTS user_watchlist (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,  -- References auth.users(id)
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    notify_on_odds_change BOOLEAN DEFAULT true,
    odds_change_threshold DECIMAL(5,2) DEFAULT 0.05,  -- Minimum odds change to notify
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, match_id)
);

-- User devices for push notifications (Expo Push)
CREATE TABLE IF NOT EXISTS user_devices (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,  -- References auth.users(id)
    expo_push_token VARCHAR(255) NOT NULL,
    platform VARCHAR(20) NOT NULL,  -- 'ios', 'android'
    device_id VARCHAR(255),  -- Optional unique device identifier
    device_name VARCHAR(100),  -- User-friendly device name
    is_active BOOLEAN DEFAULT true,
    last_used_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, expo_push_token)
);

-- User arbitrage history (viewed/interacted opportunities)
CREATE TABLE IF NOT EXISTS user_arbitrage_history (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    arbitrage_id INTEGER REFERENCES arbitrage_opportunities(id) ON DELETE SET NULL,
    match_id INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    action VARCHAR(20) NOT NULL,  -- 'viewed', 'saved', 'executed', 'dismissed'
    profit_percentage DECIMAL(8,4),  -- Snapshot at time of interaction
    best_odds JSONB,  -- Snapshot of odds at interaction time
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Push notification delivery log
CREATE TABLE IF NOT EXISTS push_notifications (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL,
    device_id INTEGER REFERENCES user_devices(id) ON DELETE SET NULL,
    notification_type VARCHAR(50) NOT NULL,  -- 'arbitrage', 'watchlist', 'match_start', 'daily_summary'
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    data JSONB,  -- Additional payload data
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'sent', 'delivered', 'failed'
    expo_receipt_id VARCHAR(255),  -- Expo push receipt ID for tracking
    error_message TEXT,
    sent_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- INDEXES FOR USER TABLES
-- ============================================

-- User preferences
CREATE INDEX IF NOT EXISTS idx_user_prefs_user_id ON user_preferences(user_id);

-- Watchlist indexes
CREATE INDEX IF NOT EXISTS idx_watchlist_user ON user_watchlist(user_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_match ON user_watchlist(match_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_user_created ON user_watchlist(user_id, created_at DESC);

-- User devices indexes
CREATE INDEX IF NOT EXISTS idx_user_devices_user ON user_devices(user_id);
CREATE INDEX IF NOT EXISTS idx_user_devices_token ON user_devices(expo_push_token);
CREATE INDEX IF NOT EXISTS idx_user_devices_active ON user_devices(user_id, is_active);

-- User arbitrage history indexes
CREATE INDEX IF NOT EXISTS idx_user_arb_history_user ON user_arbitrage_history(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_arb_history_arbitrage ON user_arbitrage_history(arbitrage_id);

-- Push notifications indexes
CREATE INDEX IF NOT EXISTS idx_push_notif_user ON push_notifications(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_push_notif_status ON push_notifications(status, created_at);
CREATE INDEX IF NOT EXISTS idx_push_notif_type ON push_notifications(notification_type, created_at DESC);

-- ============================================
-- FULL-TEXT SEARCH FOR MATCHES
-- ============================================

-- Add full-text search vector column to matches
ALTER TABLE matches ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Create GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_matches_search ON matches USING GIN(search_vector);

-- Function to update search vector
CREATE OR REPLACE FUNCTION update_match_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := to_tsvector('simple',
        COALESCE(NEW.team1, '') || ' ' ||
        COALESCE(NEW.team2, '') || ' ' ||
        COALESCE(NEW.team1_normalized, '') || ' ' ||
        COALESCE(NEW.team2_normalized, '')
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update search vector
DROP TRIGGER IF EXISTS update_match_search ON matches;
CREATE TRIGGER update_match_search
    BEFORE INSERT OR UPDATE OF team1, team2, team1_normalized, team2_normalized
    ON matches
    FOR EACH ROW
    EXECUTE FUNCTION update_match_search_vector();

-- Update existing matches with search vectors
UPDATE matches SET search_vector = to_tsvector('simple',
    COALESCE(team1, '') || ' ' ||
    COALESCE(team2, '') || ' ' ||
    COALESCE(team1_normalized, '') || ' ' ||
    COALESCE(team2_normalized, '')
);

-- ============================================
-- TRIGGERS FOR USER TABLES
-- ============================================

-- Update timestamp trigger for user_preferences
DROP TRIGGER IF EXISTS update_user_preferences_updated_at ON user_preferences;
CREATE TRIGGER update_user_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- ROW LEVEL SECURITY (Supabase Auth)
-- ============================================

-- Enable RLS on user tables
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_arbitrage_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE push_notifications ENABLE ROW LEVEL SECURITY;

-- Policies for user_preferences
DROP POLICY IF EXISTS "Users can view own preferences" ON user_preferences;
CREATE POLICY "Users can view own preferences" ON user_preferences
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own preferences" ON user_preferences;
CREATE POLICY "Users can insert own preferences" ON user_preferences
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own preferences" ON user_preferences;
CREATE POLICY "Users can update own preferences" ON user_preferences
    FOR UPDATE USING (auth.uid() = user_id);

-- Policies for user_watchlist
DROP POLICY IF EXISTS "Users can view own watchlist" ON user_watchlist;
CREATE POLICY "Users can view own watchlist" ON user_watchlist
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own watchlist" ON user_watchlist;
CREATE POLICY "Users can manage own watchlist" ON user_watchlist
    FOR ALL USING (auth.uid() = user_id);

-- Policies for user_devices
DROP POLICY IF EXISTS "Users can view own devices" ON user_devices;
CREATE POLICY "Users can view own devices" ON user_devices
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can manage own devices" ON user_devices;
CREATE POLICY "Users can manage own devices" ON user_devices
    FOR ALL USING (auth.uid() = user_id);

-- Policies for user_arbitrage_history
DROP POLICY IF EXISTS "Users can view own history" ON user_arbitrage_history;
CREATE POLICY "Users can view own history" ON user_arbitrage_history
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own history" ON user_arbitrage_history;
CREATE POLICY "Users can insert own history" ON user_arbitrage_history
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Policies for push_notifications
DROP POLICY IF EXISTS "Users can view own notifications" ON push_notifications;
CREATE POLICY "Users can view own notifications" ON push_notifications
    FOR SELECT USING (auth.uid() = user_id);

-- ============================================
-- SERVICE ROLE BYPASS (for backend)
-- Note: Backend uses service_role key which bypasses RLS
-- ============================================

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Function to create user preferences on signup (Supabase trigger)
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO user_preferences (user_id)
    VALUES (NEW.id)
    ON CONFLICT (user_id) DO NOTHING;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger on auth.users for new signups (run in Supabase dashboard)
-- This needs to be created via Supabase SQL editor as auth schema is protected
-- DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
-- CREATE TRIGGER on_auth_user_created
--     AFTER INSERT ON auth.users
--     FOR EACH ROW
--     EXECUTE FUNCTION handle_new_user();

-- Function to get users who should receive arbitrage notifications
CREATE OR REPLACE FUNCTION get_arbitrage_notification_recipients(
    p_profit_percentage DECIMAL,
    p_sport_id INTEGER
)
RETURNS TABLE (
    user_id UUID,
    expo_push_token VARCHAR(255),
    min_profit_percentage DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        up.user_id,
        ud.expo_push_token,
        up.min_profit_percentage
    FROM user_preferences up
    JOIN user_devices ud ON ud.user_id = up.user_id
    WHERE ud.is_active = true
    AND up.min_profit_percentage <= p_profit_percentage
    AND p_sport_id = ANY(up.sports)
    AND (up.notification_settings->>'arbitrage_alerts')::boolean = true
    AND (
        -- Check quiet hours
        (up.notification_settings->>'quiet_hours_start') IS NULL
        OR NOT (
            CURRENT_TIME BETWEEN
                (up.notification_settings->>'quiet_hours_start')::time
            AND
                (up.notification_settings->>'quiet_hours_end')::time
        )
    );
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get users watching a specific match
CREATE OR REPLACE FUNCTION get_watchlist_notification_recipients(
    p_match_id INTEGER,
    p_odds_change DECIMAL DEFAULT 0
)
RETURNS TABLE (
    user_id UUID,
    expo_push_token VARCHAR(255),
    notify_on_odds_change BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        uw.user_id,
        ud.expo_push_token,
        uw.notify_on_odds_change
    FROM user_watchlist uw
    JOIN user_devices ud ON ud.user_id = uw.user_id
    JOIN user_preferences up ON up.user_id = uw.user_id
    WHERE uw.match_id = p_match_id
    AND ud.is_active = true
    AND uw.notify_on_odds_change = true
    AND ABS(p_odds_change) >= uw.odds_change_threshold
    AND (up.notification_settings->>'watchlist_odds_change')::boolean = true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- VIEWS
-- ============================================

-- View for user watchlist with match details
CREATE OR REPLACE VIEW v_user_watchlist AS
SELECT
    uw.id,
    uw.user_id,
    uw.match_id,
    uw.notify_on_odds_change,
    uw.odds_change_threshold,
    uw.notes,
    uw.created_at,
    m.team1,
    m.team2,
    m.start_time,
    m.status as match_status,
    s.name as sport_name,
    s.id as sport_id,
    l.name as league_name
FROM user_watchlist uw
JOIN matches m ON uw.match_id = m.id
JOIN sports s ON m.sport_id = s.id
LEFT JOIN leagues l ON m.league_id = l.id;

-- ============================================
-- CLEANUP FUNCTION EXTENSION
-- ============================================

-- Extend cleanup function to handle user data
CREATE OR REPLACE FUNCTION cleanup_old_user_data(days_to_keep INT DEFAULT 90)
RETURNS void AS $$
BEGIN
    -- Delete old arbitrage history (keep 90 days by default)
    DELETE FROM user_arbitrage_history
    WHERE created_at < NOW() - (days_to_keep || ' days')::INTERVAL;

    -- Delete old push notification logs (keep 30 days)
    DELETE FROM push_notifications
    WHERE created_at < NOW() - INTERVAL '30 days';

    -- Deactivate devices not used in 90 days
    UPDATE user_devices
    SET is_active = false
    WHERE last_used_at < NOW() - INTERVAL '90 days'
    AND is_active = true;

    -- Clean up watchlist entries for finished matches older than 7 days
    DELETE FROM user_watchlist uw
    USING matches m
    WHERE uw.match_id = m.id
    AND m.status = 'finished'
    AND m.start_time < NOW() - INTERVAL '7 days';
END;
$$ LANGUAGE plpgsql;
