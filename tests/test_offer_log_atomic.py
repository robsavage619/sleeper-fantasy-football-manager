from __future__ import annotations

from sleeper_ffm.model import offer_log, trade_acceptance


def test_append_dedup_and_mark_sent(tmp_path, monkeypatch) -> None:
    path = tmp_path / "offers.jsonl"
    monkeypatch.setattr(offer_log, "_OFFERS_PATH", path)

    offer = {
        "partner_roster_id": 3,
        "give": [{"label": "Player X"}],
        "receive": [{"label": "Player Y"}],
    }
    offer_log.append_offers([offer], logged_at="t0")
    rows = offer_log.list_offers()
    assert len(rows) == 1

    offer_id = rows[0]["offer_id"]
    assert offer_log.mark_sent(offer_id) is True
    sent = offer_log.list_offers(sent=True)
    assert len(sent) == 1 and sent[0]["offer_id"] == offer_id

    # Re-appending the same offer must not duplicate it.
    offer_log.append_offers([offer], logged_at="t1")
    assert len(offer_log.list_offers()) == 1


def test_persist_offers_survives_log_failure(monkeypatch) -> None:
    # The error path used an undefined `log` before; a write failure must be
    # swallowed via the module logger, not raise NameError.
    def _boom(offers, logged_at):
        raise OSError("disk full")

    monkeypatch.setattr("sleeper_ffm.model.offer_log.append_offers", _boom)
    trade_acceptance._persist_offers([])  # must not raise
    assert trade_acceptance.log is not None
