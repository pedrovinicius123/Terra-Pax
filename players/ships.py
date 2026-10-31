import threading
import time
import math
import random
import numpy as np
import networkx as nx


TRAVEL_SCALE = 6.0  # segundos_de_jogo = dist / (speed * TRAVEL_SCALE)


class Ship(threading.Thread):
    def __init__(self, ship_id, faction, map_G, current_position, total_stars,
                 speed=5.0, hull=20.0, shields=0.0, weapons=0.0, cargo=0.0,
                 design_key="scout", **kwargs):
        super().__init__()
        self.daemon = True
        self.ship_id = ship_id
        self.design_key = design_key
        self.faction = faction
        self.map_G = map_G
        self.current_position = current_position
        self.total_stars = total_stars
        self.stars_dict = {s.name: s for s in total_stars}
        self.abs_position = list(current_position.position)

        self.speed = max(0.1, speed)
        self.max_hull = float(hull)
        self.hull = float(hull)
        self.max_shields = float(shields)
        self.shields = float(shields)
        self.weapons = float(weapons)
        self.cargo = float(cargo)

        self.alive = True
        self.running = False
        self.activity = "idle"

    def run(self):
        self.running = True
        try:
            self.tick()
        except Exception as e:
            print(f"[{self.ship_id}] erro: {e}")

    def tick(self):
        while self.running and self.alive:
            time.sleep(1)

    # ---------- utilidades de tempo-de-jogo ----------
    def _wait_game_time(self, seconds):
        state = getattr(self.faction, 'game_state', None)
        if state is None:
            time.sleep(seconds)
            return
        t0 = state.time
        while state.time - t0 < seconds:
            if not self.running or not self.alive:
                return
            time.sleep(0.02)

    # ---------- movimento controlado pelo relógio global ----------
    def move_to_star(self, from_star, to_star):
        if from_star is None or to_star is None or from_star is to_star:
            return
        try:
            dist = self.map_G[from_star.name][to_star.name]['weight']
        except KeyError:
            self.current_position = to_star
            self.abs_position = list(to_star.position)
            return

        game_travel_time = dist / (self.speed * TRAVEL_SCALE)
        steps = max(10, min(2000, int(game_travel_time * 30)))
        xs = np.linspace(from_star.position[0], to_star.position[0], steps)
        ys = np.linspace(from_star.position[1], to_star.position[1], steps)

        state = getattr(self.faction, 'game_state', None)
        self.activity = f"-> {to_star.name}"

        if state is None:
            for x, y in zip(xs, ys):
                if not self.running or not self.alive:
                    break
                self.abs_position[0] = x
                self.abs_position[1] = y
                time.sleep(0.02)
        else:
            t0 = state.time
            step_time = game_travel_time / steps
            for i, (x, y) in enumerate(zip(xs, ys)):
                if not self.running or not self.alive:
                    return
                target_t = t0 + i * step_time
                while state.time < target_t:
                    if not self.running or not self.alive:
                        return
                    time.sleep(0.02)
                self.abs_position[0] = x
                self.abs_position[1] = y

        self.current_position = to_star
        self.activity = "idle"

    def find_path_to_star(self, target_star):
        try:
            pos = np.array(self.abs_position)
            dists = [np.linalg.norm(pos - np.array(s.position))
                     for s in self.total_stars]
            current_star = self.total_stars[int(np.argmin(dists))]
            if current_star is target_star:
                return [target_star]
            path = nx.shortest_path(self.map_G, current_star.name,
                                    target_star.name, weight='weight')
            return [self.stars_dict[n] for n in path[1:]]
        except (nx.NetworkXNoPath, KeyError):
            return None

    def take_damage(self, dmg):
        absorbed = min(self.shields, dmg)
        self.shields -= absorbed
        self.hull -= (dmg - absorbed)
        if self.hull <= 0:
            self.destroy()

    def destroy(self):
        self.alive = False
        self.running = False
        if self.faction and self.ship_id in self.faction.ships:
            del self.faction.ships[self.ship_id]
        print(f"[{self.ship_id}] destruída")

    def stop(self):
        self.running = False


class Scout(Ship):
    def __init__(self, scan_time=1.0, **kwargs):
        super().__init__(**kwargs)
        self.scan_time = float(scan_time)

    def tick(self):
        if self.faction.scout_manager:
            self.faction.scout_manager.register_scout(self.ship_id, self)

        while self.running and self.alive:
            target = self._pick_unexplored()
            if target is None:
                self.activity = "sem alvos"
                self._wait_game_time(3)
                continue
            path = self.find_path_to_star(target) or [target]
            for star in path:
                if not self.running or not self.alive:
                    return
                self.move_to_star(self.current_position, star)
                if star.name not in self.faction.explored_stars:
                    self.activity = f"explorando {star.name}"
                    self._wait_game_time(self.scan_time)
                    self.faction.explored_stars.add(star.name)

    def _pick_unexplored(self):
        remaining = [s for s in self.total_stars
                     if s.name not in self.faction.explored_stars]
        if not remaining:
            return None
        pos = np.array(self.abs_position)
        return min(remaining,
                   key=lambda s: np.linalg.norm(pos - np.array(s.position)))


class ColonyShip(Ship):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.target_star = None
        self.target_planet = None
        self._wake = threading.Event()

    def assign_target(self, star, planet):
        if self.target_planet is not None:
            return False
        if planet.is_colonized:
            return False
        self.target_star = star
        self.target_planet = planet
        self.activity = f"-> {planet.name}"
        self._wake.set()
        return True

    def _release_target(self):
        if self.target_planet is not None and self.faction is not None:
            self.faction.reserved_targets.discard(self.target_planet.name)
        self.target_star = None
        self.target_planet = None
        self._wake.clear()

    def destroy(self):
        if self.target_planet is not None and self.faction is not None:
            self.faction.reserved_targets.discard(self.target_planet.name)
            self.target_planet = None
            self.target_star = None
        super().destroy()

    def tick(self):
        while self.running and self.alive:
            if not self._wake.wait(0.5):
                continue
            if not self.running or not self.alive:
                return

            tgt_star = self.target_star
            tgt_planet = self.target_planet
            if tgt_star is None or tgt_planet is None:
                self._wake.clear()
                continue

            if tgt_planet.is_colonized:
                self._release_target()
                return

            path = self.find_path_to_star(tgt_star) or [tgt_star]
            for star in path:
                if not self.running or not self.alive:
                    return
                self.move_to_star(self.current_position, star)

            if not self.running or not self.alive:
                return

            if tgt_planet.is_colonized:
                self._release_target()
                self.activity = "sem alvo"
                continue

            if self.faction.establish_colony(tgt_star, tgt_planet):
                self.destroy()
                return
            


class Transport(Ship):
    def __init__(self, resource='Minerals', **kwargs):
        super().__init__(**kwargs)
        self.resource = resource
        self.load = 0.0

    def tick(self):
        while self.running and self.alive:
            colonies = [p for p in self.faction.colonies.values()
                        if p is not self.faction.home_planet]
            if not colonies:
                self._wait_game_time(3)
                continue

            if self.load <= 0:
                source = max(self.faction.colonies.values(),
                             key=lambda p: p.planet_resources.get(self.resource, 0))
                if source.planet_resources.get(self.resource, 0) < self.cargo * 0.5:
                    self._wait_game_time(3)
                    continue
                path = self.find_path_to_star(source.parent_star)
                if not path:
                    self._wait_game_time(3)
                    continue
                for star in path:
                    if not self.running or not self.alive:
                        return
                    self.move_to_star(self.current_position, star)
                take = min(self.cargo, source.planet_resources.get(self.resource, 0))
                source.planet_resources[self.resource] -= take
                self.load = take
                self.activity = f"carregando {self.resource}"
            else:
                dest = min(self.faction.colonies.values(),
                           key=lambda p: p.planet_resources.get(self.resource, 0))
                path = self.find_path_to_star(dest.parent_star)
                if not path:
                    self._wait_game_time(3)
                    continue
                for star in path:
                    if not self.running or not self.alive:
                        return
                    self.move_to_star(self.current_position, star)
                dest.planet_resources[self.resource] = (
                    dest.planet_resources.get(self.resource, 0) + self.load)
                self.load = 0.0
                self.activity = "idle"
            self._wait_game_time(1)


class Warship(Ship):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def tick(self):
        while self.running and self.alive:
            if self.shields < self.max_shields:
                self.shields = min(self.max_shields,
                                   self.shields + self.max_shields * 0.02)
            target = self._pick_enemy_star()
            if target is not None:
                path = self.find_path_to_star(target) or [target]
                for star in path:
                    if not self.running or not self.alive:
                        return
                    self.move_to_star(self.current_position, star)
                self._wait_game_time(2)
                continue
            patrol = list(self.faction.controlled_stars.values())
            if patrol:
                dest = random.choice(patrol)
                if dest is not self.current_position:
                    path = self.find_path_to_star(dest)
                    if path:
                        for star in path:
                            if not self.running or not self.alive:
                                return
                            self.move_to_star(self.current_position, star)
            self._wait_game_time(2)

    def _pick_enemy_star(self):
        try:
            from players.factions import DiplomacyStatus
        except Exception:
            return None
        gs = getattr(self.faction, 'game_state', None)
        if gs is None:
            return None
        enemy_names = [n for n, st in self.faction.diplomacy.items()
                       if st == DiplomacyStatus.WAR]
        if not enemy_names:
            return None
        enemy_stars = []
        for f in gs.factions:
            if f is self.faction or f.eliminated:
                continue
            if f.name in enemy_names:
                enemy_stars.extend(f.controlled_stars.values())
        if not enemy_stars:
            return None
        pos = np.array(self.abs_position)
        return min(enemy_stars,
                   key=lambda s: np.linalg.norm(pos - np.array(s.position)))
            