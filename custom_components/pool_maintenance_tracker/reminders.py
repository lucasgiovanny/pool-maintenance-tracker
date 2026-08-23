"""Daily maintenance reminders and immediate alerts."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from .const import (
    ACID_LEVEL_NONE,
    CONF_LANGUAGE,
    CONF_NOTIFY_SERVICE,
    CONF_REMINDER_TIME,
    DEFAULT_LANGUAGE,
    DEFAULT_REMINDER_TIME,
    RENOTIFY_DAYS,
    TS_CELL_CLEAN,
    TS_CHEMISTRY_TEST,
    TS_FILTER_WASH,
    TS_PROBE_CALIBRATION,
)
from .modules import enabled_reminders

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .tracker import PoolTracker

_LOGGER = logging.getLogger(__name__)

NOTIFY_DOMAIN = "notify"
SERVICE_SEND_MESSAGE = "send_message"

# Notification texts keyed by the page language of the entry — the reminder
# audience is the same people who use the page.
NOTIFY_STRINGS = {
    "en": {
        "title": "Pool: {pool}",
        TS_FILTER_WASH: "Filter wash is overdue ({when}).",
        TS_CELL_CLEAN: "Chlorinator cell cleaning is overdue ({when}).",
        TS_PROBE_CALIBRATION: "pH probe calibration is overdue ({when}).",
        TS_CHEMISTRY_TEST: "Stabilizer and hardness test is overdue ({when}).",
        "last_done": "last done {days} days ago",
        "never_done": "never recorded",
        "acid_alert": "Acid tank is low ({level}).",
        "acid_missing": "The acid tank is gone — pH is no longer being dosed.",
        "acid_empty": "Empty",
        "acid_quarter": "1/4",
    },
    "pt": {
        "title": "Piscina: {pool}",
        TS_FILTER_WASH: "A lavagem do filtro está atrasada ({when}).",
        TS_CELL_CLEAN: "A limpeza da célula do clorador está atrasada ({when}).",
        TS_PROBE_CALIBRATION: "A calibração da sonda de pH está atrasada ({when}).",
        TS_CHEMISTRY_TEST: "O teste de estabilizante e dureza está atrasado ({when}).",
        "last_done": "última há {days} dias",
        "never_done": "nunca registada",
        "acid_alert": "O depósito de ácido está baixo ({level}).",
        "acid_missing": "O depósito de ácido foi retirado — o pH deixou de ser doseado.",
        "acid_empty": "Vazio",
        "acid_quarter": "1/4",
    },
    "es": {
        "title": "Piscina: {pool}",
        TS_FILTER_WASH: "El lavado del filtro está atrasado ({when}).",
        TS_CELL_CLEAN: "La limpieza de la célula del clorador está atrasada ({when}).",
        TS_PROBE_CALIBRATION: "La calibración de la sonda de pH está atrasada ({when}).",
        TS_CHEMISTRY_TEST: "La prueba de estabilizante y dureza está atrasada ({when}).",
        "last_done": "última hace {days} días",
        "never_done": "nunca registrada",
        "acid_alert": "El depósito de ácido está bajo ({level}).",
        "acid_missing": "El depósito de ácido fue retirado — el pH ya no se dosifica.",
        "acid_empty": "Vacío",
        "acid_quarter": "1/4",
    },
    "fr": {
        "title": "Piscine : {pool}",
        TS_FILTER_WASH: "Le lavage du filtre est en retard ({when}).",
        TS_CELL_CLEAN: "Le nettoyage de la cellule de l'électrolyseur est en retard ({when}).",
        TS_PROBE_CALIBRATION: "L'étalonnage de la sonde pH est en retard ({when}).",
        TS_CHEMISTRY_TEST: "Le test de stabilisant et de dureté est en retard ({when}).",
        "last_done": "dernier il y a {days} jours",
        "never_done": "jamais enregistré",
        "acid_alert": "Le bidon d'acide est bas ({level}).",
        "acid_missing": "Le bidon d'acide a été retiré — le pH n'est plus dosé.",
        "acid_empty": "Vide",
        "acid_quarter": "1/4",
    },
    "de": {
        "title": "Pool: {pool}",
        TS_FILTER_WASH: "Die Filterwäsche ist überfällig ({when}).",
        TS_CELL_CLEAN: "Die Reinigung der Elektrolysezelle ist überfällig ({when}).",
        TS_PROBE_CALIBRATION: "Die Kalibrierung der pH-Sonde ist überfällig ({when}).",
        TS_CHEMISTRY_TEST: "Der Stabilisator- und Härtetest ist überfällig ({when}).",
        "last_done": "zuletzt vor {days} Tagen",
        "never_done": "nie erfasst",
        "acid_alert": "Der Säurebehälter ist niedrig ({level}).",
        "acid_missing": "Der Säurebehälter wurde entfernt — der pH-Wert wird nicht mehr dosiert.",
        "acid_empty": "Leer",
        "acid_quarter": "1/4",
    },
    "it": {
        "title": "Piscina: {pool}",
        TS_FILTER_WASH: "Il lavaggio del filtro è in ritardo ({when}).",
        TS_CELL_CLEAN: "La pulizia della cella del clorinatore è in ritardo ({when}).",
        TS_PROBE_CALIBRATION: "La calibrazione della sonda pH è in ritardo ({when}).",
        TS_CHEMISTRY_TEST: "Il test di stabilizzante e durezza è in ritardo ({when}).",
        "last_done": "ultimo {days} giorni fa",
        "never_done": "mai registrato",
        "acid_alert": "Il serbatoio dell'acido è basso ({level}).",
        "acid_missing": "Il serbatoio dell'acido è stato rimosso — il pH non viene più dosato.",
        "acid_empty": "Vuoto",
        "acid_quarter": "1/4",
    },
}


def _parse_reminder_time(raw: str) -> tuple[int, int]:
    try:
        hour_str, minute_str = raw.split(":")[:2]
        hour, minute = int(hour_str), int(minute_str)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    hour_str, minute_str = DEFAULT_REMINDER_TIME.split(":")
    return int(hour_str), int(minute_str)


class ReminderEngine:
    """Per-entry reminder scheduling and notification dispatch."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, tracker: PoolTracker) -> None:
        self.hass = hass
        self.entry = entry
        self.tracker = tracker
        self._unsub: CALLBACK_TYPE | None = None

    @callback
    def async_start(self) -> None:
        hour, minute = _parse_reminder_time(
            self.entry.options.get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME)
        )
        self._unsub = async_track_time_change(
            self.hass, self._async_daily_check, hour=hour, minute=minute, second=0
        )

    @callback
    def async_stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def _strings(self) -> dict[str, str]:
        language = self.entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        return NOTIFY_STRINGS.get(language, NOTIFY_STRINGS[DEFAULT_LANGUAGE])

    def overdue_since(self, timestamp_key: str) -> datetime:
        """Baseline for the overdue calculation of a timestamp key.

        Falls back to the install time when the task was never recorded, so
        a fresh install does not fire every reminder on day one.
        """
        return self.tracker.get_timestamp(timestamp_key) or self.tracker.installed_at_dt

    def is_overdue(self, timestamp_key: str, days: int, now: datetime) -> bool:
        """Whether a task is past due.

        The filter is special: with a pressure gauge linked and a clean
        baseline known, the gauge decides — a filter that is still clean
        after the interval should not be washed, and one that clogged early
        should not wait.
        """
        if timestamp_key == TS_FILTER_WASH:
            from . import filter_pressure

            by_pressure = filter_pressure.is_due(self.entry, self.tracker)
            if by_pressure is not None:
                return by_pressure
        return now - self.overdue_since(timestamp_key) >= timedelta(days=days)

    async def _async_daily_check(self, now: datetime) -> None:
        now = dt_util.as_utc(now)
        strings = self._strings()
        notified_any = False
        for spec in enabled_reminders(self.entry.options):
            days = int(self.entry.options.get(spec.conf_key, spec.default_days))
            if not self.is_overdue(spec.timestamp_key, days, now):
                continue
            last_notified_raw = self.tracker.reminders_last_notified.get(spec.timestamp_key)
            last_notified = dt_util.parse_datetime(last_notified_raw) if last_notified_raw else None
            if last_notified and now - last_notified < timedelta(days=RENOTIFY_DAYS):
                continue
            last_done = self.tracker.get_timestamp(spec.timestamp_key)
            when = (
                strings["last_done"].format(days=(now - last_done).days)
                if last_done
                else strings["never_done"]
            )
            await self.async_notify(strings[spec.timestamp_key].format(when=when))
            self.tracker.reminders_last_notified[spec.timestamp_key] = now.isoformat()
            notified_any = True
        if notified_any:
            self.tracker.async_save()
        # Refresh the *_due binary sensors even when nothing was notified.
        self.tracker.async_update_listeners()

    async def async_send_acid_alert(self, level: str) -> None:
        """Said once, when the level changes — never repeated daily."""
        strings = self._strings()
        if level == ACID_LEVEL_NONE:
            await self.async_notify(strings["acid_missing"])
            return
        await self.async_notify(
            strings["acid_alert"].format(level=strings.get(f"acid_{level}", level))
        )

    async def async_notify(self, message: str) -> None:
        """Send through whichever kind of notify target was configured.

        Notify exists twice over: the legacy services and the newer notify
        entities, called with send_message. Both are picked from the same
        dropdown, so tell them apart by whether the target has a state.
        """
        target = self.entry.options.get(CONF_NOTIFY_SERVICE, "")
        if not target:
            return
        title = self._strings()["title"].format(pool=self.tracker.pool_name)
        try:
            state = self.hass.states.get(target)
            if state is not None and target.startswith(f"{NOTIFY_DOMAIN}."):
                data: dict[str, str] = {"entity_id": target, "message": message}
                # NotifyEntityFeature.TITLE — an entity without it rejects a title
                if state.attributes.get("supported_features", 0) & 1:
                    data["title"] = title
                await self.hass.services.async_call(NOTIFY_DOMAIN, SERVICE_SEND_MESSAGE, data)
                return
            domain, _, service_name = target.partition(".")
            await self.hass.services.async_call(
                domain, service_name, {"title": title, "message": message}
            )
        except Exception:
            _LOGGER.exception("Failed to send notification via %s", target)
