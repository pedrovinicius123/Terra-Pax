"""Sonda das estrelas (limitada): folheto visual + custo por quadro.

Uso: timeout -s ABRT 300 venv/bin/python -u _star_probe.py

Carrega graphics/star_sprites.py direto do fonte (o .so compilado pode estar
velho) e:
  * grava /tmp/star_probe/sheet.png com cada classe espectral em vários raios;
  * mede o tempo de quadro do mapa com o sprite novo versus o círculo antigo.
"""
import importlib.util
import math
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import faulthandler
import random
import threading
import time

T0 = time.perf_counter()
faulthandler.enable(all_threads=True)
OUT = "/tmp/star_probe"
os.makedirs(OUT, exist_ok=True)


def el():
    return f"[{time.perf_counter() - T0:5.1f}s]"


import numpy as np
import pygame
import main as m
import ui.interface as U
from game_state import GameState
from graphics.generate_map import init_map
from controllers.ai import AIController
from controllers.player import PlayerController
from players.factions import Faction

spec_obj = importlib.util.spec_from_file_location(
    "star_sprites_src", os.path.join(os.getcwd(), "graphics/star_sprites.py"))
SS = importlib.util.module_from_spec(spec_obj)
spec_obj.loader.exec_module(SS)
if os.environ.get('STAR_EDGE'):
    SS.MAX_SCALED_EDGE = int(os.environ['STAR_EDGE'])
print(f"{el()} fonte testado: {SS.__file__} teto_blit={SS.MAX_SCALED_EDGE}",
      flush=True)

random.seed(13)
pygame.init()
screen = pygame.display.set_mode((1400, 820))

# ---- folheto visual -------------------------------------------------------
RADII = (2, 3, 5, 8, 12, 20, 34, 60, 110, 200, 400, 900)
CELL = (240, 180)
BACKGROUND = (8, 12, 26)
sheet = pygame.Surface((CELL[0] * len(RADII), CELL[1] * len(SS.SPECTRAL_CLASSES)))
sheet.fill(BACKGROUND)


class Mock:
    def __init__(self, name):
        self.name = name
        self.total_resources = 1e5


for row, entry in enumerate(SS.SPECTRAL_CLASSES):
    star = Mock(f"{entry[0]}-teste")
    for col, radius in enumerate(RADII):
        tile = pygame.Surface(CELL)
        tile.fill(BACKGROUND)
        SS.draw_star(tile, star, (CELL[0] // 2, CELL[1] // 2), radius)
        sheet.blit(tile, (CELL[0] * col, CELL[1] * row))
pygame.image.save(sheet, f"{OUT}/sheet.png")
print(f"{el()} sheet gravada ({len(RADII)} raios x "
      f"{len(SS.SPECTRAL_CLASSES)} classes)", flush=True)

# ---- comparação de quadro -------------------------------------------------
gmap, stars = init_map(*m.GALAXY_LAYOUTS["large"][:3])
factions = []
used = set()
agg = {}
for name, ftype, is_human, color, aggression, desc in m.FACTION_DEFS:
    home = m.pick_home_planet(stars, ftype, used)
    if not home:
        continue
    star, planet = home
    used.add(planet.name)
    idx = next(i for i, d in enumerate(m.FACTION_DEFS) if d[0] == name)
    adv, dis = m.FACTION_TRAIT_ASSIGNMENTS[idx]
    f = Faction(name, ftype, home_planet=planet, home_star=star,
                is_human=is_human, color=color, description=desc,
                advantage=adv, disadvantage=dis)
    factions.append(f)
    agg[id(f)] = aggression
for f in factions:
    f.initialize_scout_manager(gmap, stars)
player = factions[0]
pc = PlayerController(player)
for f in factions:
    f.is_human = f is player
    f.controller = (pc if f is player
                    else AIController(f, aggression=min(.95, max(.1, agg[id(f)]))))
state = GameState(gmap, stars, factions, tick_interval=0.5)
state._recompute_control()

ui = U.GameUI(screen, state, pc)
ui.off_x, ui.off_y = player.home_star.position
STARBORDER = (255, 239, 190)


def legacy(screen, star, center, disk):
    sx, sy = center
    pygame.draw.circle(screen, U.C.STAR, (sx, sy), disk)
    pygame.draw.circle(screen, STARBORDER, (sx, sy), disk, 1)


def frames(n):
    timings = []
    for _ in range(n):
        for _event in pygame.event.get():
            pass
        t = time.perf_counter()
        ui.render()
        pygame.display.flip()
        timings.append((time.perf_counter() - t) * 1000)
    timings.sort()
    return (timings[n // 2], timings[int(n * .95)], timings[-1])


def measure(draw, zoom, shots=None, rounds=3):
    """Aquece as texturas pendentes e fica com a melhor das passadas."""
    U.draw_star = draw
    ui.zoom = zoom
    for _ in range(40):
        ui.render()
        pygame.display.flip()
    best = None
    for _ in range(rounds):
        result = frames(60)
        if best is None or result[0] < best[0]:
            best = result
    if shots is not None:
        ui.render()
        pygame.image.save(screen, shots)
    return best


state.start()
state.speed = 0.0          # congela o jogo: as passadas medem só o render
try:
    default_zooms = (("longe", 0.05), ("padrao", 0.45), ("sistema", 4.0),
                     ("fechado", 14.0), ("maximo", 40.0), ("absurdo", 120.0))
    wanted = os.environ.get('STAR_ZOOMS')
    if wanted:
        zooms = [(f"z{float(z):g}", float(z)) for z in wanted.split(',')]
    else:
        zooms = default_zooms
    tag = os.environ.get('STAR_TAG', '')
    for label, zoom in zooms:
        new_cost = measure(SS.draw_star, zoom, f"{OUT}/after{tag}_{label}.png")
        old_cost = measure(legacy, zoom)
        new_again = measure(SS.draw_star, zoom)
        new_cost = min(new_cost, new_again, key=lambda r: r[0])
        visible = sum(
            1 for s in state.stars
            if abs((s.position[0] - ui.off_x) * zoom) < ui.W
            and abs((s.position[1] - ui.off_y) * zoom) < ui.H)
        print(f"{el()} {label} zoom={zoom} na_tela={visible} "
              f"novo ms: med={new_cost[0]:.2f} p95={new_cost[1]:.2f} "
              f"max={new_cost[2]:.2f} | antigo ms: med={old_cost[0]:.2f} "
              f"p95={old_cost[1]:.2f} max={old_cost[2]:.2f}", flush=True)

    classes = {}
    for s in state.stars:
        key = SS.stellar_class(s)
        classes[key] = classes.get(key, 0) + 1
    exact = list(SS._sprite_cache.values())
    scaled = list(SS._scaled_cache.values())
    exact_px = sum(sp.get_width() * sp.get_height() for sp in exact)
    scaled_px = sum(sp.get_width() * sp.get_height() for sp in scaled)
    print(f"{el()} classes={classes} sprites_exatos={len(exact)} "
          f"{exact_px * 4 / 1e6:.1f} MB | ampliados={len(scaled)} "
          f"{scaled_px * 4 / 1e6:.1f} MB (teto "
          f"{SS.SCALED_BUDGET * 4 / 1e6:.1f} MB)", flush=True)
finally:
    state.stop()
    time.sleep(0.3)
    print(f"{el()} threads={threading.active_count()}", flush=True)
os._exit(0)
