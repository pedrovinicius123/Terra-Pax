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


def generate_city_light_texture(
        suitability: Mapping[str, float], seed: str,
        size: tuple[int, int], detail_level: int = 3) -> pygame.Surface:
    """Create seeded city clusters and roads restricted to procedural land."""
    width, height = size
    if width < 32 or height < 16:
        raise ValueError("Planet textures must be at least 32x16 pixels")
    if not isinstance(detail_level, int) or not 1 <= detail_level <= 8:
        raise ValueError("Texture detail must be an integer from 1 to 8")
    _, land_mask, _, _ = _planet_fields(seed, size, detail_level)
    land_pixels = np.argwhere(land_mask >= 0.5)
    light_strength = np.zeros((height, width), dtype=np.float32)
    if len(land_pixels):
        generator = random.Random(_stable_seed(f"{seed}:cities"))
        pixel_generator = np.random.default_rng(
            _stable_seed(f"{seed}:city-pixels"))
        count = max(80, min(320, width * height // 1200))
        base_radius = max(0.024, min(0.075, 4.0 * math.tau / width))
        centers = generator.sample(
            range(len(land_pixels)), min(count, len(land_pixels)))
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
    land_pixels = np.argwhere(
        generate_planet_land_mask(seed, (720, 360), 3))
    center_indices = generator.sample(
        range(len(land_pixels)), min(max(0, count), len(land_pixels)))

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
