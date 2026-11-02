import threading
import time
import math
import random
import networkx as nx

# Cadência dos laços de espera das threads de nave. As posições são
# interpoladas pelo getter abs_position a partir do relógio do jogo, então a
# thread só precisa perceber chegada/ordem nesta granularidade — não a cada
# quadro. Polling curto demais (20 ms) faz centenas de threads disputarem o
# GIL e travar a renderização, sobretudo em 5x.
SHIP_POLL = 0.12


def _nearest_star(stars, px, py):
    """Estrela mais próxima de (px, py) por distância ao quadrado.

    Equivale ao argmin da norma L2 (ordenação idêntica), mas sem os
    vetores NumPy de 2 elementos, que tinham custo desproporcional quando
    chamados contra todas as estrelas em cada decisão de nave.
    """
    best = None
    best_d = None
    for s in stars:
        dx = s.position[0] - px
        dy = s.position[1] - py
        d = dx * dx + dy * dy
        if best_d is None or d < best_d:
            best_d = d
            best = s
    return best


TRAVEL_SCALE = 6.0  # meses_de_jogo = dist / (speed * TRAVEL_SCALE)
EASE_RAMP = 0.22  # fração do trajeto gasta acelerando e desacelerando


def ease_travel(u, ramp=EASE_RAMP):
    """Deslocamento normalizado de um perfil acelera-cruza-desacelera.

    A velocidade é C1-contínua: senoidal nas pontas, constante no meio, de
    modo que a nave entra e sai do salto suavemente em vez de partir em
    velocidade máxima.
    """
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    ramp = min(max(ramp, 1e-6), 0.5)
    span = 1.0 - ramp
    if u < ramp:
        arc = 0.5 * (u - ramp / math.pi * math.sin(math.pi * u / ramp))
    elif u > 1.0 - ramp:
        tail = 1.0 - u
        arc = span - 0.5 * (tail - ramp / math.pi
                            * math.sin(math.pi * tail / ramp))
    else:
        arc = 0.5 * ramp + (u - ramp)
    return arc / span


def point_at_distance(points, cum, length, travelled):
    """Ponto e rumo (radianos) a `travelled` unidades da polilinha."""
    if length <= 0.0:
        return tuple(points[-1]), None
    travelled = min(max(travelled, 0.0), length)
    index = 1
    while index < len(cum) - 1 and cum[index] < travelled:
        index += 1
    origin = points[index - 1]
    target = points[index]
    span = cum[index] - cum[index - 1]
    if span <= 1e-9:
        return tuple(target), None
    ratio = (travelled - cum[index - 1]) / span
    x = origin[0] + (target[0] - origin[0]) * ratio
    y = origin[1] + (target[1] - origin[1]) * ratio
    heading = math.atan2(target[1] - origin[1], target[0] - origin[0])
    return (x, y), heading


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
        self._position = list(current_position.position)
        self._voyage = None
        # Reentrante: o getter de posição finaliza a viagem sob a mesma trava.
        self._motion_lock = threading.RLock()
        self._station_cache = {}
        self._pinned = None
        self.heading = -math.pi / 2
        self.order = None
        self._wake = threading.Event()

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

    # ---------- posição paramétrica no tempo ----------
    def _station_for(self, star):
        """Slot de formação ao redor da estrela: mantém a frota legível."""
        if star is None:
            return tuple(self._position)
        slot = self._station_cache.get(star.name)
        if slot is None:
            generator = random.Random(f"{self.ship_id}:{star.name}")
            angle = generator.uniform(0.0, math.tau)
            distance = 5.0 + generator.uniform(0.0, 20.0)
            slot = (star.position[0] + math.cos(angle) * distance,
                    star.position[1] + math.sin(angle) * distance)
            if len(self._station_cache) > 64:
                self._station_cache.clear()
            self._station_cache[star.name] = slot
        return slot

    @property
    def abs_position(self):
        with self._motion_lock:
            voyage = self._voyage
            if voyage is None:
                if self._pinned is not None:
                    return list(self._pinned)
                return list(self._station_for(self.current_position))
            progress = self._voyage_progress(voyage)
            if progress >= 1.0:
                self._complete_voyage(voyage)
                return list(self._position)
            travelled = ease_travel(progress) * voyage['length']
            point, heading = point_at_distance(
                voyage['points'], voyage['cum'], voyage['length'], travelled)
            if heading is not None:
                self.heading = heading
            return [point[0], point[1]]

    @abs_position.setter
    def abs_position(self, value):
        with self._motion_lock:
            self._voyage = None
            self._position = [float(value[0]), float(value[1])]
            self._pinned = list(self._position)

    @property
    def is_moving(self):
        return self._voyage is not None

    def _clock(self):
        state = getattr(self.faction, 'game_state', None)
        if state is None:
            return time.monotonic()
        smooth = getattr(state, 'smooth_time', None)
        if callable(smooth):
            return smooth()
        return state.time

    def _voyage_progress(self, voyage):
        duration = voyage['duration']
        if duration <= 0.0:
            return 1.0
        return min(1.0, max(0.0, (self._clock() - voyage['start']) / duration))

    def _complete_voyage(self, voyage):
        with self._motion_lock:
            if self._voyage is not voyage:
                return False
            self._voyage = None
            self._position = list(voyage['points'][-1])
            self.current_position = voyage['destinations'][-1]
            self._pinned = None
            return True

    def start_voyage(self, stars, activity=None, speed_cap=None):
        """Inicia um único trajeto contínuo por uma sequência de estrelas."""
        destinations = [star for star in stars if star is not None]
        if not destinations:
            return False
        with self._motion_lock:
            points = [tuple(self.abs_position)]
            for star in destinations[:-1]:
                points.append(tuple(star.position))
            points.append(self._station_for(destinations[-1]))
            cum = [0.0]
            for index in range(1, len(points)):
                cum.append(cum[-1] + math.dist(points[index - 1],
                                               points[index]))
            length = cum[-1]
            if length <= 1e-6:
                self._voyage = None
                self._position = list(points[-1])
                self._pinned = None
                self.current_position = destinations[-1]
                return True
            effective = self.speed
            if speed_cap is not None:
                effective = min(effective, max(0.1, float(speed_cap)))
            self._voyage = {
                'points': points, 'cum': cum, 'length': length,
                'destinations': destinations,
                'arrivals': cum[1:],
                'visited': set(),
                'start': self._clock(),
                'duration': length / (effective * TRAVEL_SCALE),
            }
        if activity:
            self.activity = activity
        return True

    def stop_voyage(self):
        """Congela a nave no ponto atual do trajeto."""
        position = list(self.abs_position)
        with self._motion_lock:
            self._voyage = None
            self._position = position
            self._pinned = position

    def wait_for_voyage(self, on_arrive=None):
        """Aguarda o trajeto, disparando `on_arrive` ao passar por cada estrela.

        Retorna False quando a nave morreu, parou ou recebeu uma ordem.
        """
        while self.running and self.alive:
            voyage = self._voyage
            if voyage is None:
                return True
            if self.order is not None:
                return False
            progress = self._voyage_progress(voyage)
            eased = ease_travel(progress) * voyage['length']
            if on_arrive is not None:
                for index, arrival in enumerate(voyage['arrivals']):
                    if index in voyage['visited'] or eased < arrival - 1e-6:
                        continue
                    voyage['visited'].add(index)
                    if on_arrive(voyage['destinations'][index]) is False:
                        return False
            if progress >= 1.0:
                self._complete_voyage(voyage)
                return True
            time.sleep(SHIP_POLL)
        return False

    def travel_path(self, stars, on_arrive=None, activity=None,
                    speed_cap=None):
        if not self.start_voyage(stars, activity, speed_cap):
            return self.running and self.alive
        return self.wait_for_voyage(on_arrive)

    # ---------- ordens manuais ----------
    def issue_order(self, kind, star=None, planet=None, speed_cap=None):
        if kind not in ('move', 'hold', 'clear'):
            return False
        if kind == 'move' and star is None:
            return False
        if kind == 'hold':
            self.stop_voyage()
        self.order = {'kind': kind, 'star': star, 'planet': planet,
                      'speed_cap': speed_cap}
        self._wake.set()
        return True

    def clear_order(self):
        self.order = None
        self._wake.set()

    def _handle_order(self):
        """Executa uma ordem pendente. True quando ela foi atendida."""
        order = self.order
        if order is None:
            return False
        kind = order['kind']
        if kind == 'clear':
            self.clear_order()
            return False
        # A ordem passa a ser a ação corrente: libera o trajeto para reagir
        # a uma ordem seguinte.
        self.order = None
        if kind == 'hold':
            self.activity = "aguardando ordens"
            while self.running and self.alive and self.order is None:
                time.sleep(SHIP_POLL)
            self._wake.set()
            return True
        star = order['star']
        self.activity = f"-> {star.name} (ordem)"
        path = self.find_path_to_star(star) or [star]
        self.travel_path(path, speed_cap=order.get('speed_cap'))
        self._wake.set()
        return True

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
        t0 = self._clock()
        if getattr(self.faction, 'game_state', None) is None:
            time.sleep(seconds)
            return
        while self.running and self.alive and self.order is None:
            if self._clock() - t0 >= seconds:
                return
            time.sleep(SHIP_POLL)

    # ---------- movimento controlado pelo relógio global ----------
    def move_to_star(self, from_star, to_star):
        if from_star is None or to_star is None:
            return
        if self.current_position is to_star and self._voyage is None:
            return
        self.activity = f"-> {to_star.name}"
        self.travel_path([to_star])
        if not self.running or not self.alive:
            return
        self.current_position = to_star
        self.activity = "idle"

    def find_path_to_star(self, target_star):
        try:
            pos = self.abs_position
            current_star = _nearest_star(self.total_stars, pos[0], pos[1])
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
            if self._handle_order():
                continue
            target = self._pick_unexplored()
            if target is None:
                self.activity = "sem alvos"
                self._wait_game_time(3)
                continue
            path = self.find_path_to_star(target) or [target]
            self.activity = f"-> {target.name}"
            if not self.travel_path(path, on_arrive=self._scan):
                if not self.running or not self.alive:
                    return
                continue
            self.activity = "idle"

    def _scan(self, star):
        if star.name in self.faction.explored_stars:
            return True
        self.activity = f"explorando {star.name}"
        self._wait_game_time(self.scan_time)
        self.faction.explored_stars.add(star.name)
        return self.running and self.alive and self.order is None

    def _pick_unexplored(self):
        remaining = [s for s in self.total_stars
                     if s.name not in self.faction.explored_stars]
        if not remaining:
            return None
        pos = self.abs_position
        return _nearest_star(remaining, pos[0], pos[1])


class ColonyShip(Ship):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.target_star = None
        self.target_planet = None

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
            if self._handle_order():
                continue
            if not self._wake.wait(0.5):
                continue
            self._wake.clear()
            if not self.running or not self.alive:
                return

            tgt_star = self.target_star
            tgt_planet = self.target_planet
            if tgt_star is None or tgt_planet is None:
                continue

            if tgt_planet.is_colonized:
                self._release_target()
                return

            path = self.find_path_to_star(tgt_star) or [tgt_star]
            if not self.travel_path(path, activity=f"-> {tgt_planet.name}"):
                if not self.running or not self.alive:
                    return
                self._wake.set()
                continue

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
    RESOURCE_TYPES = (
        'Food', 'Minerals', 'Energy', 'Electronics', 'Chemicals', 'Alloys',
    )

    def __init__(self, resource='Minerals', **kwargs):
        super().__init__(**kwargs)
        self.resource = resource
        self.load = 0.0
        self.population_cargo = 0.0
        self.mission_kind = None
        self.source = None
        self.destination = None
        self._prefer_population = True

    def plan_population_transfer(self):
        best_route = None
        best_score = 0.0
        for source in self.faction.colonies.values():
            if (not source.is_colonized
                    or source.faction is not self.faction
                    or not self._route_is_reachable(source, source)):
                continue
            source_population = float(source.population)
            source_capacity = source.capacity_info()['max_pop']
            source_ratio = source_population / max(1.0, source_capacity)
            source_available = max(
                0.0, source_population - max(100.0, source_population * 0.1))
            if source_population < 250 or source_available < 50:
                continue

            for destination in self.faction.colonies.values():
                if destination is source:
                    continue
                if (not destination.is_colonized
                        or destination.faction is not self.faction):
                    continue
                if not self._route_is_reachable(source, destination):
                    continue
                destination_capacity = (
                    destination.capacity_info()['max_pop'])
                destination_population = float(destination.population)
                destination_ratio = (
                    destination_population / max(1.0, destination_capacity))
                if source_ratio <= destination_ratio:
                    continue

                room = max(0.0, destination_capacity - destination_population)
                amount = min(
                    self.cargo,
                    source_available,
                    room,
                    (source_population - destination_population) * 0.5,
                )
                if amount < 50:
                    continue
                score = amount * (source_ratio - destination_ratio)
                if score > best_score:
                    best_score = score
                    best_route = source, destination, amount
        return best_route

    def _plan_resource_transfer(self):
        best_route = None
        best_score = 0.0
        logistics = self.faction.logistics_manager
        for resource in self.RESOURCE_TYPES:
            route = logistics.plan_transport_trip(resource, self.cargo)
            if route is None:
                continue
            source, destination, amount = route
            if not self._route_is_reachable(source, destination):
                continue
            capacity = destination.storage_capacity.get(resource, 0.0)
            stored = destination.planet_resources.get(resource, 0.0)
            deficit = max(0.0, 1.0 - stored / max(1.0, capacity))
            priority = 1.5 if resource == 'Food' else 1.0
            score = amount * deficit * priority
            if score > best_score:
                best_score = score
                best_route = resource, source, destination, amount
        return best_route

    def _route_is_reachable(self, source, destination):
        return (
            nx.has_path(
                self.map_G, self.current_position.name,
                source.parent_star.name)
            and nx.has_path(
                self.map_G, source.parent_star.name,
                destination.parent_star.name)
        )

    def _load_population(self, source, amount):
        with source.lock:
            if (source.faction is not self.faction
                    or not source.is_colonized):
                return False
            available = max(
                0.0, source.population
                - max(100.0, source.population * 0.1))
            loaded = min(amount, available, self.cargo)
            if loaded <= 0:
                return False
            source.population -= loaded
            self.population_cargo = loaded
            return True

    def _deliver_population(self, destination):
        with destination.lock:
            if (destination.faction is not self.faction
                    or not destination.is_colonized):
                return 0.0
            capacity = destination.capacity_info()['max_pop']
            room = max(0.0, capacity - destination.population)
            delivered = min(self.population_cargo, room)
            destination.population += delivered
            self.population_cargo -= delivered
            return delivered

    def _find_population_destination(self, origin):
        destinations = []
        for planet in self.faction.colonies.values():
            if (planet is origin or not planet.is_colonized
                    or planet.faction is not self.faction):
                continue
            capacity = planet.capacity_info()['max_pop']
            population = float(planet.population)
            room = capacity - population
            if room <= 0:
                continue
            destinations.append(
                (population / max(1.0, capacity), planet))
        if not destinations:
            return None
        return min(destinations, key=lambda item: item[0])[1]

    def _travel_to_planet(self, planet):
        path = self.find_path_to_star(planet.parent_star)
        if path is None:
            return False
        return self.travel_path(path)

    def _clear_mission(self, completed=False):
        self.load = 0.0
        self.population_cargo = 0.0
        self.mission_kind = None
        self.source = None
        self.destination = None
        if completed:
            self._prefer_population = not self._prefer_population

    def tick(self):
        while self.running and self.alive:
            if self._handle_order():
                continue
            logistics = self.faction.logistics_manager
            has_cargo = (
                self.population_cargo > 1e-6
                if self.mission_kind == 'population'
                else self.load > 1e-6
            )
            if not has_cargo:
                migration_route = self.plan_population_transfer()
                resource_route = self._plan_resource_transfer()
                if self._prefer_population:
                    mission = (
                        ('population', migration_route)
                        if migration_route is not None
                        else ('resource', resource_route)
                    )
                else:
                    mission = (
                        ('resource', resource_route)
                        if resource_route is not None
                        else ('population', migration_route)
                    )
                mission_kind, route = mission
                if route is None:
                    self._wait_game_time(3)
                    continue

                if mission_kind == 'population':
                    source, destination, amount = route
                    self.mission_kind = 'population'
                else:
                    self.resource, source, destination, amount = route
                    self.mission_kind = 'resource'
                self.source = source
                self.destination = destination
                self.activity = (
                    "indo buscar migrantes"
                    if self.mission_kind == 'population'
                    else f"indo buscar {self.resource}"
                )
                if not self._travel_to_planet(source):
                    if not self.running or not self.alive:
                        return
                    self._clear_mission()
                    self._wait_game_time(3)
                    continue
                loaded = (
                    self._load_population(source, amount)
                    if self.mission_kind == 'population'
                    else logistics.load_cargo(self, source, amount)
                )
                if not loaded:
                    self._clear_mission()
                    self._wait_game_time(1)
                    continue

            destination = self.destination
            if destination is None:
                if self.mission_kind == 'population':
                    destination = self._find_population_destination(
                        self.source)
                else:
                    destination = logistics.plan_delivery(
                        self.resource, self.load, origin=self.source)
                if destination is None:
                    self._wait_game_time(3)
                    continue
                self.destination = destination

            self.activity = (
                "migrando população"
                if self.mission_kind == 'population'
                else f"transportando {self.resource}"
            )
            if not self._travel_to_planet(destination):
                if not self.running or not self.alive:
                    return
                self.destination = None
                self._wait_game_time(3)
                continue
            delivered = (
                self._deliver_population(destination)
                if self.mission_kind == 'population'
                else logistics.deliver_cargo(self, destination)
            )
            if delivered <= 0:
                self.destination = None
                self._wait_game_time(1)
                continue

            remaining = (
                self.population_cargo
                if self.mission_kind == 'population'
                else self.load
            )
            self.activity = (
                f"migração de {delivered:.0f} habitantes concluída"
                if self.mission_kind == 'population'
                else f"entregue {delivered:.0f} {self.resource}"
            )
            if remaining <= 1e-6:
                self._clear_mission(completed=True)
            else:
                self.destination = None
            self._wait_game_time(1)


class Warship(Ship):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def tick(self):
        while self.running and self.alive:
            if self.shields < self.max_shields:
                self.shields = min(self.max_shields,
                                   self.shields + self.max_shields * 0.02)
            if self._handle_order():
                continue
            target = self._pick_enemy_star()
            if target is not None:
                path = self.find_path_to_star(target) or [target]
                if not self.travel_path(path, activity=f"-> {target.name}"):
                    if not self.running or not self.alive:
                        return
                    continue
                self._wait_game_time(2)
                continue
            patrol = list(self.faction.controlled_stars.values())
            if patrol:
                dest = random.choice(patrol)
                if dest is not self.current_position:
                    path = self.find_path_to_star(dest)
                    if path and not self.travel_path(
                            path, activity=f"patrulhando {dest.name}"):
                        if not self.running or not self.alive:
                            return
                        continue
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
        pos = self.abs_position
        return _nearest_star(enemy_stars, pos[0], pos[1])
            