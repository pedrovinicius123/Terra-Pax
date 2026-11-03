"""Sonda de economia (limitada): ~60 anos de simulação sem render.

Uso: timeout -s ABRT 300 venv/bin/python -u _economy_probe.py

Mede o ciclo demanda -> fila de obras -> transporte multi-recurso -> obra
paga e iniciada, e o aviso de sobrecarga da frota. Só o LogisticsManager é
Python puro (os módulos compilados não aceitam monkeypatch), então as obras
são medidas por estado observável, não por hooks.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import faulthandler
import random
import time

T0 = time.perf_counter()
faulthandler.enable(all_threads=True)


def el():
    return f"[{time.perf_counter() - T0:5.1f}s]"


import pygame
import main as m
from game_state import GameState
from graphics.generate_map import init_map
from controllers.ai import AIController
from controllers.player import PlayerController
from players.factions import Faction
from logistics.modules.logistics_manager import LogisticsManager

random.seed(13)
pygame.init()

gmap, stars = init_map(*m.GALAXY_LAYOUTS["medium"][:3])
factions_data = []
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
    factions_data.append(f)
    agg[id(f)] = aggression
for f in factions_data:
    f.initialize_scout_manager(gmap, stars)
player = factions_data[0]
pc = PlayerController(player)
for f in factions_data:
    f.is_human = f is player
    f.controller = (pc if f is player
                    else AIController(f, aggression=min(.95, max(.1, agg[id(f)]))))
state = GameState(gmap, stars, factions_data, tick_interval=0.5)

stats = {'runs': 0, 'legs': [], 'loaded': 0.0, 'delivered': 0.0, 'flips': 0}

_orig_plan = LogisticsManager.plan_freight_runs
_orig_load = LogisticsManager.load_cargo
_orig_deliver = LogisticsManager.deliver_cargo
_orig_notify = LogisticsManager._notify_overload


def plan_freight_runs(self, capacity, count=1, origin=None, reachable=None):
    runs = _orig_plan(self, capacity, count, origin, reachable)
    for run in runs:
        stats['runs'] += 1
        stats['legs'].append(len(run['legs']))
    return runs


def load_cargo(self, ship, source, legs):
    got = _orig_load(self, ship, source, legs)
    stats['loaded'] += got
    return got


def deliver_cargo(self, ship, destination):
    got = _orig_deliver(self, ship, destination)
    stats['delivered'] += got
    return got


def notify_overload(self):
    before = self._announced_overload
    _orig_notify(self)
    if before != self._announced_overload:
        stats['flips'] += 1


LogisticsManager.plan_freight_runs = plan_freight_runs
LogisticsManager.load_cargo = load_cargo
LogisticsManager.deliver_cargo = deliver_cargo
LogisticsManager._notify_overload = notify_overload


def snapshot():
    rows = []
    for f in factions_data:
        colonies = list(f.colonies.values())
        transports = [s for s in f.ships.values()
                      if getattr(s, 'alive', False)
                      and getattr(s, 'design_key', None) == 'transport']
        loaded = sum(s.used_cargo for s in transports)
        rows.append(
            f"{f.name[:4]} col={len(colonies)} "
            f"fila={sum(len(p.build_queue) for p in colonies)} "
            f"agrav={sum(1 for p in colonies if p.awaiting_resources())} "
            f"nav={len(transports)}/{loaded:.0f} "
            f"trab={sum(p.supply_strain for p in colonies):.2f} "
            f"pop={sum(p.population for p in colonies):.0f} "
            f"hab={sum(p.habitats for p in colonies)}")
    return ' | '.join(rows)


frames = 0
progress = 0.0
HORIZON = float(os.environ.get('PROBE_MONTHS', 3600.0))
STEP = int(os.environ.get('PROBE_EVERY', 25))
try:
    while frames < HORIZON / 5.0:
        for _event in pygame.event.get():
            pass
        state.tick(state.tick_interval * 10.0)
        progress = state.time
        frames += 1
        if frames % STEP == 0:
            print(f"{el()} t={progress:6.1f}m {snapshot()}", flush=True)
        if progress > HORIZON:
            break
finally:
    print(f"{el()} fim sim={progress:.1f} meses frames={frames}", flush=True)

multi = sum(1 for n in stats['legs'] if n > 1)
avg = sum(stats['legs']) / max(1, len(stats['legs']))
print(f"{el()} viagens={stats['runs']} multi_recurso={multi} pernas_media={avg:.2f} "
      f"carregado={stats['loaded']:.0f} entregue={stats['delivered']:.0f} "
      f"flips_sobrecarga={stats['flips']}", flush=True)

for f in factions_data:
    manager = f.logistics_manager
    manager._sync_nodes()
    manager._refresh_estimates()
    status = manager.overload_status()
    print(f"{el()} {f.name[:12]:<12} sobrecarga={status.get('overloaded')} "
          f"razao={status.get('deficit_ratio', 0):.2f} "
          f"faltam={status.get('missing_transports', 0)} "
          f"esperando={status.get('awaiting_colonies', 0)}", flush=True)

audit = factions_data[1]
manager = audit.logistics_manager
rows = {}
for planet in audit.colonies.values():
    yearly = planet.resource_output()
    for resource, amount in planet.consumption().items():
        cell = rows.setdefault(resource, [0.0, 0.0, 0.0, 0.0])
        cell[0] += amount
        cell[1] += yearly.get(resource, 0.0)
    for resource, amount in planet.import_need().items():
        rows.setdefault(resource, [0.0, 0.0, 0.0, 0.0])[2] += amount
    for resource, amount in planet.blocked_need().items():
        rows.setdefault(resource, [0.0, 0.0, 0.0, 0.0])[3] += amount
print(f"{el()} auditoria {audit.name}: recurso consome/produz/fila_parada "
      f"({len(audit.colonies)} colonias)", flush=True)
for resource, cell in sorted(rows.items(), key=lambda item: -item[1][2]):
    print(f"    {resource:<12} {cell[0]:10.0f} {cell[1]:10.0f} "
          f"necessidade={cell[2]:9.0f} obras_paradas={cell[3]:9.0f}", flush=True)
os._exit(0)
