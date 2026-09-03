"""Port makra `interpolate()` z blueprintu HA.

Idea: `color_matrix` to mapa temperatura -> kolor HEX (punkty na skali).
Dla dowolnej temperatury `x` szukamy najbliższego progu poniżej i powyżej
i liniowo interpolujemy kolor RGB między nimi. Poza zakresem używamy koloru
brzegowego.

Uwaga (zachowane celowo dla zgodności z oryginałem): oryginalny szablon Jinja
szuka klucza *ściśle mniejszego* i *ściśle większego* od x, więc gdy x trafia
dokładnie w istniejący próg, ten próg nie jest traktowany jako "dokładne
trafienie" tylko normalnie bierze udział w interpolacji z sąsiadem - efekt
końcowy jest identyczny z tym, co widać na wyświetlaczach AWTRIX używających
oryginalnego blueprintu.
"""
from __future__ import annotations


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def interpolate_color(color_matrix: dict[float, str], x: float) -> str | None:
    if not color_matrix:
        return None

    sorted_keys = sorted(color_matrix.keys())
    above = next((k for k in sorted_keys if k > x), None)
    below = next((k for k in reversed(sorted_keys) if k < x), None)

    if below is not None and above is not None:
        lower_rgb = _hex_to_rgb(color_matrix[below])
        upper_rgb = _hex_to_rgb(color_matrix[above])
        factor = (x - below) / (above - below)
        r = int((1 - factor) * lower_rgb[0] + factor * upper_rgb[0])
        g = int((1 - factor) * lower_rgb[1] + factor * upper_rgb[1])
        b = int((1 - factor) * lower_rgb[2] + factor * upper_rgb[2])
        return f"#{r:02X}{g:02X}{b:02X}"

    if below is not None:
        return color_matrix[below]

    if above is not None:
        return color_matrix[above]

    # x dokładnie równe jedynemu progowi w tabeli
    if x in color_matrix:
        return color_matrix[x]

    return None
