"""Port makra `get_text_len()` z blueprintu - przybliżona szerokość (w px)
napisu z temperaturą na matrycy 5x5 / 3x5 czcionce AWTRIX, żeby wyśrodkować
tekst na dostępnej szerokości ekranu."""
from __future__ import annotations


def text_pixel_length(text: str) -> int:
    length = 0
    chars = list(text)
    for i, ch in enumerate(chars):
        if ch.isdigit():
            length += 3
        elif ch == "°":
            length += 2
        elif ch == ".":
            length += 1
        elif ch in ("-", "C", "F"):
            length += 3
        else:
            length += 1
        if i != len(chars) - 1:
            length += 1  # odstęp między znakami
    return length


def center_text_x(text: str, available_width: int, base_x: int = 8) -> float:
    return base_x + (available_width - text_pixel_length(text)) / 2
