"""Estrelas do mapa desenhadas como estrelas, não como círculos chapados.

Cada sistema recebe uma classe espectral determinística (nome + recursos do
sistema) e é montado uma única vez como sprite RGBA premultiplicado: disco com
escurecimento de limbo, corona suave e riscos de difração. O custo por quadro é
um blit; a construção acontece uma vez por degrau de tamanho.

Perto do zoom máximo o disco cresce mais do que cabe numa superfície sem gastar
memória ou tempo demais, então acima do último degrau o corpo é pintado com
círculos concêntricos nas mesmas cores do sprite — o resultado é o mesmo
gradiente, só que recortado pela tela em vez de por um sprite gigante.
"""
import math
import zlib
from collections import OrderedDict

import numpy as np
import pygame


# (classe, peso, corpo, corona, limbo, alcance da corona, força do clarão)
SPECTRAL_CLASSES = (
    ('O', 0.010, (165, 185, 255), (104, 138, 255), 0.62, 3.1, 1.00),
    ('B', 0.035, (186, 203, 255), (130, 158, 255), 0.56, 2.8, 0.90),
    ('A', 0.070, (208, 220, 255), (168, 190, 250), 0.50, 2.5, 0.78),
    ('F', 0.115, (241, 244, 250), (212, 220, 240), 0.44, 2.3, 0.66),
    ('G', 0.170, (255, 235, 188), (255, 208, 130), 0.40, 2.2, 0.58),
    ('K', 0.260, (255, 203, 137), (255, 162, 84), 0.36, 2.1, 0.50),
    ('M', 0.340, (255, 163, 124), (226, 98, 74), 0.32, 2.0, 0.42),
)

# Degraus de disco (px). Geométricos: no máximo ~22% de erro de tamanho, e só
# estas poucas superfícies existem por classe espectral.
DISK_STEPS = (2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 26, 34, 44)
LARGEST_STEP = DISK_STEPS[-1]

# Acima do último degrau o sprite é ampliado; o teto de 1030 px mantém um blit
# de ~1 ms e a memória do cache na casa de dezenas de MB nem sempre usados.
MAX_SCALED_EDGE = 1030
SCALED_RATIO_STEP = 1.08        # quantização do tamanho ampliado (~8% de erro)
SCALED_BUDGET = 3_000_000       # pixels vivos no cache de ampliados

# Quando nem o teto de blit alcança, o corpo é pintado em faixas concêntricas:
# o mesmo gradiente radial, recortado pela tela e sem superfície gigante.
RIM_REACH = 1.06                # a corona externa fica de fora nas faixas
CORE_FRACTION = 0.5             # abaixo disso o disco é praticamente chato
CLOSE_BANDS = 12

_CUMULATIVE = None
_CLASS_BY_NAME = {}
_ENTRY_BY_CLASS = {}
_sprite_cache = {}
_scaled_cache = OrderedDict()
_scaled_pixels = 0


def _cumulative_weights():
    global _CUMULATIVE
    if _CUMULATIVE is None:
        steps = []
        total = 0.0
        for entry in SPECTRAL_CLASSES:
            total += entry[1]
            steps.append(total)
        _CUMULATIVE = (total, steps)
    return _CUMULATIVE


def stellar_class(star) -> str:
    """Classe espectral estável do sistema; ricos são mais massivos."""
    name = str(star.name)
    cached = _CLASS_BY_NAME.get(name)
    if cached is not None:
        return cached
    total, steps = _cumulative_weights()
    digest = zlib.crc32(name.encode('utf-8'))
    fraction = ((digest >> 8) & 0xFFFFFF) / float(0xFFFFFF)
    resources = float(getattr(star, 'total_resources', 0.0))
    mass = 0.0
    if resources > 1.0:
        mass = min(1.0, max(0.0, (math.log10(resources) - 4.0) / 2.0))
    fraction **= 1.0 + 1.8 * mass
    spec = 'M'
    for index, bound in enumerate(steps):
        if fraction * total <= bound:
            spec = SPECTRAL_CLASSES[index][0]
            break
    _CLASS_BY_NAME[name] = spec
    return spec


def _spec_entry(name):
    entry = _ENTRY_BY_CLASS.get(name)
    if entry is None:
        for candidate in SPECTRAL_CLASSES:
            if candidate[0] == name:
                entry = candidate
                break
        else:
            entry = SPECTRAL_CLASSES[-1]
        _ENTRY_BY_CLASS[name] = entry
    return entry


def _disk_step(radius):
    for step in DISK_STEPS:
        if radius <= step:
            return step
    return LARGEST_STEP


def _shade(entry, distance):
    """Cor RGB da superfície (limbo + clarão do núcleo) — a conta do sprite."""
    _, _, body, corona, limb, _, flare = entry
    if distance <= 1.0:
        mu = math.sqrt(max(0.0, 1.0 - distance * distance))
        light = (1.0 - limb * (1.0 - mu)) * (1.0 + 0.35 * mu)
        lum = min(1.0, light / 1.35)
        hot = min(1.0, max(0.0, (light - 1.12) / 0.23))
        return tuple(int(c * lum + (255 - c * lum) * hot) for c in body)
    # Corona externa não tem como ser translúcida em faixas chapadas: fica só o
    # contorno quente encostado no limbo.
    glow = math.exp(-(distance - 1.0) * (5.0 / entry[5])) * flare
    return tuple(int(c * min(1.0, glow) + 0.55 * (1.0 - min(1.0, glow)))
                 for c in corona)


def _visible_band(screen, center, outer):
    """Faixa de raios da estrela que realmente cai dentro da tela."""
    width, height = screen.get_size()
    cx, cy = center
    dx = max(cx - width, 0, -cx)
    dy = max(cy - height, 0, -cy)
    near = math.hypot(dx, dy)
    far = max(math.hypot(cx - x, cy - y)
              for x in (0, width) for y in (0, height))
    return max(0.0, near - 1.0), min(outer, far + 1.0)


def _draw_close_star(screen, entry, center, disk_radius):
    """Estrela maior que qualquer blit razoável: gradiente em faixas recortadas."""
    lo, hi = _visible_band(screen, center, disk_radius * RIM_REACH)
    if hi <= lo:
        return
    cx, cy = int(center[0]), int(center[1])
    core = disk_radius * CORE_FRACTION
    if lo < core:
        lo = min(core, hi)
        pygame.draw.circle(screen, _shade(entry, lo / disk_radius),
                           (cx, cy), max(1, int(lo)))
    # O limbo escurece rápido perto da borda: faixas geometricamente espaçadas.
    ratio = (hi / lo) ** (1.0 / CLOSE_BANDS)
    while lo < hi:
        nxt = min(hi, lo * ratio)
        pygame.draw.circle(
            screen, _shade(entry, (lo + nxt) / 2.0 / disk_radius),
            (cx, cy), max(1, int(nxt)), int(nxt - lo) + 1)
        lo = nxt


def _spikes(gx, gy, disk, flare):
    """Quatro riscos longos e quatro curtos, em diagonais, com queda própria."""
    arms = []
    diagonal = 0.7071
    for along, across, length, width in (
            (gx, gy, 4.6, 0.16), (-gx, -gy, 4.6, 0.16),
            (gy, gx, 4.2, 0.16), (-gy, -gx, 4.2, 0.16),
            ((gx + gy) * diagonal, (gx - gy) * diagonal, 2.4, 0.11),
            (-(gx + gy) * diagonal, -(gx - gy) * diagonal, 2.4, 0.11),
            ((gx - gy) * diagonal, (gx + gy) * diagonal, 2.2, 0.11),
            (-(gx - gy) * diagonal, -(gx + gy) * diagonal, 2.2, 0.11)):
        along_t = np.clip(along / (disk * length), 0.0, 1.0)
        across_t = np.abs(across) / (disk * width)
        arms.append((1.0 - along_t) ** 2.4
                    * np.exp(-across_t * across_t))
    return np.sum(arms, axis=0) * (0.42 * flare)


def _build(spec_name, disk):
    entry = _spec_entry(spec_name)
    _, _, body, corona, limb, reach, flare = entry
    seed = zlib.crc32(f"{spec_name}:{disk}".encode('utf-8')) & 0xFFFFFFFF
    phases = [(seed >> (8 * index)) & 0xFF for index in range(3)]
    radius = max(3, int(math.ceil(disk * reach)))
    edge = radius * 2 + 1
    span = np.arange(-radius, radius + 1, dtype=np.float32)
    gy, gx = np.meshgrid(span, span)
    distance = np.hypot(gx, gy) / float(disk)

    mu = np.sqrt(np.clip(1.0 - distance * distance, 0.0, 1.0))
    light = (1.0 - limb * (1.0 - mu)) * (1.0 + 0.35 * mu)
    # Grânulos só aparecem quando há pixels suficientes para mostrá-los.
    feature = max(3.0, disk * 0.34)
    amplitude = 0.055 * min(1.0, disk / 9.0)
    light = light * (1.0 + amplitude * (
        np.sin(gx / feature + phases[0]) * np.cos(gy / feature + phases[1])
        + 0.6 * np.sin((gx + gy) / feature * 1.7 + phases[2])))
    light = np.where(distance <= 1.0, light, 0.0)

    halo = np.where(
        distance > 1.0,
        np.exp(-(distance - 1.0) * (5.0 / reach)) * flare, 0.0)
    glow = np.clip(halo + _spikes(gx, gy, disk, flare), 0.0, 1.0)
    # Disco opaco com a borda suavizada em ~1 pixel; fora, só o clarão.
    disk_mask = np.clip((1.0 + 0.5 / disk - distance) * disk, 0.0, 1.0)
    alpha = np.clip(disk_mask + glow, 0.0, 1.0)

    lum = np.clip(light / 1.35, 0.0, 1.0)
    hot = np.clip((light - 1.12) / 0.23, 0.0, 1.0)
    tint_mix = np.clip(2.0 - distance * distance, 0.0, 1.0)
    brightness = np.clip(lum + glow, 0.0, 1.0)
    channels = []
    for axis in range(3):
        tint = corona[axis] + (body[axis] - corona[axis]) * tint_mix
        surface = np.clip(tint * brightness, 0.0, 255.0)
        channels.append(
            (surface + (255.0 - surface) * hot) * alpha)
    pixels = np.dstack(
        [channel.astype(np.uint8) for channel in channels]
        + [(alpha * 255.0).astype(np.uint8)])
    return pygame.image.frombuffer(pixels.tobytes(), (edge, edge), 'RGBA')


def star_sprite(spec_name, disk):
    """Sprite premultiplicado de uma classe num degrau de tamanho."""
    key = (spec_name, disk)
    sprite = _sprite_cache.get(key)
    if sprite is None:
        _sprite_cache[key] = _build(spec_name, disk).convert_alpha()
    return _sprite_cache[key]


def _scaled_size(edge, disk_radius, step):
    """Largura do blit ampliado: o pedido, arredondado para baixo na escada.

    Arredondar para baixo nunca faz o disco vazar para a órbita mais interna.
    """
    wanted = edge * disk_radius / float(step)
    if wanted <= edge:
        return edge
    bucket = int(math.log(wanted / edge) / math.log(SCALED_RATIO_STEP))
    size = round(edge * SCALED_RATIO_STEP ** bucket)
    return max(edge, (size // 2) * 2 + 1)


def _scaled_sprite(spec_name, step, target):
    """Amplia o degrau até `target` px e guarda os poucos tamanhos usados."""
    global _scaled_pixels
    key = (spec_name, target)
    surface = _scaled_cache.get(key)
    if surface is not None:
        _scaled_cache.move_to_end(key)
        return surface
    source = star_sprite(spec_name, step)
    surface = pygame.transform.smoothscale(source, (target, target))
    _scaled_cache[key] = surface
    _scaled_pixels += target * target
    while _scaled_pixels > SCALED_BUDGET and len(_scaled_cache) > 1:
        _, dropped = _scaled_cache.popitem(last=False)
        _scaled_pixels -= dropped.get_width() ** 2
    return surface


def _fits_scaled(entry, disk_radius):
    return disk_radius * 2 * entry[5] <= MAX_SCALED_EDGE


def draw_star(screen, star, center, disk_radius):
    """Blit da estrela; corpo pintado em faixas quando ela passa do blit máximo."""
    spec = stellar_class(star)
    entry = _spec_entry(spec)
    if not _fits_scaled(entry, disk_radius):
        _draw_close_star(screen, entry, center, disk_radius)
        return
    step = _disk_step(disk_radius)
    sprite = star_sprite(spec, step)
    edge = sprite.get_width()
    if disk_radius > step:
        target = _scaled_size(edge, disk_radius, step)
        if target > edge:
            sprite = _scaled_sprite(spec, step, target)
            edge = target
    cx, cy = center
    screen.blit(sprite, (int(cx) - edge // 2, int(cy) - edge // 2),
                special_flags=pygame.BLEND_PREMULTIPLIED)
