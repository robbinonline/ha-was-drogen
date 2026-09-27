"""De markdown-kaarten uit dashboard/ moeten renderen tegen de echte entiteiten."""

from __future__ import annotations

from pathlib import Path

import yaml
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template

from .test_integration import _create, _set_station, forecast_calls  # noqa: F401

VIEW = Path(__file__).parents[1] / "dashboard" / "was-drogen-view.yaml"


async def test_markdown_cards_render(hass: HomeAssistant, forecast_calls):  # noqa: F811
    hass.config.language = "nl"
    hass.states.async_set("sun.sun", "above_horizon", {"next_setting": "2026-09-28T17:25:00+00:00"})
    _set_station(hass)
    await _create(hass)

    view = yaml.safe_load(VIEW.read_text())
    cards = [c for s in view["sections"] for c in s["cards"] if c["type"] == "markdown"]
    assert len(cards) == 2
    for card in cards:
        out = Template(card["content"], hass).async_render(parse_result=False)
        print(out, "\n-----")
        assert "None" not in out
        assert "unknown" not in out.lower()

    ids = {c.get("entity") for s in view["sections"] for c in s["cards"] if c.get("entity")}
    for s in view["sections"]:
        for c in s["cards"]:
            ids |= {x["entity"] for x in c.get("entities", [])}
    for entity_id in ids:
        assert hass.states.get(entity_id) is not None, entity_id
