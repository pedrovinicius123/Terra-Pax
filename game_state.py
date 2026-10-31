import threading
import time
import math
from queue import Empty

from players.ships import Warship


class GameState:
    def __init__(self, map_G, stars, factions, tick_interval=0.5):
        self.map_G = map_G
        self.stars = stars
        self.factions = factions
        self.stars_by_name = {s.name: s for s in stars}
        self.time = 0.0
        self.speed = 1.0
        self.paused = False
        self.running = False
        self.tick_interval = tick_interval
        self.lock = threading.RLock()
        self._thread = None
        self.event_log = []
        for f in factions:
            f.game_state = self

    def log_event(self, msg):
        self.event_log.append((self.time, msg))
        print(f"[{self.time:6.1f}s] {msg}")

    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self.running:
            if not self.paused:
                self.tick(self.tick_interval * self.speed)
            time.sleep(self.tick_interval)

    def tick(self, dt):
        with self.lock:
            self.time += dt
            for star in self.stars:
                for planet in star.planets:
                    if planet.is_colonized and planet.faction:
                        try:
                            planet.develop()
                        except Exception as e:
                            print(f"[planet {planet.name}] {e}")
            for f in self.factions:
                if f.eliminated:
                    continue
                try:
                    f._recompute_resources()
                    f.process_research(dt)
                except Exception as e:
                    print(f"[faction {f.name}] {e}")
            self._resolve_combat(dt)
            self._resolve_sieges(dt)
            for f in self.factions:
                if f.eliminated or f.controller is None:
                    continue
                try:
                    f.controller.update(self, dt)
                except Exception as e:
                    print(f"[ctrl {f.name}] {e}")

    def _resolve_combat(self, dt):
        warships = []
        for f in self.factions:
            if f.eliminated:
                continue
            for s in list(f.ships.values()):
                if isinstance(s, Warship) and s.alive:
                    warships.append(s)
        for i, s1 in enumerate(warships):
            if not s1.alive:
                continue
            for s2 in warships[i + 1:]:
                if not s2.alive or s1.faction is s2.faction:
                    continue
                if s2.faction.name in s1.faction.allies:
                    continue
                if math.dist(s1.abs_position, s2.abs_position) > 100:
                    continue
                s1.take_damage(s2.weapons * dt)
                s2.take_damage(s1.weapons * dt)
                if not s1.alive or not s2.alive:
                    break

    def _resolve_sieges(self, dt):
        try:
            from players.factions import DiplomacyStatus
        except Exception:
            return
        siege_range = 200
        for f in self.factions:
            if f.eliminated:
                continue
            enemy_names = {n for n, st in f.diplomacy.items()
                           if st == DiplomacyStatus.WAR}
            if not enemy_names:
                continue
            warships = [s for s in f.ships.values()
                        if isinstance(s, Warship) and s.alive]
            if not warships:
                continue
            damage_by_planet = {}
            for ws in warships:
                for star in self.stars:
                    if math.dist(ws.abs_position, star.position) > siege_range:
                        continue
                    found = False
                    for planet in star.planets:
                        if not planet.is_colonized:
                            continue
                        if (planet.faction is None or planet.faction is f
                                or planet.faction.eliminated):
                            continue
                        if planet.faction.name not in enemy_names:
                            continue
                        dmg = ws.weapons * dt * 0.5
                        damage_by_planet[planet] = (
                            damage_by_planet.get(planet, 0.0) + dmg)
                        found = True
                        break
                    if found:
                        break
            for planet, dmg in damage_by_planet.items():
                planet.defense = max(0.0, planet.defense - dmg)
                if planet.defense <= 0:
                    self._capture_planet(planet, f)

    def _capture_planet(self, planet, attacker):
        defender = planet.faction
        if defender is None or defender is attacker:
            return
        # Transfere
        planet.faction = attacker
        planet.population *= 0.5
        planet.developement *= 0.7
        planet.defense = planet.max_defense * 0.3
        # Limpa fila de construção
        while True:
            try:
                planet.const_queue.get_nowait()
            except Empty:
                break
        # Remove do defensor, adiciona ao atacante
        defender.colonies.pop(planet.name, None)
        attacker.colonies[planet.name] = planet
        attacker.stats['planets_captured'] += 1
        # Home planet caiu?
        if defender.home_planet is planet and defender.colonies:
            defender.home_planet = next(iter(defender.colonies.values()))
        # Explorado
        attacker.explored_stars.add(planet.parent_star.name)
        # Elimina defensor se ficou sem colônias
        if not defender.colonies:
            defender.eliminated = True
            for s in list(defender.ships.values()):
                s.alive = False
                s.running = False
        # Recalcula controle de sistemas e recursos
        self._recompute_control()
        attacker._recompute_resources()
        defender._recompute_resources()
        self.log_event(f"{attacker.name} conquistou {planet.name} de "
                       f"{defender.name}")
        if defender.eliminated:
            self.log_event(f"{defender.name} foi eliminada!")

    def _recompute_control(self):
        for f in self.factions:
            f.controlled_stars = {}
        for star in self.stars:
            for planet in star.planets:
                if planet.is_colonized and planet.faction:
                    planet.faction.controlled_stars[star.name] = star

    def stop(self):
        self.running = False
        