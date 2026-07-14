from __future__ import annotations

from sleeper_ffm.model import news_feed as nf


def test_injury_alert_severity_tiers() -> None:
    out = nf._injury_alert(
        {"player_id": "1", "full_name": "Hurt Guy", "position": "RB", "injury_status": "IR"}
    )
    que = nf._injury_alert(
        {"player_id": "2", "full_name": "Maybe", "position": "WR", "injury_status": "Questionable"}
    )
    healthy = nf._injury_alert({"player_id": "3", "position": "WR", "injury_status": None})
    assert out is not None and out.severity == "WARN"
    assert que is not None and que.severity == "WATCH"
    assert healthy is None


def test_depth_alert_only_flags_buried_players() -> None:
    starter = nf._depth_alert({"player_id": "1", "position": "RB", "depth_chart_order": 1})
    buried = nf._depth_alert(
        {"player_id": "2", "full_name": "Deep Guy", "position": "RB", "depth_chart_order": 3}
    )
    assert starter is None
    assert buried is not None and buried.kind == "DEPTH"
