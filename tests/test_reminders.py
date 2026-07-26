"""Reminder engine tests."""

from datetime import timedelta

from freezegun import freeze_time
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.pool_maintenance_tracker.const import DOMAIN

from .conftest import setup_entry


async def fire_daily_check(hass, when):
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()


def next_check(now):
    """Next 10:00 local after now."""
    local = dt_util.as_local(now)
    check = local.replace(hour=10, minute=0, second=0, microsecond=0)
    if check <= local:
        check += timedelta(days=1)
    return check


async def test_fresh_install_does_not_notify(hass, salt_entry):
    notifications = []

    async def record_notify(call):
        notifications.append(call.data)

    hass.services.async_register("notify", "test_target", record_notify)
    await setup_entry(hass, salt_entry)

    await fire_daily_check(hass, next_check(dt_util.utcnow()))
    assert notifications == []


async def test_overdue_task_notifies_with_damper(hass, salt_entry):
    notifications = []

    async def record_notify(call):
        notifications.append(call.data)

    hass.services.async_register("notify", "test_target", record_notify)
    await setup_entry(hass, salt_entry)

    tracker = salt_entry.runtime_data.tracker
    now = dt_util.utcnow()
    tracker.timestamps["filter_wash"] = (now - timedelta(days=40)).isoformat()
    # keep the other reminders quiet
    tracker.timestamps["cell_clean"] = now.isoformat()
    tracker.timestamps["probe_calibration"] = now.isoformat()
    tracker.installed_at = (now - timedelta(days=400)).isoformat()

    check1 = next_check(now)
    with freeze_time(check1):
        await fire_daily_check(hass, check1)
    assert len(notifications) == 1
    assert "filtro" in notifications[0]["message"]
    assert notifications[0]["title"] == "Piscina: Piscina"

    # next day: damper (3 days) suppresses the repeat
    check2 = check1 + timedelta(days=1)
    with freeze_time(check2):
        await fire_daily_check(hass, check2)
    assert len(notifications) == 1

    # after 3 days it fires again
    check3 = check1 + timedelta(days=3)
    with freeze_time(check3):
        await fire_daily_check(hass, check3)
    assert len(notifications) == 2


async def test_due_binary_sensor(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    registry = er.async_get(hass)
    due_entity = registry.async_get_entity_id(
        "binary_sensor", DOMAIN, f"{salt_entry.entry_id}_filter_wash_due"
    )
    # fresh install: baseline is install time -> not due
    assert hass.states.get(due_entity).state == "off"

    tracker = salt_entry.runtime_data.tracker
    tracker.timestamps["filter_wash"] = (dt_util.utcnow() - timedelta(days=31)).isoformat()
    tracker.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(due_entity).state == "on"

    tracker.timestamps["filter_wash"] = dt_util.utcnow().isoformat()
    tracker.async_update_listeners()
    await hass.async_block_till_done()
    assert hass.states.get(due_entity).state == "off"


async def test_no_notify_service_is_silent(hass, chlorine_entry):
    await setup_entry(hass, chlorine_entry)
    tracker = chlorine_entry.runtime_data.tracker
    now = dt_util.utcnow()
    tracker.timestamps["filter_wash"] = (now - timedelta(days=60)).isoformat()

    # must not raise even though no notify service is configured
    check = next_check(now)
    with freeze_time(check):
        await fire_daily_check(hass, check)
