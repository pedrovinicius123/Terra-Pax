import random
from collections.abc import Mapping

import pygame


SUITABILITY_STYLES = {
    'Human': ((25, 77, 112), (42, 157, 121), (135, 220, 187)),
    'Alien': ((68, 34, 105), (188, 63, 154), (242, 139, 202)),
    'Hybrid': ((33, 75, 79), (111, 150, 100), (187, 211, 153)),
    'Robot': ((57, 69, 92), (142, 155, 176), (236, 190, 103)),
}


def generate_suitability_profile(
        rng: random.Random | None = None) -> dict[str, float]:
    """Create a world profile with one randomly dominant suitability."""
    generator = random if rng is None else rng
    dominant = generator.choice(tuple(SUITABILITY_STYLES))
    peak = generator.uniform(0.75, 1.0)
    return {
        category: peak if category == dominant
        else generator.uniform(0.1, peak - 0.05)
        for category in SUITABILITY_STYLES
    }


def dominant_suitability(suitability: Mapping[str, float]) -> str:
    return max(
        SUITABILITY_STYLES,
        key=lambda category: suitability.get(category, 0.0),
    )


def _stable_seed(value: str) -> int:
    seed = 2166136261
    for character in value:
        seed = ((seed ^ ord(character)) * 16777619) & 0xFFFFFFFF
    return seed


def generate_planet_surface(
        suitability: Mapping[str, float], seed: str,
        size: int = 96) -> pygame.Surface:
    """Render a repeatable, randomly textured 2D planet for a world."""
    if size < 16:
        raise ValueError("Planet surfaces must be at least 16 pixels wide")

    base_color, land_color, highlight_color = SUITABILITY_STYLES[
        dominant_suitability(suitability)
    ]
    generator = random.Random(_stable_seed(seed))
    center = size // 2
    radius = int(size * 0.43)

    sphere = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.circle(sphere, base_color, (center, center), radius)

    terrain = pygame.Surface((size, size), pygame.SRCALPHA)
    for _ in range(generator.randint(4, 8)):
        x = center + generator.randint(-radius // 2, radius // 2)
        y = center + generator.randint(-radius // 2, radius // 2)
        width = generator.randint(max(4, radius // 3), max(5, radius))
        height = generator.randint(max(3, radius // 5),
                                   max(4, radius // 2))
        color = generator.choice((land_color, highlight_color))
        pygame.draw.ellipse(
            terrain, color,
            (x - width // 2, y - height // 2, width, height),
        )

    sphere_mask = pygame.mask.from_surface(sphere)
    clip = sphere_mask.to_surface(
        setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    terrain.blit(clip, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    sphere.blit(terrain)

    shade = pygame.Surface((size, size), pygame.SRCALPHA)
    pygame.draw.ellipse(
        shade, (5, 12, 27, 105),
        (center - radius // 3, center - radius,
         radius * 2, radius * 2),
    )
    shade.blit(clip, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    sphere.blit(shade)

    pygame.draw.arc(
        sphere, highlight_color,
        (center - radius + 2, center - radius + 2,
         radius * 2 - 4, radius * 2 - 4),
        3.8, 5.7, max(1, size // 32),
    )
    pygame.draw.circle(sphere, (196, 227, 255), (center, center), radius, 1)
    return sphere
