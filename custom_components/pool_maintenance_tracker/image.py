"""QR code image entity for the public page URL."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Any

import segno
from homeassistant.components.image import ImageEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .entity import PoolBaseEntity, kiosk_url, page_url

# Everything is pushed from the tracker; nothing here polls.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from . import PoolConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PoolQrCodeImage(hass, entry)])


class PoolQrCodeImage(PoolBaseEntity, ImageEntity):
    """QR code of the public page URL, ready to print or scan.

    The full URL is exposed as the ``url`` attribute for copying into an
    NFC-writing app (deliberately not a sensor state, which would overflow
    the UI).
    """

    _attr_content_type = "image/png"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: PoolConfigEntry) -> None:
        PoolBaseEntity.__init__(self, entry, "access_qr")
        ImageEntity.__init__(self, hass)
        self._rendered_url: str | None = None
        self._png: bytes | None = None
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "url": page_url(self.hass, self.entry),
            "kiosk_url": kiosk_url(self.hass, self.entry),
        }

    async def async_image(self) -> bytes | None:
        url = page_url(self.hass, self.entry)
        if url is None:
            return None
        if url != self._rendered_url:
            # segno is synchronous; tiny, but the event loop is not the place
            self._png = await self.hass.async_add_executor_job(self._render, url)
            self._rendered_url = url
            self._attr_image_last_updated = dt_util.utcnow()
        return self._png

    @staticmethod
    def _render(url: str) -> bytes:
        buffer = io.BytesIO()
        segno.make(url, error="m").save(buffer, kind="png", scale=8, border=2)
        return buffer.getvalue()
