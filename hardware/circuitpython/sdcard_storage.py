"""CircuitPython adapter mounting an SD card as a live DeviceStorage.

The only module that imports ``sdcardio`` and ``storage`` -- ``device_builder``
reaches this module only through a deferred import inside its sdcard setup
helper (mirroring the radio path's ``rfm69_radio_transport`` deferral), so a
config with no ``sdcard`` section never requires either library to be
installed.
"""

import sdcardio
import storage

from hardware.shared.device_storage import DeviceStorage

__all__ = ["SdCardStorage"]


class SdCardStorage(DeviceStorage):
    """Live ``DeviceStorage`` backed by a FAT-formatted SD card.

    Mounts the card at construction time via ``sdcardio.SDCard`` +
    ``storage.mount``, then behaves exactly like ``DeviceStorage`` for every
    read/write against the mount point.

    Args:
        spi: The shared SPI bus (see ``device_builder._setup_spi``).
        cs: Chip-select pin as a raw ``microcontroller.Pin`` -- unlike the
            radio path, ``sdcardio.SDCard`` takes the raw pin itself rather
            than a ``digitalio.DigitalInOut`` wrapper.
        mount: Absolute mount point (e.g. ``"/sd"``).

    Raises:
        OSError: From ``sdcardio.SDCard`` or ``storage.mount`` -- no card
            fitted, or the card carries no FAT filesystem. Propagates
            unwrapped; the builder that constructs this is responsible for
            adding legible context.
    """

    def __init__(self, spi: object, cs: object, mount: str) -> None:
        card = sdcardio.SDCard(spi, cs)
        # readonly=False is VfsFat's own default, but is passed explicitly
        # here to document that device-mutable state depends on the mount
        # being writable.
        storage.mount(storage.VfsFat(card), mount, readonly=False)
        super().__init__(mount)
