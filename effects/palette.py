class Palette:
    """Maps a normalized float value to a packed RGB color.

    Subclasses implement ``lookup`` to define the color mapping strategy.
    """

    @staticmethod
    def pack_rgb(r: int, g: int, b: int) -> int:
        """Pack ``r``, ``g``, ``b`` bytes into a single 24-bit integer."""
        return (r << 16) | (g << 8) | b

    def lookup(self, value: float) -> int:
        """Return a packed RGB color for a normalized ``value`` in ``[0.0, 1.0]``."""
        raise NotImplementedError("Palette implementations must implement lookup()")


class PaletteLUT256(Palette):
    """A 256-entry lookup table palette built from a compact palette definition.

    At construction time, ``color_stops`` is expanded into a full 256-color
    LUT by linearly interpolating between the defined color stops. Lookups are
    then a single list index — no interpolation at runtime.

    Palette format:
    - A flat ``bytes`` object where each color stop is 4 bytes: ``[index, r, g, b]``.
    - ``index`` is the LUT position (``0``–``255``) for that stop.
    - Stops need not cover ``0`` or ``255``; endpoints are added automatically.
    - Length must be a multiple of 4.
    """

    __slots__ = ("colors",)

    def __init__(self, color_stops: bytes):
        self.colors: list[int] = PaletteLUT256._build_lookup(color_stops)

    @staticmethod
    def _build_lookup(color_stops: bytes) -> list[int]:
        if len(color_stops) == 0:
            return [0] * 256
        if len(color_stops) % 4 != 0:
            raise ValueError("Color stops length must be a multiple of 4")

        # Ensure the first and last stops anchor the LUT at 0 and 255
        anchored_stops = color_stops[:]
        if anchored_stops[0] != 0:
            anchored_stops = bytes([0, 0, 0, 0]) + anchored_stops
        if anchored_stops[-4] != 255:
            anchored_stops = anchored_stops + bytes([255, 0, 0, 0])

        lookup_palette: list[int] = [0] * 256

        # Iterate through each pair of adjacent stops and fill in the LUT between them
        for anchor_index in range(0, len(anchored_stops) - 4, 4):
            # get the next two stops, which anchor a segment of the LUT
            start_index = anchored_stops[anchor_index]
            start_r = anchored_stops[anchor_index + 1]
            start_g = anchored_stops[anchor_index + 2]
            start_b = anchored_stops[anchor_index + 3]

            end_index = anchored_stops[anchor_index + 4]
            end_r = anchored_stops[anchor_index + 5]
            end_g = anchored_stops[anchor_index + 6]
            end_b = anchored_stops[anchor_index + 7]

            # set the start color
            lookup_palette[start_index] = Palette.pack_rgb(start_r, start_g, start_b)

            # set all colors between start and end to a weighted blend of the two
            for i in range(start_index + 1, end_index):
                weight = (i - start_index) / (end_index - start_index)
                r = int(start_r + weight * (end_r - start_r))
                g = int(start_g + weight * (end_g - start_g))
                b = int(start_b + weight * (end_b - start_b))
                lookup_palette[i] = Palette.pack_rgb(r, g, b)

        # make sure the final stop is set, the loop will only set the start color of each segment
        lookup_palette[255] = Palette.pack_rgb(
            anchored_stops[-3], anchored_stops[-2], anchored_stops[-1]
        )

        return lookup_palette

    def lookup(self, value: float) -> int:
        if value <= 0.0:
            return self.colors[0]
        if value >= 1.0:
            return self.colors[255]

        index = int(value * 255.0)
        return self.colors[index]
