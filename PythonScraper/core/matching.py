"""
Enhanced match matching for BetSnipe.ai v2.0

Multi-field scoring algorithm combining:
- Team name similarity (RapidFuzz)
- Time proximity
- League matching
- Odds similarity bonus
"""

import re
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any

from rapidfuzz import fuzz

from .config import settings, SPORTS

logger = logging.getLogger(__name__)


# Cyrillic to Latin transliteration map (Serbian)
CYRILLIC_TO_LATIN = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'ђ': 'dj', 'е': 'e',
    'ж': 'z', 'з': 'z', 'и': 'i', 'ј': 'j', 'к': 'k', 'л': 'l', 'љ': 'lj',
    'м': 'm', 'н': 'n', 'њ': 'nj', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's',
    'т': 't', 'ћ': 'c', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'c', 'ч': 'c',
    'џ': 'dz', 'ш': 's',
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Ђ': 'Dj', 'Е': 'E',
    'Ж': 'Z', 'З': 'Z', 'И': 'I', 'Ј': 'J', 'К': 'K', 'Л': 'L', 'Љ': 'Lj',
    'М': 'M', 'Н': 'N', 'Њ': 'Nj', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S',
    'Т': 'T', 'Ћ': 'C', 'У': 'U', 'Ф': 'F', 'Х': 'H', 'Ц': 'C', 'Ч': 'C',
    'Џ': 'Dz', 'Ш': 'S',
}

# Common suffixes to remove from team names
TEAM_SUFFIXES = [
    r'\s+(fc|fk|sk|bc|hc|kk|rk|ok|sc|ac|as|ss|us|cd|cf|sd|ud|rc|afc|sfc)$',
    r'\s+\d{4}$',  # Year suffixes like "2024"
    r'\s+\(w\)$',  # Women indicator
    r'\s+\(e\)$',  # Esports indicator
    r'\s+esports?$',
    r'\s+gaming$',
]

# Category patterns (must match exactly between teams)
CATEGORY_PATTERNS = {
    'u15': r'\b(u-?15|under.?15|jun(?:ior)?s?\s*15)\b',
    'u16': r'\b(u-?16|under.?16|jun(?:ior)?s?\s*16)\b',
    'u17': r'\b(u-?17|under.?17|jun(?:ior)?s?\s*17)\b',
    'u18': r'\b(u-?18|under.?18|jun(?:ior)?s?\s*18)\b',
    'u19': r'\b(u-?19|under.?19|jun(?:ior)?s?\s*19)\b',
    'u20': r'\b(u-?20|under.?20|jun(?:ior)?s?\s*20)\b',
    'u21': r'\b(u-?21|under.?21|jun(?:ior)?s?\s*21)\b',
    'u23': r'\b(u-?23|under.?23)\b',
    'women': r'\b(wom[ae]n|w\)|ladies|female|zene)\b',
    'reserves': r'\b(reserves?|res\.|ii|b\s*team)\b',
    'youth': r'\b(youth|omladinci|kadeti|pioniri)\b',
    'amateur': r'\b(amat(?:eu)?r|ljubitelji)\b',
}


@dataclass
class MatchScore:
    """Result of match comparison."""
    is_match: bool
    confidence: float
    team_score: float
    time_score: float
    league_score: float
    odds_bonus: float
    swapped: bool = False
    details: Dict[str, Any] = None


class MatchMatcher:
    """
    Enhanced match matching engine.

    Combines multiple signals to determine if two matches are the same:
    1. Team name similarity (primary)
    2. Time proximity (secondary)
    3. League matching (optional bonus)
    4. Odds similarity (optional bonus)
    """

    def __init__(self):
        self.threshold = settings.match_similarity_threshold

    def normalize_team_name(self, name: str) -> str:
        """
        Normalize team name for comparison.

        Steps:
        1. Transliterate Cyrillic to Latin
        2. Convert to lowercase
        3. Remove common suffixes (FC, FK, etc.)
        4. Remove special characters
        5. Normalize whitespace
        """
        if not name:
            return ""

        # Transliterate Cyrillic
        normalized = ''.join(CYRILLIC_TO_LATIN.get(c, c) for c in name)

        # Lowercase
        normalized = normalized.lower()

        # Remove category markers (but remember them for hard filter)
        for pattern in CATEGORY_PATTERNS.values():
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

        # Remove common suffixes
        for suffix in TEAM_SUFFIXES:
            normalized = re.sub(suffix, '', normalized, flags=re.IGNORECASE)

        # Remove special characters
        normalized = re.sub(r'[^\w\s]', ' ', normalized)

        # Normalize whitespace
        normalized = ' '.join(normalized.split())

        return normalized.strip()

    def extract_categories(self, team1: str, team2: str) -> Dict[str, bool]:
        """Extract category markers from team names."""
        combined = f"{team1} {team2}".lower()
        categories = {}
        for cat, pattern in CATEGORY_PATTERNS.items():
            categories[cat] = bool(re.search(pattern, combined, re.IGNORECASE))
        return categories

    def normalize_tennis_player(self, name: str) -> str:
        """
        Normalize tennis player name to (surname, initial) format.
        "Novak Djokovic" -> "djokovic n"
        "N. Djokovic" -> "djokovic n"
        """
        name = self.normalize_team_name(name)
        parts = name.split()

        if len(parts) >= 2:
            # Check if first part is initial
            if len(parts[0]) <= 2:
                # "N Djokovic" format
                return f"{parts[-1]} {parts[0][0]}"
            else:
                # "Novak Djokovic" format
                return f"{parts[-1]} {parts[0][0]}"
        return name

    def calculate_team_similarity(
        self,
        team1_a: str,
        team2_a: str,
        team1_b: str,
        team2_b: str,
        sport_id: int
    ) -> Tuple[float, bool]:
        """
        Calculate team name similarity between two matches.

        Returns:
            Tuple of (similarity_score, is_swapped)
            is_swapped indicates if teams were in reversed order
        """
        # Normalize names
        if sport_id == 3:  # Tennis
            t1a = self.normalize_tennis_player(team1_a)
            t2a = self.normalize_tennis_player(team2_a)
            t1b = self.normalize_tennis_player(team1_b)
            t2b = self.normalize_tennis_player(team2_b)
        else:
            t1a = self.normalize_team_name(team1_a)
            t2a = self.normalize_team_name(team2_a)
            t1b = self.normalize_team_name(team1_b)
            t2b = self.normalize_team_name(team2_b)

        # Check categories (hard filter)
        cats_a = self.extract_categories(team1_a, team2_a)
        cats_b = self.extract_categories(team1_b, team2_b)

        if cats_a != cats_b:
            # Categories don't match - no match possible
            return 0.0, False

        # Calculate similarity both ways
        # Normal order: t1a vs t1b, t2a vs t2b
        sim1_normal = fuzz.ratio(t1a, t1b)
        sim2_normal = fuzz.ratio(t2a, t2b)
        score_normal = (sim1_normal + sim2_normal) / 2

        # Swapped order: t1a vs t2b, t2a vs t1b
        sim1_swapped = fuzz.ratio(t1a, t2b)
        sim2_swapped = fuzz.ratio(t2a, t1b)
        score_swapped = (sim1_swapped + sim2_swapped) / 2

        if score_swapped > score_normal:
            return score_swapped, True
        return score_normal, False

    def calculate_time_score(
        self,
        time_a: datetime,
        time_b: datetime,
        sport_id: int
    ) -> float:
        """
        Calculate time proximity score.

        Returns 0-100 based on how close the times are.
        Tighter windows for sports like tennis, looser for football.
        """
        # Get sport-specific time window
        sport_config = SPORTS.get(sport_id, {})
        max_window_minutes = sport_config.get('time_window_minutes', 30)

        # Calculate difference in minutes
        diff_seconds = abs((time_a - time_b).total_seconds())
        diff_minutes = diff_seconds / 60

        if diff_minutes > max_window_minutes * 4:  # Beyond 4x window = 0
            return 0.0

        if diff_minutes <= 5:  # Within 5 minutes = perfect
            return 100.0

        if diff_minutes <= max_window_minutes:  # Within window = high score
            return 100 - (diff_minutes / max_window_minutes) * 20

        # Beyond window but within 4x = declining score
        return max(0, 80 - (diff_minutes - max_window_minutes) * 2)

    def calculate_league_score(
        self,
        league_a: Optional[str],
        league_b: Optional[str]
    ) -> float:
        """Calculate league name similarity bonus."""
        if not league_a or not league_b:
            return 0.0

        # Normalize league names
        la = self.normalize_team_name(league_a)
        lb = self.normalize_team_name(league_b)

        # Calculate similarity
        similarity = fuzz.ratio(la, lb)

        # Only give bonus for high similarity
        if similarity >= 80:
            return 10.0
        elif similarity >= 60:
            return 5.0
        return 0.0

    def calculate_odds_bonus(
        self,
        odds_a: Optional[List[float]],
        odds_b: Optional[List[float]],
        tolerance: float = 0.20
    ) -> float:
        """
        Calculate odds similarity bonus.

        If odds are within tolerance (20% by default), give bonus.
        This helps disambiguate between similar-named teams.
        """
        if not odds_a or not odds_b:
            return 0.0

        if len(odds_a) != len(odds_b):
            return 0.0

        # Check if all odds are within tolerance
        all_within = True
        for oa, ob in zip(odds_a, odds_b):
            if oa and ob:
                ratio = min(oa, ob) / max(oa, ob)
                if ratio < (1 - tolerance):
                    all_within = False
                    break

        return 5.0 if all_within else 0.0

    def match(
        self,
        team1_a: str,
        team2_a: str,
        team1_b: str,
        team2_b: str,
        sport_id: int,
        time_a: datetime,
        time_b: datetime,
        league_a: Optional[str] = None,
        league_b: Optional[str] = None,
        odds_a: Optional[List[float]] = None,
        odds_b: Optional[List[float]] = None
    ) -> MatchScore:
        """
        Determine if two matches are the same.

        Args:
            team1_a, team2_a: Teams from first source
            team1_b, team2_b: Teams from second source
            sport_id: Sport ID
            time_a, time_b: Match start times
            league_a, league_b: Optional league names
            odds_a, odds_b: Optional odds for comparison

        Returns:
            MatchScore with is_match, confidence, and component scores
        """
        # Calculate component scores
        team_score, swapped = self.calculate_team_similarity(
            team1_a, team2_a, team1_b, team2_b, sport_id
        )
        time_score = self.calculate_time_score(time_a, time_b, sport_id)
        league_score = self.calculate_league_score(league_a, league_b)
        odds_bonus = self.calculate_odds_bonus(odds_a, odds_b)

        # Weighted combination
        # Team similarity is most important, time is secondary
        weighted_score = (
            team_score * 0.70 +
            time_score * 0.20 +
            league_score * 0.05 +
            odds_bonus * 0.05
        )

        # Determine if it's a match based on confidence tiers
        is_match = False

        if team_score >= 92:
            # Very high team similarity - auto match
            is_match = True
        elif team_score >= 80 and time_score >= 60:
            # High team similarity + reasonable time proximity
            is_match = True
        elif team_score >= 70 and time_score >= 90:
            # Medium team similarity + very close time
            is_match = True
        elif weighted_score >= self.threshold:
            # Overall score exceeds threshold
            is_match = True

        return MatchScore(
            is_match=is_match,
            confidence=weighted_score,
            team_score=team_score,
            time_score=time_score,
            league_score=league_score,
            odds_bonus=odds_bonus,
            swapped=swapped,
            details={
                'team1_a': team1_a,
                'team2_a': team2_a,
                'team1_b': team1_b,
                'team2_b': team2_b,
            }
        )

    def find_best_match(
        self,
        team1: str,
        team2: str,
        sport_id: int,
        start_time: datetime,
        candidates: List[Dict[str, Any]],
        league_name: Optional[str] = None,
        odds: Optional[List[float]] = None
    ) -> Tuple[Optional[Dict[str, Any]], Optional[MatchScore]]:
        """
        Find the best matching candidate from a list.

        Args:
            team1, team2: Team names to match
            sport_id: Sport ID
            start_time: Match start time
            candidates: List of candidate matches to compare against
            league_name: Optional league name
            odds: Optional odds for comparison

        Returns:
            Tuple of (best_candidate, match_score) or (None, None) if no match
        """
        best_candidate = None
        best_score: Optional[MatchScore] = None

        for candidate in candidates:
            score = self.match(
                team1_a=team1,
                team2_a=team2,
                team1_b=candidate.get('team1', ''),
                team2_b=candidate.get('team2', ''),
                sport_id=sport_id,
                time_a=start_time,
                time_b=candidate.get('start_time', start_time),
                league_a=league_name,
                league_b=candidate.get('league_name'),
                odds_a=odds,
                odds_b=None  # Could add current odds from candidate
            )

            if score.is_match:
                if best_score is None or score.confidence > best_score.confidence:
                    best_candidate = candidate
                    best_score = score

        return best_candidate, best_score


# Global matcher instance
matcher = MatchMatcher()


def normalize_team_name(name: str) -> str:
    """Convenience function for team name normalization."""
    return matcher.normalize_team_name(name)


def calculate_match_similarity(
    team1_a: str,
    team2_a: str,
    team1_b: str,
    team2_b: str,
    sport_id: int,
    time_diff_seconds: float = 0
) -> Tuple[bool, float]:
    """
    Legacy compatibility function.

    Matches the signature of the old team_matching.py function.
    """
    time_a = datetime.utcnow()
    time_b = datetime.utcfromtimestamp(time_a.timestamp() + time_diff_seconds)

    result = matcher.match(
        team1_a, team2_a, team1_b, team2_b,
        sport_id, time_a, time_b
    )

    return result.is_match, result.confidence
