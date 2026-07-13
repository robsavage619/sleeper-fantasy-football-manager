"""CDN URL helpers for Sleeper imagery — player photos, team logos, owner avatars.

All URLs are hotlinked from Sleeper's CDN (sleepercdn.com). The React app loads
them directly in <img> tags; no backend caching needed unless building a proxy.
"""

from __future__ import annotations

_CDN = "https://sleepercdn.com"
_ESPN_CDN = "https://a.espncdn.com/combiner/i?img=/i/headshots/nfl/players/full"


def player_photo(sleeper_id: str, thumb: bool = False) -> str:
    """Return the Sleeper CDN URL for a player headshot.

    Args:
        sleeper_id: Sleeper player ID (string key from the /players/nfl dump).
        thumb: If True, return the thumbnail variant (~100px) instead of full.

    Returns:
        HTTPS URL to the player's photo on sleepercdn.com.
    """
    variant = "thumb" if thumb else "players"
    return f"{_CDN}/content/nfl/{variant}/{sleeper_id}.jpg"


def player_photo_espn(espn_id: str) -> str:
    """Return the ESPN CDN URL for a player headshot (fallback when Sleeper is missing).

    Args:
        espn_id: ESPN player ID (from the nflverse ``import_ids()`` crosswalk).

    Returns:
        HTTPS URL to the player's photo on ESPN's CDN.
    """
    return f"{_ESPN_CDN}/{espn_id}.png&w=350&h=254"


def team_logo(team: str) -> str:
    """Return the Sleeper CDN URL for an NFL team logo.

    Args:
        team: Lowercase 2-3 char team abbreviation as used by Sleeper (e.g. ``"sf"``,
            ``"ne"``, ``"kc"``).

    Returns:
        HTTPS URL to the team's logo PNG on sleepercdn.com.
    """
    return f"{_CDN}/images/team_logos/nfl/{team.lower()}.png"


def owner_avatar(avatar_id: str, thumb: bool = False) -> str:
    """Return the Sleeper CDN URL for a user/owner avatar.

    Args:
        avatar_id: Avatar ID from the ``User.metadata["avatar"]`` field.
        thumb: If True, return the thumbnail variant.

    Returns:
        HTTPS URL to the avatar image on sleepercdn.com.
    """
    if thumb:
        return f"{_CDN}/avatars/thumbs/{avatar_id}"
    return f"{_CDN}/avatars/{avatar_id}"
