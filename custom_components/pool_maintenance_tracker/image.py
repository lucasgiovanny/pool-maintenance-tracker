"""QR code image entity for the public page URL."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import segno
from homeassistant.components.image import ImageEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util import dt as dt_util

from .const import CONF_TOKEN, URL_PAGE
from .entity import PoolBaseEntity

if TYPE_CHECKING:
    from . import PoolConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PoolQrCodeImage(hass, entry)])


class PoolQrCodeImage(PoolBaseEntity, ImageEntity):
    """QR code of the public page URL, ready to print or scan."""

    _attr_content_type = "image/png"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:qrcode"

    def __init__(self, hass: HomeAssistant, entry: PoolConfigEntry) -> None:
        PoolBaseEntity.__init__(self, entry, "access_qr")
        ImageEntity.__init__(self, hass)
        self._rendered_url: str | None = None
        self._png: bytes | None = None
        self._attr_image_last_updated = dt_util.utcnow()

    def _page_url(self) -> str | None:
        path = URL_PAGE.format(token=self.entry.data[CONF_TOKEN])
        try:
            base = get_url(self.hass, prefer_external=True)
        except NoURLAvailableError:
            return None
        return f"{base}{path}"

    async def async_image(self) -> bytes | None:
        url = self._page_url()
        if url is None:
            return None
        if url != self._rendered_url:
            buffer = io.BytesIO()
            segno.make(url, error="m").save(buffer, kind="png", scale=8, border=2)
            self._png = buffer.getvalue()
            self._rendered_url = url
            self._attr_image_last_updated = dt_util.utcnow()
        return self._png
