import math
import random
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

import numpy as np
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


def city_light_intensity(
        development: float, population: float,
        max_development: float, max_population: float) -> float:
    development_ratio = min(
        1.0, max(0.0, development / max(1.0, max_development)))
    population_ratio = min(
        1.0, max(0.0, population / max(1.0, max_population)))
    return (development_ratio * population_ratio) ** 0.5


def _stable_seed(value: str) -> int:
    seed = 2166136261
    for character in value:
        seed = ((seed ^ ord(character)) * 16777619) & 0xFFFFFFFF
    return seed


ASSET_DIRECTORY = Path(__file__).with_name("assets")


@lru_cache(maxsize=4)
def _load_asset_surface(filename: str) -> pygame.Surface:
    path = ASSET_DIRECTORY / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required planet texture asset is missing: {path}")
    return pygame.image.load(str(path))


@lru_cache(maxsize=32)
def _asset_pixels(
        filename: str, size: tuple[int, int]) -> np.ndarray:
    image = pygame.transform.smoothscale(
        _load_asset_surface(filename), size)
    return np.transpose(pygame.surfarray.array3d(image), (1, 0, 2))


@lru_cache(maxsize=8)
def generate_starfield_surface(size: tuple[int, int]) -> pygame.Surface:
    """Scale and tint the NASA all-sky mosaic for the planet viewer backdrop."""
    starfield = pygame.transform.smoothscale(
        _load_asset_surface("wise_starfield.jpg"), size)
    starfield.fill((95, 120, 165), special_flags=pygame.BLEND_RGB_MULT)
    starfield.set_alpha(165)
    return starfield


def _seeded_asset_pixels(
        filename: str, size: tuple[int, int], seed: str,
        layer: str) -> np.ndarray:
    pixels = _asset_pixels(filename, size)
    generator = random.Random(_stable_seed(f"{seed}:{layer}"))
    width, height = size
    offset_x = generator.randrange(width)
    offset_y = generator.randrange(max(1, round(height * 0.12))) - round(
        height * 0.06)
    transformed = np.roll(pixels, (offset_y, offset_x), axis=(0, 1))
    if generator.random() < 0.5:
        transformed = transformed[:, ::-1]
    return transformed


def generate_cloud_texture(seed: str, size: tuple[int, int]):
    """Return a seeded, transparent cloud layer from the NASA cloud atlas."""
    width, height = size
    source = _seeded_asset_pixels(
        "earth_clouds.jpg", size, seed, "clouds").astype(np.float32)
    luminance = (
        0.2126 * source[..., 0]
        + 0.7152 * source[..., 1]
        + 0.0722 * source[..., 2]
    )
    alpha = np.clip((luminance - 70.0) * 1.25, 0, 165).astype(np.uint8)
    cloud = pygame.Surface((width, height), pygame.SRCALPHA)
    rgb_pixels = pygame.surfarray.pixels3d(cloud)
    rgb_pixels[:, :, :] = (205, 222, 235)
    del rgb_pixels
    alpha_pixels = pygame.surfarray.pixels_alpha(cloud)
    alpha_pixels[:, :] = alpha.T
    del alpha_pixels
    return cloud


def generate_city_light_texture(
        suitability: Mapping[str, float], seed: str,
        size: tuple[int, int]) -> pygame.Surface:
    """Return a seeded, transparent night-city layer from NASA's light atlas."""
    width, height = size
    source = _seeded_asset_pixels(
        "earth_surface_lights.jpg", size, seed, "cities").astype(np.float32)
    luminance = (
        0.2126 * source[..., 0]
        + 0.7152 * source[..., 1]
        + 0.0722 * source[..., 2]
    )
    light_strength = np.clip((luminance - 31.0) * 3.2, 0, 225)
    _, colors, highlights = SUITABILITY_STYLES[
        dominant_suitability(suitability)]
    color = np.asarray(highlights, dtype=np.float32) * 0.65 + (
        np.asarray(colors, dtype=np.float32) * 0.35)
    city = pygame.Surface((width, height), pygame.SRCALPHA)
    rgb_pixels = pygame.surfarray.pixels3d(city)
    rgb_pixels[:, :, :] = np.broadcast_to(
        np.clip(color, 0, 255).astype(np.uint8), (width, height, 3))
    del rgb_pixels
    alpha_pixels = pygame.surfarray.pixels_alpha(city)
    alpha_pixels[:, :] = light_strength.T.astype(np.uint8)
    del alpha_pixels
    return city


@lru_cache(maxsize=256)
def generate_city_networks(seed: str, count: int = 36):
    """Create deterministic city clusters with roads and dense block lights."""
    generator = random.Random(_stable_seed(f"{seed}:cities"))
    networks = []
    grid = (-0.72, -0.36, 0.0, 0.36, 0.72)
    phase = generator.uniform(0.0, math.tau)
    golden_angle = math.pi * (3.0 - math.sqrt(5.0))

    for index in range(count):
        y = 1.0 - 2.0 * (index + 0.5) / count
        latitude = math.asin(y) + generator.uniform(-0.015, 0.015)
        longitude = (
            index * golden_angle + phase
            + generator.uniform(-0.015, 0.015)
        ) % math.tau
        center = (
            math.cos(latitude) * math.sin(longitude),
            math.sin(latitude),
            math.cos(latitude) * math.cos(longitude),
        )
        east = (math.cos(longitude), 0.0, -math.sin(longitude))
        north = (
            -math.sin(latitude) * math.sin(longitude),
            math.cos(latitude),
            -math.sin(latitude) * math.cos(longitude),
        )
        city_radius = generator.uniform(0.045, 0.11)

        def surface_point(east_offset, north_offset):
            point = tuple(
                center[axis]
                + east[axis] * east_offset
                + north[axis] * north_offset
                for axis in range(3)
            )
            length = math.sqrt(sum(component ** 2 for component in point))
            return tuple(component / length for component in point)

        grid_points = []
        blocks = []
        roads = []
        for north_index, north_offset in enumerate(grid):
            row = []
            for east_index, east_offset in enumerate(grid):
                if east_offset ** 2 + north_offset ** 2 > 0.92:
                    row.append(None)
                    continue
                jitter = city_radius * 0.035
                point = surface_point(
                    city_radius * (east_offset + generator.uniform(
                        -jitter, jitter)),
                    city_radius * (north_offset + generator.uniform(
                        -jitter, jitter)),
                )
                row.append(point)
                blocks.append(point)
                if east_index > 0 and row[-2] is not None:
                    roads.append((row[-2], point))
                if north_index > 0 and grid_points[north_index - 1][
                        east_index] is not None:
                    roads.append((
                        grid_points[north_index - 1][east_index], point))
            grid_points.append(row)

        for spoke in range(8):
            angle = math.tau * spoke / 8
            edge = surface_point(
                city_radius * 0.98 * math.cos(angle),
                city_radius * 0.98 * math.sin(angle),
            )
            roads.append((center, edge))
            blocks.append(edge)

        networks.append((center, blocks, roads, city_radius))
    generator.shuffle(networks)
    return networks


def _periodic_value_noise(
        width: int, height: int, grid_width: int, grid_height: int,
        generator: random.Random) -> np.ndarray:
    lattice = np.asarray([
        [generator.random() for _ in range(grid_width)]
        for _ in range(grid_height + 1)
    ], dtype=np.float32)
    x = (np.arange(width, dtype=np.float32) + 0.5) * grid_width / width
    y = (np.arange(height, dtype=np.float32) + 0.5) * grid_height / height
    x_floor = np.floor(x).astype(np.int32)
    y_floor = np.floor(y).astype(np.int32)
    x_fraction = x - x_floor
    y_fraction = y - y_floor
    x_blend = x_fraction * x_fraction * (3.0 - 2.0 * x_fraction)
    y_blend = y_fraction * y_fraction * (3.0 - 2.0 * y_fraction)

    x0 = x_floor % grid_width
    x1 = (x0 + 1) % grid_width
    y0 = np.minimum(y_floor, grid_height - 1)
    y1 = y0 + 1
    north = (
        lattice[y0[:, None], x0[None, :]]
        * (1.0 - x_blend[None, :])
        + lattice[y0[:, None], x1[None, :]] * x_blend[None, :]
    )
    south = (
        lattice[y1[:, None], x0[None, :]]
        * (1.0 - x_blend[None, :])
        + lattice[y1[:, None], x1[None, :]] * x_blend[None, :]
    )
    return (
        north * (1.0 - y_blend[:, None])
        + south * y_blend[:, None]
    )


def _surface_array(texture: pygame.Surface) -> np.ndarray:
    return np.transpose(pygame.surfarray.array3d(texture), (1, 0, 2))


def generate_planet_surface(
        suitability: Mapping[str, float], seed: str,
        size: int = 96, city_lights: float = 0.0,
        detail_level: int = 3) -> pygame.Surface:
    """Render a repeatable, randomly textured 2D planet for a world."""
    if size < 16:
        raise ValueError("Planet surfaces must be at least 16 pixels wide")
    if not isinstance(detail_level, int) or not 1 <= detail_level <= 8:
        raise ValueError("Texture detail must be an integer from 1 to 8")

    texture = generate_planet_texture(
        suitability, seed, (size * 2, size), detail_level=detail_level)
    texture_pixels = _surface_array(texture)
    center = size // 2
    radius = int(size * 0.43)

    sphere = pygame.Surface((size, size), pygame.SRCALPHA)
    x_grid, y_grid = np.meshgrid(np.arange(size), np.arange(size))
    nx = (x_grid - center) / radius
    ny = (center - y_grid) / radius
    nz_squared = 1.0 - nx ** 2 - ny ** 2
    mask = nz_squared >= 0.0
    nz = np.sqrt(np.maximum(0.0, nz_squared))
    longitude = np.arctan2(nx, nz)
    latitude = np.arcsin(np.clip(ny, -1.0, 1.0))
    tex_x = np.mod(
        ((longitude / math.tau + 0.5) * texture.get_width()).astype(int),
        texture.get_width(),
    )
    tex_y = np.clip(
        ((0.5 - latitude / math.pi) * texture.get_height()).astype(int),
        0, texture.get_height() - 1,
    )
    sun = np.asarray((-0.45, 0.24, 0.86), dtype=np.float32)
    sun /= np.linalg.norm(sun)
    illumination = (
        nx * sun[0] + ny * sun[1] + nz * sun[2])
    brightness = 0.20 + 0.80 * np.maximum(0.0, illumination)
    pixels = texture_pixels[tex_y, tex_x]
    shaded = pixels * brightness[..., None]
    cloud_texture = generate_cloud_texture(
        seed, (texture.get_width(), texture.get_height()))
    cloud_alpha = pygame.surfarray.array_alpha(cloud_texture).T[
        tex_y, tex_x].astype(np.float32) / 255.0
    daylight = np.maximum(0.0, illumination)
    cloud_opacity = cloud_alpha * (0.22 + 0.58 * daylight)
    shaded = (
        shaded * (1.0 - cloud_opacity[..., None])
        + np.asarray((205, 222, 235), dtype=np.float32)
        * (0.32 + 0.68 * daylight[..., None])
        * cloud_opacity[..., None]
    )
    if city_lights > 0:
        city_texture = generate_city_light_texture(
            suitability, seed, (texture.get_width(), texture.get_height()))
        city_pixels = _surface_array(city_texture)[tex_y, tex_x]
        city_alpha = pygame.surfarray.array_alpha(city_texture).T[
            tex_y, tex_x].astype(np.float32) / 255.0
        city_alpha *= min(1.0, city_lights) * np.clip(
            -illumination, 0.0, 1.0) ** 1.2
        city_alpha *= 1.0 - cloud_opacity * 0.35
        shaded = (
            shaded * (1.0 - city_alpha[..., None])
            + city_pixels * city_alpha[..., None] * 1.15
        )
    shaded = np.clip(shaded, 0, 255).astype(np.uint8)
    pixels3d = pygame.surfarray.pixels3d(sphere)
    pixels3d[:, :, :] = np.transpose(shaded, (1, 0, 2))
    del pixels3d
    pixels_alpha = pygame.surfarray.pixels_alpha(sphere)
    pixels_alpha[:, :] = np.transpose(mask.astype(np.uint8) * 255, (1, 0))
    del pixels_alpha

    _, _, highlight_color = SUITABILITY_STYLES[
        dominant_suitability(suitability)]
    pygame.draw.arc(
        sphere, highlight_color,
        (center - radius + 2, center - radius + 2,
         radius * 2 - 4, radius * 2 - 4),
        3.8, 5.7, max(1, size // 32),
    )
    pygame.draw.circle(sphere, (196, 227, 255), (center, center), radius, 1)
    return sphere


def generate_planet_texture(
        suitability: Mapping[str, float], seed: str,
        size: tuple[int, int] = (256, 128),
        detail_level: int = 3) -> pygame.Surface:
    """Create a repeatable equirectangular surface for 3D planet rendering."""
    width, height = size
    if width < 32 or height < 16:
        raise ValueError("Planet textures must be at least 32x16 pixels")
    if not isinstance(detail_level, int) or not 1 <= detail_level <= 8:
        raise ValueError("Texture detail must be an integer from 1 to 8")
    pixel_scale = 0.5 + detail_level * 0.5
    width = round(width * pixel_scale)
    height = round(height * pixel_scale)

    suitability_type = dominant_suitability(suitability)
    base_color, land_color, highlight_color = SUITABILITY_STYLES[
        suitability_type]
    generator = random.Random(_stable_seed(seed))
    continents = (
        0.58 * _periodic_value_noise(width, height, 6, 3, generator)
        + 0.29 * _periodic_value_noise(width, height, 12, 6, generator)
        + 0.13 * _periodic_value_noise(width, height, 24, 12, generator)
    )
    terrain_layers = [
        _periodic_value_noise(
            width, height,
            min(width // 2, 16 * 2 ** octave),
            min(height // 2, 8 * 2 ** octave),
            generator)
        for octave in range(detail_level)
    ]
    terrain_weights = np.asarray(
        [0.5 ** octave for octave in range(detail_level)],
        dtype=np.float32)
    terrain_weights /= terrain_weights.sum()
    terrain_variation = sum(
        layer * weight
        for layer, weight in zip(terrain_layers, terrain_weights))
    latitude = np.linspace(-math.pi / 2, math.pi / 2, height)
    latitude = np.broadcast_to(latitude[:, None], (height, width))
    land_mask = np.clip((continents - 0.455) / 0.105, 0.0, 1.0)
    terrain_variation = np.clip(terrain_variation, 0.0, 1.0)
    ocean_depth = np.clip((0.52 - continents) * 2.8, 0.0, 1.0)

    ocean = np.asarray(base_color, dtype=np.float32) * (
        0.58 + 0.48 * (1.0 - ocean_depth[..., None]))
    shallow = np.asarray(land_color, dtype=np.float32) * 0.54
    ocean = ocean * (1.0 - land_mask[..., None] * 0.56) + (
        shallow * land_mask[..., None] * 0.56)
    land_dark = np.asarray(land_color, dtype=np.float32) * 0.72
    land_bright = np.asarray(highlight_color, dtype=np.float32) * 0.86
    land = land_dark * (1.0 - terrain_variation[..., None]) + (
        land_bright * terrain_variation[..., None])
    color = ocean * (1.0 - land_mask[..., None]) + (
        land * land_mask[..., None])

    polar_ice = np.clip(
        (np.abs(latitude) - 0.96
         + (terrain_layers[-1] - 0.5) * 0.11) / 0.08,
        0.0, 1.0,
    )
    ice_color = np.asarray((194, 222, 231), dtype=np.float32)
    color = color * (1.0 - polar_ice[..., None]) + (
        ice_color * polar_ice[..., None])

    surface_reference = _seeded_asset_pixels(
        "earth_surface.jpg", (width, height), seed, "surface"
    ).astype(np.float32)
    surface_luminance = (
        0.2126 * surface_reference[..., 0]
        + 0.7152 * surface_reference[..., 1]
        + 0.0722 * surface_reference[..., 2]
    )
    brightness_detail = np.clip(
        0.78 + 0.38 * surface_luminance / 255.0, 0.78, 1.16)
    chroma_detail = surface_reference - surface_luminance[..., None]
    color = color * brightness_detail[..., None] + chroma_detail * 0.12

    rgb = np.clip(color, 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(
        np.transpose(rgb, (1, 0, 2)))
