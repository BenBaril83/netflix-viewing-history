from datetime import date
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.netflix_viewing_history.const import CONF_TOKEN, DOMAIN
from custom_components.netflix_viewing_history.coordinator import count_since

DATA = {
    "status": {},
    "profiles": {
        "Ben": [
            {"title": "Show: Season 1: Ep", "date": "2026-10-09", "date_raw": "10/9/26", "show": "Show", "title_id": "1"},
            {"title": "Old", "date": "2026-01-01", "date_raw": "1/1/26", "show": None, "title_id": "2"},
        ],
        "Kids": [{"title": "Undated", "date": None, "date_raw": "9/10/26", "show": None, "title_id": "3"}],
    },
}
CONN = {CONF_HOST: "addon", CONF_PORT: 8100, CONF_TOKEN: "t"}
FETCH = "custom_components.netflix_viewing_history.coordinator.fetch_history"
FLOW_FETCH = "custom_components.netflix_viewing_history.config_flow.fetch_history"


def test_count_since():
    es = DATA["profiles"]["Ben"] + DATA["profiles"]["Kids"]
    assert count_since(es, 7, date(2026, 10, 11)) == 1


async def test_sensors(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=CONN)
    entry.add_to_hass(hass)
    with patch(FETCH, return_value=DATA):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    s = hass.states.get("sensor.netflix_ben_last_watched")
    assert s.state == "Show: Season 1: Ep" and s.attributes["show"] == "Show"
    assert hass.states.get("sensor.netflix_ben_titles_watched").state == "2"
    assert hass.states.get("sensor.netflix_kids_watched_in_last_7_days").state == "unknown"
    assert hass.states.get("button.netflix_viewing_history_refresh_viewing_history")


async def test_flow_ok_and_errors(hass):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    with patch(FLOW_FETCH, side_effect=ConfigEntryAuthFailed):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], CONN)
    assert r["errors"] == {"base": "invalid_auth"}
    with patch(FLOW_FETCH, return_value=DATA), patch("custom_components.netflix_viewing_history.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_configure(r["flow_id"], CONN)
    assert r["type"] == FlowResultType.CREATE_ENTRY


async def test_reauth_with_new_token(hass):
    from homeassistant.config_entries import ConfigEntryState

    entry = MockConfigEntry(domain=DOMAIN, data=CONN)
    entry.add_to_hass(hass)
    with patch(FETCH, side_effect=ConfigEntryAuthFailed):  # the add-on rotated its token
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]  # HA asked the user to re-authenticate

    r = await hass.config_entries.flow.async_configure(flows[0]["flow_id"])
    assert r["step_id"] == "reauth_confirm"
    with patch(FLOW_FETCH, side_effect=ConfigEntryAuthFailed):
        r = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {CONF_TOKEN: "still-wrong"})
    assert r["errors"] == {"base": "invalid_auth"}

    with patch(FLOW_FETCH, return_value=DATA), patch(FETCH, return_value=DATA):
        r = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {CONF_TOKEN: "new-token"})
        await hass.async_block_till_done()
    assert r["type"] == FlowResultType.ABORT and r["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "new-token" and entry.data[CONF_HOST] == "addon"
    assert entry.state is ConfigEntryState.LOADED
