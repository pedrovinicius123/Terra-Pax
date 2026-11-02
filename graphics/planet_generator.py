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


def generate_gas_giant_suitability(
        rng: random.Random | None = None) -> dict[str, float]:
    """Hostile profile: gas giants barely sustain any life."""
    generator = random if rng is None else rng
    return {
        category: generator.uniform(0.02, 0.18)
        for category in SUITABILITY_STYLES
    }


def generate_asteroid_suitability(
        rng: random.Random | None = None) -> dict[str, float]:
    """Low profile: belt bodies only support small outpost populations."""
    generator = random if rng is None else rng
    return {
        category: generator.uniform(0.05, 0.35)
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
    return math.sqrt(development_ratio * population_ratio)


def _stable_seed(value: str) -> int:
    seed = 2166136261
    for character in value:
        seed = ((seed ^ ord(character)) * 16777619) & 0xFFFFFFFF
    return seed


ASSET_DIRECTORY = Path(__file__).with_name("assets")
PLANET_SUN_DIRECTION = (-0.82, 0.25, 0.35)
_ASSET_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".webp"}
_ASSET_LAYER_TOKENS = {
    "clouds": ("cloud",),
    "starfield": ("starfield", "star_field", "sky"),
}


@lru_cache(maxsize=4)
def _assets_for_layer(layer: str) -> tuple[str, ...]:
    tokens = _ASSET_LAYER_TOKENS[layer]
    paths = []
    for path in ASSET_DIRECTORY.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in _ASSET_EXTENSIONS:
            continue
        if "ships" in path.relative_to(ASSET_DIRECTORY).parts:
            continue
        stem = path.stem.lower()
        if any(token in stem for token in tokens):
            paths.append(path.relative_to(ASSET_DIRECTORY).as_posix())
    if not paths:
        raise FileNotFoundError(
            f"No planet texture assets found for layer '{layer}' "
            f"in {ASSET_DIRECTORY}")
    return tuple(sorted(paths))


def _asset_for_layer(layer: str, seed: str) -> str:
    assets = _assets_for_layer(layer)
    index = _stable_seed(f"{seed}:{layer}:asset") % len(assets)
    return assets[index]


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
        _load_asset_surface(_asset_for_layer("starfield", "global")), size)
    starfield.fill((95, 120, 165), special_flags=pygame.BLEND_RGB_MULT)
    starfield.set_alpha(220)
    return starfield


def _seeded_asset_pixels(
        size: tuple[int, int], seed: str, layer: str) -> np.ndarray:
    filename = _asset_for_layer(layer, seed)
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
        size, seed, "clouds").astype(np.float32)
    luminance = (
        0.2126 * source[..., 0]
        + 0.7152 * source[..., 1]
        + 0.0722 * source[..., 2]
    )
    alpha = np.clip((luminance - 45.0) * 2.1, 0, 220).astype(np.uint8)
    cloud = pygame.Surface((width, height), pygame.SRCALPHA)
    rgb_pixels = pygame.surfarray.pixels3d(cloud)
    rgb_pixels[:, :, :] = (205, 222, 235)
    del rgb_pixels
    alpha_pixels = pygame.surfarray.pixels_alpha(cloud)
    alpha_pixels[:, :] = alpha.T
    del alpha_pixels
    return cloud


@lru_cache(maxsize=4)
def _sphere_coordinates(
        size: tuple[int, int]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    width, height = size
    longitude = (
        (np.arange(width, dtype=np.float32) + 0.5) / width - 0.5
    ) * math.tau
    latitude = (
        0.5 - (np.arange(height, dtype=np.float32) + 0.5) / height
    ) * math.pi
    lon, lat = np.meshgrid(longitude, latitude)
    cos_latitude = np.cos(lat)
    return (
        cos_latitude * np.sin(lon),
        np.sin(lat),
        cos_latitude * np.cos(lon),
    )


def _spherical_value_noise(
        x: np.ndarray, y: np.ndarray, z: np.ndarray,
        grid_size: int, generator: np.random.Generator) -> np.ndarray:
    lattice = generator.random(
        (grid_size, grid_size, grid_size), dtype=np.float32)
    coordinates = [
        (component + 1.0) * (0.5 * grid_size)
        for component in (x, y, z)
    ]
    floors = [np.floor(axis).astype(np.int32) for axis in coordinates]
    fractions = [axis - floor for axis, floor in zip(coordinates, floors)]
    blends = [
        fraction * fraction * (3.0 - 2.0 * fraction)
        for fraction in fractions
    ]
    x0, y0, z0 = (floor % grid_size for floor in floors)
    x1, y1, z1 = (
        (floor + 1) % grid_size for floor in floors)
    blend_x, blend_y, blend_z = blends

    corners = [
        lattice[zi, yi, xi]
        for zi, yi, xi in (
            (z0, y0, x0), (z0, y0, x1),
            (z0, y1, x0), (z0, y1, x1),
            (z1, y0, x0), (z1, y0, x1),
            (z1, y1, x0), (z1, y1, x1),
        )
    ]
    near = (
        corners[0] * (1.0 - blend_x) + corners[1] * blend_x
    ) * (1.0 - blend_y) + (
        corners[2] * (1.0 - blend_x) + corners[3] * blend_x
    ) * blend_y
    far = (
        corners[4] * (1.0 - blend_x) + corners[5] * blend_x
    ) * (1.0 - blend_y) + (
        corners[6] * (1.0 - blend_x) + corners[7] * blend_x
    ) * blend_y
    return near * (1.0 - blend_z) + far * blend_z


def _resize_scalar_field(
        field: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    width, height = size
    source_height, source_width = field.shape
    if (source_width, source_height) == size:
        return field
    sample_x = (
        (np.arange(width, dtype=np.float32) + 0.5)
        * source_width / width - 0.5
    )
    sample_y = (
        (np.arange(height, dtype=np.float32) + 0.5)
        * source_height / height - 0.5
    )
    x_floor = np.floor(sample_x).astype(np.int32)
    y_floor = np.floor(sample_y).astype(np.int32)
    x0, x1 = x_floor % source_width, (x_floor + 1) % source_width
    y0 = np.clip(y_floor, 0, source_height - 1)
    y1 = np.clip(y_floor + 1, 0, source_height - 1)
    blend_x = sample_x - x_floor
    blend_y = sample_y - y_floor
    upper = (
        field[y0[:, None], x0[None, :]]
        * (1.0 - blend_x[None, :])
        + field[y0[:, None], x1[None, :]] * blend_x[None, :]
    )
    lower = (
        field[y1[:, None], x0[None, :]]
        * (1.0 - blend_x[None, :])
        + field[y1[:, None], x1[None, :]] * blend_x[None, :]
    )
    return upper * (1.0 - blend_y[:, None]) + lower * blend_y[:, None]


@lru_cache(maxsize=8)
def _planet_fields(
        seed: str, size: tuple[int, int], detail_level: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    width, height = size
    field_size = (min(width, 768), min(height, 384))
    x, y, z = _sphere_coordinates(field_size)
    warp_generator = np.random.default_rng(
        _stable_seed(f"{seed}:continent-warp"))
    warped_x = x + (
        _spherical_value_noise(x, y, z, 2, warp_generator) - 0.5
    ) * 0.28
    warped_y = y + (
        _spherical_value_noise(x, y, z, 2, warp_generator) - 0.5
    ) * 0.28
    warped_z = z + (
        _spherical_value_noise(x, y, z, 2, warp_generator) - 0.5
    ) * 0.28

    continent_generator = np.random.default_rng(
        _stable_seed(f"{seed}:continents"))
    continent = (
        0.46 * _spherical_value_noise(
            warped_x, warped_y, warped_z, 3, continent_generator)
        + 0.27 * _spherical_value_noise(
            warped_x, warped_y, warped_z, 6, continent_generator)
        + 0.15 * _spherical_value_noise(
            warped_x, warped_y, warped_z, 12, continent_generator)
        + 0.08 * _spherical_value_noise(
            warped_x, warped_y, warped_z, 24, continent_generator)
        + 0.04 * _spherical_value_noise(
            warped_x, warped_y, warped_z, 48, continent_generator)
    )
    sea_level_generator = random.Random(
        _stable_seed(f"{seed}:sea-level"))
    land_fraction = sea_level_generator.uniform(0.28, 0.46)
    sea_level = float(np.quantile(continent, 1.0 - land_fraction))
    shore_width = 0.03
    land_mask = np.clip(
        (continent - sea_level + shore_width) / (2.0 * shore_width),
        0.0, 1.0,
    )

    terrain_generator = np.random.default_rng(
        _stable_seed(f"{seed}:terrain"))
    terrain_grids = []
    for octave in range(detail_level):
        grid_size = min(96, 4 * 2 ** octave)
        if not terrain_grids or grid_size != terrain_grids[-1][0]:
            terrain_grids.append((
                grid_size,
                _spherical_value_noise(
                    x, y, z, grid_size, terrain_generator),
            ))
    terrain_weights = np.asarray(
        [0.55 ** octave for octave in range(len(terrain_grids))],
        dtype=np.float32)
    terrain_weights /= terrain_weights.sum()
    terrain = sum(
        layer * weight
        for (_, layer), weight in zip(terrain_grids, terrain_weights))
    latitude = np.arcsin(np.clip(y, -1.0, 1.0))
    if field_size != size:
        continent, land_mask, terrain, latitude = (
            _resize_scalar_field(field, size)
            for field in (continent, land_mask, terrain, latitude)
        )
    return continent, land_mask, terrain, latitude


def generate_planet_land_mask(
        seed: str, size: tuple[int, int] = (256, 128),
        detail_level: int = 3) -> np.ndarray:
    """Return a deterministic land mask; true pixels are above sea level."""
    width, height = size
    if width < 32 or height < 16:
        raise ValueError("Planet textures must be at least 32x16 pixels")
    if not isinstance(detail_level, int) or not 1 <= detail_level <= 8:
        raise ValueError("Texture detail must be an integer from 1 to 8")
    _, land_mask, _, _ = _planet_fields(seed, size, detail_level)
    return (land_mask >= 0.5).copy()


def _settlement_site_weights(
        land_mask: np.ndarray, terrain: np.ndarray,
        latitude: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    land = land_mask >= 0.5
    north = np.zeros_like(land)
    south = np.zeros_like(land)
    north[1:] = land[:-1]
    south[:-1] = land[1:]
    east = np.roll(land, 1, axis=1)
    west = np.roll(land, -1, axis=1)
    coast = land & ~(north & south & east & west)
    coast_influence = coast.astype(np.float32)
    for offset in (1, 2):
        north_coast = np.zeros_like(coast)
        south_coast = np.zeros_like(coast)
        north_coast[offset:] = coast[:-offset]
        south_coast[:-offset] = coast[offset:]
        coast_influence = np.maximum(
            coast_influence,
            north_coast.astype(np.float32) / (offset + 1))
        coast_influence = np.maximum(
            coast_influence,
            south_coast.astype(np.float32) / (offset + 1))
        coast_influence = np.maximum(
            coast_influence,
            np.roll(coast, offset, axis=1).astype(np.float32) / (offset + 1))
        coast_influence = np.maximum(
            coast_influence,
            np.roll(coast, -offset, axis=1).astype(np.float32)
            / (offset + 1))

    terrain_variation = np.zeros_like(terrain, dtype=np.float32)
    north_terrain = np.empty_like(terrain)
    south_terrain = np.empty_like(terrain)
    north_terrain[0] = terrain[0]
    north_terrain[1:] = terrain[:-1]
    south_terrain[-1] = terrain[-1]
    south_terrain[:-1] = terrain[1:]
    terrain_variation += np.abs(terrain - north_terrain)
    terrain_variation += np.abs(terrain - south_terrain)
    terrain_variation += np.abs(terrain - np.roll(terrain, 1, axis=1))
    terrain_variation += np.abs(terrain - np.roll(terrain, -1, axis=1))
    flatness = np.clip(1.0 - terrain_variation * 2.0, 0.15, 1.0)
    temperate = np.clip(np.cos(latitude) ** 1.5, 0.12, 1.0)
    moderate_elevation = np.exp(-((terrain - 0.48) / 0.3) ** 2)
    weights = (
        (0.35 + coast_influence * 1.4)
        * flatness * temperate * (0.35 + moderate_elevation)
        * land
    )
    return land, weights.astype(np.float64)


def generate_city_light_texture(
        suitability: Mapping[str, float], seed: str,
        size: tuple[int, int], detail_level: int = 3) -> pygame.Surface:
    """Create seeded city clusters and roads restricted to procedural land."""
    width, height = size
    if width < 32 or height < 16:
        raise ValueError("Planet textures must be at least 32x16 pixels")
    if not isinstance(detail_level, int) or not 1 <= detail_level <= 8:
        raise ValueError("Texture detail must be an integer from 1 to 8")
    _, land_mask, terrain, latitude = _planet_fields(
        seed, size, detail_level)
    land, site_weights = _settlement_site_weights(
        land_mask, terrain, latitude)
    land_pixels = np.argwhere(land)
    light_strength = np.zeros((height, width), dtype=np.float32)
    if len(land_pixels):
        generator = random.Random(_stable_seed(f"{seed}:cities"))
        pixel_generator = np.random.default_rng(
            _stable_seed(f"{seed}:city-pixels"))
        site_generator = np.random.default_rng(
            _stable_seed(f"{seed}:city-sites"))
        count = max(80, min(320, width * height // 1200))
        base_radius = max(0.024, min(0.075, 4.0 * math.tau / width))
        probabilities = site_weights[land]
        probabilities /= probabilities.sum()
        centers = site_generator.choice(
            len(land_pixels), min(count, len(land_pixels)),
            replace=False, p=probabilities)
        for center_index in centers:
            center_y, center_x = land_pixels[center_index]
            latitude = (
                0.5 - (center_y + 0.5) / height) * math.pi
            longitude = (
                (center_x + 0.5) / width - 0.5) * math.tau
            city_radius = base_radius * generator.uniform(0.8, 2.3)
            radius_y = max(
                1, math.ceil(city_radius * height / math.pi * 1.4))
            radius_x = max(
                1, math.ceil(
                    city_radius * width / math.tau
                    / max(0.18, math.cos(latitude)) * 1.4))
            y0, y1 = max(0, center_y - radius_y), min(
                height, center_y + radius_y + 1)
            x_indices = np.arange(
                center_x - radius_x, center_x + radius_x + 1) % width
            y_indices = np.arange(y0, y1)
            local_latitudes = (
                0.5 - (y_indices + 0.5) / height) * math.pi
            local_longitudes = (
                (x_indices + 0.5) / width - 0.5) * math.tau
            delta_latitude = (
                local_latitudes[:, None] - latitude)
            delta_longitude = (
                (local_longitudes[None, :] - longitude + math.pi)
                % math.tau - math.pi
            ) * math.cos(latitude)
            distance = np.hypot(delta_latitude, delta_longitude)
            angle = np.arctan2(delta_latitude, delta_longitude)
            core = np.exp(-2.8 * (distance / city_radius) ** 2)
            spoke_count = generator.randint(4, 8)
            road_distance = np.abs(np.sin(
                angle * spoke_count + generator.uniform(0.0, math.tau)))
            roads = (
                np.exp(-distance / (city_radius * 0.72))
                * np.exp(-((road_distance / 0.075) ** 2))
            )
            land = land_mask[np.ix_(y_indices, x_indices)]
            pixel_noise = pixel_generator.uniform(
                0.68, 1.0, size=(len(y_indices), len(x_indices))
            ).astype(np.float32)
            cluster = np.maximum(core * 0.78, roads * 0.92)
            cluster *= pixel_noise * (land >= 0.5)
            local = light_strength[np.ix_(y_indices, x_indices)]
            np.maximum(local, cluster * 255.0, out=local)
            light_strength[np.ix_(y_indices, x_indices)] = local

    _, _, highlights = SUITABILITY_STYLES[
        dominant_suitability(suitability)]
    color = np.asarray((255, 178, 92), dtype=np.float32) * 0.82 + (
        np.asarray(highlights, dtype=np.float32) * 0.18)
    city = pygame.Surface((width, height), pygame.SRCALPHA)
    rgb_pixels = pygame.surfarray.pixels3d(city)
    rgb_pixels[:, :, :] = np.broadcast_to(
        np.clip(color, 0, 255).astype(np.uint8), (width, height, 3))
    del rgb_pixels
    alpha_pixels = pygame.surfarray.pixels_alpha(city)
    alpha_pixels[:, :] = np.transpose(
        np.clip(light_strength, 0, 255).astype(np.uint8), (1, 0))
    del alpha_pixels
    return city


@lru_cache(maxsize=256)
def generate_city_networks(seed: str, count: int = 36):
    """Create deterministic city clusters with roads and dense block lights."""
    generator = random.Random(_stable_seed(f"{seed}:cities"))
    networks = []
    grid = (-0.72, -0.36, 0.0, 0.36, 0.72)
    _, land_mask, terrain, latitude = _planet_fields(
        seed, (720, 360), 3)
    land, site_weights = _settlement_site_weights(
        land_mask, terrain, latitude)
    land_pixels = np.argwhere(land)
    probabilities = site_weights[land]
    probabilities /= probabilities.sum()
    site_generator = np.random.default_rng(_stable_seed(f"{seed}:city-sites"))
    center_indices = site_generator.choice(
        len(land_pixels), min(max(0, count), len(land_pixels)),
        replace=False, p=probabilities)

    for center_index in center_indices:
        center_y, center_x = land_pixels[center_index]
        latitude = (
            0.5 - (center_y + 0.5) / 360) * math.pi
        longitude = (
            (center_x + 0.5) / 720 - 0.5) * math.tau
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


def _surface_array(texture: pygame.Surface) -> np.ndarray:
    return np.transpose(pygame.surfarray.array3d(texture), (1, 0, 2))


def _sample_pixels_bilinear(
        pixels: np.ndarray, sample_x: np.ndarray,
        sample_y: np.ndarray) -> np.ndarray:
    height, width = pixels.shape[:2]
    x_floor = np.floor(sample_x).astype(np.int32)
    y_floor = np.floor(sample_y).astype(np.int32)
    x0, x1 = x_floor % width, (x_floor + 1) % width
    y0 = np.clip(y_floor, 0, height - 1)
    y1 = np.clip(y_floor + 1, 0, height - 1)
    blend_x = sample_x - x_floor
    blend_y = sample_y - y_floor
    if pixels.ndim == 3:
        blend_x = blend_x[..., None]
        blend_y = blend_y[..., None]
    upper = (
        pixels[y0, x0] * (1.0 - blend_x)
        + pixels[y0, x1] * blend_x
    )
    lower = (
        pixels[y1, x0] * (1.0 - blend_x)
        + pixels[y1, x1] * blend_x
    )
    return upper * (1.0 - blend_y) + lower * blend_y


def generate_planet_surface(
        suitability: Mapping[str, float], seed: str,
        size: int = 96, city_lights: float = 0.0,
        detail_level: int = 3, planet_type: str = 'terrestrial',
        rings: bool = False) -> pygame.Surface:
    """Render a repeatable, randomly textured 2D planet for a world."""
    if planet_type == 'gas_giant':
        return generate_gas_giant_surface(
            seed, size, detail_level, rings=rings)
    if planet_type == 'asteroid':
        return generate_asteroid_surface(seed, size, detail_level)
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
    sun = np.asarray(PLANET_SUN_DIRECTION, dtype=np.float32)
    sun /= np.linalg.norm(sun)
    illumination = (
        nx * sun[0] + ny * sun[1] + nz * sun[2])
    brightness = 0.20 + 0.80 * np.maximum(0.0, illumination)
    pixels = _sample_pixels_bilinear(
        texture_pixels,
        ((longitude / math.tau + 0.5) * texture.get_width()) - 0.5,
        ((0.5 - latitude / math.pi) * texture.get_height()) - 0.5,
    )
    shaded = pixels * brightness[..., None]
    cloud_texture = generate_cloud_texture(
        seed, (texture.get_width(), texture.get_height()))
    sample_x = (
        (longitude / math.tau + 0.5) * texture.get_width() - 0.5)
    sample_y = (
        (0.5 - latitude / math.pi) * texture.get_height() - 0.5)
    cloud_alpha = _sample_pixels_bilinear(
        pygame.surfarray.array_alpha(cloud_texture).T.astype(np.float32),
        sample_x, sample_y,
    ) / 255.0
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
            suitability, seed, (texture.get_width(), texture.get_height()),
            detail_level)
        city_pixels = _sample_pixels_bilinear(
            _surface_array(city_texture),
            sample_x, sample_y)
        city_alpha = _sample_pixels_bilinear(
            pygame.surfarray.array_alpha(city_texture).T.astype(np.float32),
            sample_x, sample_y) / 255.0
        city_strength = math.pow(
            min(1.0, max(0.0, city_lights)), 0.35)
        city_alpha *= city_strength * np.clip(
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
        detail_level: int = 3,
        planet_type: str = 'terrestrial') -> pygame.Surface:
    """Create a repeatable equirectangular surface for 3D planet rendering."""
    if planet_type == 'gas_giant':
        return generate_gas_giant_texture(seed, size, detail_level)
    if planet_type == 'asteroid':
        return generate_asteroid_texture(seed, size, detail_level)
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
    continents, land_mask, terrain_variation, latitude = _planet_fields(
        seed, (width, height), detail_level)
    terrain_variation = np.clip(
        (terrain_variation - 0.32) * 2.6, 0.0, 1.0)
    ocean_depth = np.clip((0.48 - continents) * 3.2, 0.0, 1.0)

    ocean = np.asarray(base_color, dtype=np.float32) * (
        0.48 + 0.62 * (1.0 - ocean_depth[..., None]))
    shallow = (
        np.asarray(base_color, dtype=np.float32) * 0.68
        + np.asarray(land_color, dtype=np.float32) * 0.22
    )
    ocean = ocean * (1.0 - land_mask[..., None] * 0.72) + (
        shallow * land_mask[..., None] * 0.72)
    land_dark = np.asarray(land_color, dtype=np.float32) * 0.72
    land_bright = np.asarray(highlight_color, dtype=np.float32) * 0.86
    land = land_dark * (1.0 - terrain_variation[..., None]) + (
        land_bright * terrain_variation[..., None])
    color = ocean * (1.0 - land_mask[..., None]) + (
        land * land_mask[..., None])

    polar_ice = np.clip(
        (np.abs(latitude) - 0.96
         + (terrain_variation - 0.5) * 0.11) / 0.08,
        0.0, 1.0,
    )
    ice_color = np.asarray((194, 222, 231), dtype=np.float32)
    color = color * (1.0 - polar_ice[..., None]) + (
        ice_color * polar_ice[..., None])

    rgb = np.clip(color, 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(
        np.transpose(rgb, (1, 0, 2)))


GAS_GIANT_PALETTES = (
    ((235, 205, 160), (150, 106, 70), (206, 120, 86)),
    ((182, 216, 228), (86, 132, 158), (232, 244, 250)),
    ((216, 158, 122), (122, 74, 62), (244, 190, 150)),
    ((170, 178, 222), (92, 100, 158), (222, 228, 252)),
    ((224, 206, 158), (152, 124, 78), (248, 236, 196)),
)

ASTEROID_PALETTES = (
    ((150, 142, 132), (96, 90, 82), (190, 182, 170)),
    ((132, 118, 104), (84, 74, 66), (172, 158, 140)),
    ((118, 120, 126), (76, 78, 86), (162, 166, 174)),
)


def _check_texture_arguments(size: tuple[int, int],
                             detail_level: int) -> tuple[int, int]:
    width, height = size
    if width < 32 or height < 16:
        raise ValueError("Planet textures must be at least 32x16 pixels")
    if not isinstance(detail_level, int) or not 1 <= detail_level <= 8:
        raise ValueError("Texture detail must be an integer from 1 to 8")
    pixel_scale = 0.5 + detail_level * 0.5
    return round(width * pixel_scale), round(height * pixel_scale)


def gas_giant_palette(seed: str) -> tuple[tuple[int, int, int], ...]:
    """Return the (light, dark, storm) palette chosen for a gas giant."""
    generator = random.Random(_stable_seed(f"{seed}:gas-giant"))
    return GAS_GIANT_PALETTES[
        generator.randrange(len(GAS_GIANT_PALETTES))]


def generate_gas_giant_texture(
        seed: str, size: tuple[int, int] = (256, 128),
        detail_level: int = 3) -> pygame.Surface:
    """Banded equirectangular texture with turbulence and storm ovals."""
    width, height = _check_texture_arguments(size, detail_level)
    x, y, z = _sphere_coordinates((width, height))
    latitude = np.arcsin(np.clip(y, -1.0, 1.0))
    longitude = np.arctan2(x, z)

    generator = random.Random(_stable_seed(f"{seed}:gas-giant"))
    light_band, dark_band, storm_color = gas_giant_palette(seed)
    noise = np.random.default_rng(_stable_seed(f"{seed}:gas-bands"))

    turbulence = (
        0.5 * _spherical_value_noise(x, y, z, 6, noise)
        + 0.5 * _spherical_value_noise(x, y, z, 12, noise))
    band_frequency = generator.uniform(3.0, 6.0)
    phase = latitude * band_frequency + (turbulence - 0.5) * 2.8
    band = 0.5 + 0.5 * np.sin(phase * math.tau)
    streaks = _spherical_value_noise(
        x, y, z, min(96, 12 + 6 * detail_level), noise)
    band = np.clip(band + (streaks - 0.5) * 0.3, 0.0, 1.0)

    light_rgb = np.asarray(light_band, dtype=np.float32)
    dark_rgb = np.asarray(dark_band, dtype=np.float32)
    color = dark_rgb * (1.0 - band[..., None]) + (
        light_rgb * band[..., None])
    color *= (0.86 + 0.28 * turbulence)[..., None]

    for index in range(generator.randint(1, 4)):
        major = index == 0
        center_lat = (generator.uniform(-0.9, 0.9) if major
                      else generator.uniform(-1.2, 1.2))
        center_lon = generator.uniform(-math.pi, math.pi)
        radius_x = (generator.uniform(0.35, 0.7) if major
                    else generator.uniform(0.1, 0.3))
        radius_y = (generator.uniform(0.14, 0.24) if major
                    else generator.uniform(0.05, 0.12))
        delta_lon = (
            ((longitude - center_lon + math.pi) % math.tau - math.pi)
            * max(0.25, abs(math.cos(center_lat))) / radius_x)
        delta_lat = (latitude - center_lat) / radius_y
        blob = np.clip(
            1.0 - delta_lon ** 2 - delta_lat ** 2, 0.0, 1.0) ** 2
        tint = (np.asarray(storm_color, dtype=np.float32) if major
                else light_rgb * generator.uniform(0.9, 1.1))
        strength = 0.9 if major else 0.55
        color = color * (1.0 - blob[..., None] * strength) + (
            tint * blob[..., None] * strength)

    polar = np.clip((np.abs(latitude) - 1.12) / 0.35, 0.0, 1.0)
    color = color * (1.0 - 0.3 * polar[..., None]) + (
        dark_rgb * 0.3 * polar[..., None])

    rgb = np.clip(color, 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))


def generate_asteroid_texture(
        seed: str, size: tuple[int, int] = (256, 128),
        detail_level: int = 3) -> pygame.Surface:
    """Cratered grey-brown equirectangular texture for belt bodies."""
    width, height = _check_texture_arguments(size, detail_level)
    x, y, z = _sphere_coordinates((width, height))
    latitude = np.arcsin(np.clip(y, -1.0, 1.0))
    longitude = np.arctan2(x, z)

    generator = random.Random(_stable_seed(f"{seed}:asteroid"))
    base_rgb_tuple, dark_rgb_tuple, bright_rgb = ASTEROID_PALETTES[
        generator.randrange(len(ASTEROID_PALETTES))]
    noise = np.random.default_rng(_stable_seed(f"{seed}:asteroid-surface"))

    mottle = (
        0.5 * _spherical_value_noise(x, y, z, 4, noise)
        + 0.5 * _spherical_value_noise(x, y, z, 9, noise))
    base_rgb = np.asarray(base_rgb_tuple, dtype=np.float32)
    color = base_rgb * (0.72 + 0.56 * mottle[..., None])

    dark_rgb = np.asarray(dark_rgb_tuple, dtype=np.float32)
    bright_rgb = np.asarray(bright_rgb, dtype=np.float32)
    for _ in range(generator.randint(24, 60)):
        center_lat = generator.uniform(-1.35, 1.35)
        center_lon = generator.uniform(-math.pi, math.pi)
        radius = generator.uniform(0.05, 0.30)
        delta_lon = (
            ((longitude - center_lon + math.pi) % math.tau - math.pi)
            * max(0.25, abs(math.cos(center_lat))) / radius)
        delta_lat = (latitude - center_lat) / radius
        distance = np.hypot(delta_lon, delta_lat)
        bowl = np.clip((0.8 - distance) / 0.8, 0.0, 1.0) ** 1.5
        rim = np.clip(1.0 - np.abs(distance - 0.94) / 0.26, 0.0, 1.0)
        color = color * (1.0 - 0.4 * bowl[..., None]) + (
            dark_rgb * 0.4 * bowl[..., None])
        color = color + (bright_rgb - color) * (
            rim[..., None] * 0.28)

    rgb = np.clip(color, 0, 255).astype(np.uint8)
    return pygame.surfarray.make_surface(np.transpose(rgb, (1, 0, 2)))


@lru_cache(maxsize=64)
def _asteroid_shape(seed: str) -> tuple[tuple[int, float, float], ...]:
    generator = random.Random(_stable_seed(f"{seed}:asteroid-shape"))
    return tuple(
        (harmonic, generator.uniform(0.05, 0.16) / harmonic ** 0.5,
         generator.uniform(0.0, math.tau))
        for harmonic in (1, 2, 3, 4, 5)
    )


def asteroid_radius_factor(seed: str,
                           theta: np.ndarray) -> np.ndarray:
    """Lumpy silhouette radius multiplier for an asteroid at screen angle."""
    factor = np.ones_like(theta, dtype=np.float32)
    for harmonic, amplitude, phase in _asteroid_shape(seed):
        factor += amplitude * np.sin(harmonic * theta + phase)
    return np.clip(factor, 0.62, 1.38)


def _shaded_sphere_from_texture(
        texture: pygame.Surface, size: int, radius: np.ndarray | float,
        center: float, ambient: float) -> pygame.Surface:
    """Project an equirectangular texture onto a (possibly lumpy) disc."""
    texture_pixels = _surface_array(texture)
    sphere = pygame.Surface((size, size), pygame.SRCALPHA)
    x_grid, y_grid = np.meshgrid(
        np.arange(size, dtype=np.float32),
        np.arange(size, dtype=np.float32))
    nx = (x_grid - center) / radius
    ny = (center - y_grid) / radius
    nz_squared = 1.0 - nx ** 2 - ny ** 2
    mask = nz_squared >= 0.0
    nz = np.sqrt(np.maximum(0.0, nz_squared))
    longitude = np.arctan2(nx, nz)
    latitude = np.arcsin(np.clip(ny, -1.0, 1.0))
    sun = np.asarray(PLANET_SUN_DIRECTION, dtype=np.float32)
    sun /= np.linalg.norm(sun)
    illumination = nx * sun[0] + ny * sun[1] + nz * sun[2]
    brightness = ambient + (1.0 - ambient) * np.maximum(0.0, illumination)
    sample_x = (longitude / math.tau + 0.5) * texture.get_width() - 0.5
    sample_y = (0.5 - latitude / math.pi) * texture.get_height() - 0.5
    shaded = _sample_pixels_bilinear(
        texture_pixels, sample_x, sample_y) * brightness[..., None]
    shaded = np.clip(shaded, 0, 255).astype(np.uint8)

    pixels3d = pygame.surfarray.pixels3d(sphere)
    pixels3d[:, :, :] = np.transpose(shaded, (1, 0, 2))
    del pixels3d
    pixels_alpha = pygame.surfarray.pixels_alpha(sphere)
    pixels_alpha[:, :] = np.transpose(
        mask.astype(np.uint8) * 255, (1, 0))
    del pixels_alpha
    return sphere


def generate_gas_giant_surface(
        seed: str, size: int = 96, detail_level: int = 3,
        rings: bool = False) -> pygame.Surface:
    """Render a banded gas giant, optionally with a ring system."""
    if size < 16:
        raise ValueError("Planet surfaces must be at least 16 pixels wide")
    texture = generate_gas_giant_texture(
        seed, (size * 2, size), detail_level=detail_level)
    center = size // 2
    radius = int(size * 0.43)
    body = _shaded_sphere_from_texture(texture, size, radius, center, 0.15)

    _, _, highlight = gas_giant_palette(seed)
    pygame.draw.arc(
        body, highlight,
        (center - radius + 2, center - radius + 2,
         radius * 2 - 4, radius * 2 - 4),
        3.8, 5.7, max(1, size // 32),
    )

    if not rings:
        return body

    light_band, dark_band, _ = gas_giant_palette(seed)
    ring_color = tuple(
        int(0.45 * dark_band[axis] + 0.55 * light_band[axis])
        for axis in range(3))
    back = pygame.Surface((size, size), pygame.SRCALPHA)
    front = pygame.Surface((size, size), pygame.SRCALPHA)
    semi_major = int(size * 0.49)
    semi_minor = max(2, int(size * 0.12))
    dot = max(1, size // 40)
    for t in np.linspace(0.0, math.tau, 240):
        x = int(center + semi_major * math.cos(t))
        y = int(center + semi_minor * math.sin(t))
        target = front if math.sin(t) >= 0.0 else back
        pygame.draw.circle(target, ring_color, (x, y), dot)
        pygame.draw.circle(target, ring_color, (x, y - 1), max(1, dot - 1))
    composed = pygame.Surface((size, size), pygame.SRCALPHA)
    composed.blit(back, (0, 0))
    composed.blit(body, (0, 0))
    composed.blit(front, (0, 0))
    return composed


def generate_asteroid_surface(
        seed: str, size: int = 64, detail_level: int = 3) -> pygame.Surface:
    """Render a cratered, irregularly shaped asteroid body."""
    if size < 16:
        raise ValueError("Planet surfaces must be at least 16 pixels wide")
    texture = generate_asteroid_texture(
        seed, (size * 2, size), detail_level=detail_level)
    center = size // 2
    base_radius = int(size * 0.34)
    x_grid, y_grid = np.meshgrid(
        np.arange(size, dtype=np.float32),
        np.arange(size, dtype=np.float32))
    theta = np.arctan2(y_grid - center, x_grid - center)
    radius = base_radius * asteroid_radius_factor(seed, theta)
    radius = np.maximum(radius, 1.0)
    return _shaded_sphere_from_texture(texture, size, radius, center, 0.06)
