from functools import lru_cache
from pathlib import Path

import numpy as np
import pygame


SHIP_ASSET_DIRECTORY = Path(__file__).with_name("assets") / "ships"


@lru_cache(maxsize=256)
def get_ship_sprite(
        filename: str, faction_color: tuple[int, int, int],
        size: tuple[int, int]) -> pygame.Surface:
    path = SHIP_ASSET_DIRECTORY / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required ship sprite is missing: {path}")

    sprite = pygame.image.load(str(path))
    colors = pygame.surfarray.pixels3d(sprite)
    source = colors.astype(np.float32)
    red_hull = (
        (source[:, :, 0] > source[:, :, 1] * 1.25)
        & (source[:, :, 0] > source[:, :, 2] * 1.25)
        & (source[:, :, 0] > 45)
    )
    brightness = np.maximum.reduce(
        (source[:, :, 0], source[:, :, 1], source[:, :, 2])) / 255.0
    tint = np.asarray(faction_color, dtype=np.float32)
    colors[red_hull] = np.clip(
        tint * (0.3 + brightness[red_hull][:, None] * 0.7),
        0, 255,
    ).astype(np.uint8)
    del colors
    return pygame.transform.smoothscale(sprite, size)
