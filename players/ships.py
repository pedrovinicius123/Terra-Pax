import threading
import time
import math
import random
import networkx as nx


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


class Ship:
    """Nave conduzida por uma corrotina cooperativa, avançada pelo jogo.

    Antes cada nave era uma `threading.Thread` com laço de polling; centenas
    delas disputavam o GIL e travavam a renderização (pior em 5x). Agora a IA
    é um gerador (`ai`) e o `GameState.tick` chama `step()` uma vez por quadro
    de simulação. O `abs_position` segue paramétrico no relógio do jogo, e a
    trava de movimento continua protegendo a leitura do quadro de render.
    """

    def __init__(self, ship_id, faction, map_G, current_position, total_stars,
                 speed=5.0, hull=20.0, shields=0.0, weapons=0.0, cargo=0.0,
                 design_key="scout", **kwargs):
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
        self._ai = None

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
        voyage = self._voyage
        return voyage is not None and self._voyage_progress(voyage) < 1.0

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
            effective = self.speed
            if speed_cap is not None:
                effective = min(effective, max(0.1, float(speed_cap)))
            # Uma viagem de comprimento zero também é registrada (duração 0):
            # é assim que a estrela onde a nave já está recebe a chegada e a
            # exploração/colonização corresponde.
            self._voyage = {
                'points': points, 'cum': cum, 'length': length,
                'destinations': destinations,
                'arrivals': cum[1:],
                'visited': set(),
                'start': self._clock(),
                'duration': length / max(1e-9, effective * TRAVEL_SCALE),
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
        """Corrotina: aguarda o trajeto, disparando `on_arrive` a cada estrela.

        Cede o controle (`yield`) a cada quadro de simulação até o voo
        terminar. `on_arrive` é ela própria uma corrotina que devolve False
        para abortar. Retorna False quando a nave morreu, parou ou recebeu
        ordem.
        """
        while self.running and self.alive:
            voyage = self._voyage
            if voyage is None:
                # Cede um quadro: chamar esta corrotina sem viagem não pode
                # retornar instantaneamente, senão o laço de IA gira sem pausa.
                yield
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
                    if (yield from on_arrive(
                            voyage['destinations'][index])) is False:
                        return False
            if progress >= 1.0:
                self._complete_voyage(voyage)
                yield
                return True
            yield
        return False

    def travel_path(self, stars, on_arrive=None, activity=None,
                    speed_cap=None):
        if not self.start_voyage(stars, activity, speed_cap):
            return self.running and self.alive
        return (yield from self.wait_for_voyage(on_arrive))

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
        return True

    def clear_order(self):
        self.order = None

    def _handle_order(self):
        """Corrotina: executa uma ordem pendente. True quando foi atendida."""
        order = self.order
        if order is None:
            return False
        kind = order['kind']
        if kind == 'clear':
            self.clear_order()
            return False
        # A ordem passa a ser a ação corrente: libera o slot para reagir
        # a uma ordem seguinte.
        self.order = None
        if kind == 'hold':
            self.activity = "aguardando ordens"
            while self.running and self.alive and self.order is None:
                yield
            return True
        star = order['star']
        self.activity = f"-> {star.name} (ordem)"
        path = self.find_path_to_star(star) or [star]
        yield from self.travel_path(path, speed_cap=order.get('speed_cap'))
        return True

    def start(self):
        """Instancia a corrotina de IA; chamada na criação da nave."""
        self.running = True
        self._ai = self.ai()

    def step(self):
        """Avança a IA um quadro de simulação (chamada pelo GameState)."""
        if self._ai is None or not self.running or not self.alive:
            return
        try:
            next(self._ai)
        except StopIteration:
            self.running = False
            self._ai = None

    def ai(self):
        while self.running and self.alive:
            if (yield from self._handle_order()):
                continue
            yield

    # ---------- utilidades de tempo-de-jogo ----------
    def _wait_game_time(self, seconds):
        """Corrotina: espera `seconds` de relógio de jogo, cedendo a cada quadro."""
        t0 = self._clock()
        if getattr(self.faction, 'game_state', None) is None:
            time.sleep(seconds)
            return
        while self.running and self.alive and self.order is None:
            if self._clock() - t0 >= seconds:
                return
            yield

    # ---------- movimento controlado pelo relógio global ----------
    def move_to_star(self, from_star, to_star):
        if from_star is None or to_star is None:
            return
        if self.current_position is to_star and self._voyage is None:
            return
        self.activity = f"-> {to_star.name}"
        yield from self.travel_path([to_star])
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

    def ai(self):
        if self.faction.scout_manager:
            self.faction.scout_manager.register_scout(self.ship_id, self)

        while self.running and self.alive:
            if (yield from self._handle_order()):
                continue
            target = self._pick_unexplored()
            if target is None:
                self.activity = "sem alvos"
                yield from self._wait_game_time(3)
                continue
            path = self.find_path_to_star(target) or [target]
            self.activity = f"-> {target.name}"
            if not (yield from self.travel_path(path, on_arrive=self._scan)):
                if not self.running or not self.alive:
                    return
                continue
            self.activity = "idle"

    def _scan(self, star):
        if star.name in self.faction.explored_stars:
            return True
        self.activity = f"explorando {star.name}"
        yield from self._wait_game_time(self.scan_time)
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
        return True

    def _release_target(self):
        if self.target_planet is not None and self.faction is not None:
            self.faction.reserved_targets.discard(self.target_planet.name)
        self.target_star = None
        self.target_planet = None

    def destroy(self):
        if self.target_planet is not None and self.faction is not None:
            self.faction.reserved_targets.discard(self.target_planet.name)
            self.target_planet = None
            self.target_star = None
        super().destroy()

    def ai(self):
        while self.running and self.alive:
            if (yield from self._handle_order()):
                continue

            tgt_star = self.target_star
            tgt_planet = self.target_planet
            if tgt_star is None or tgt_planet is None:
                yield
                continue

            if tgt_planet.is_colonized:
                self._release_target()
                return

            path = self.find_path_to_star(tgt_star) or [tgt_star]
            if not (yield from self.travel_path(
                    path, activity=f"-> {tgt_planet.name}")):
                if not self.running or not self.alive:
                    return
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
    """Nave civil que cumpre uma fila de missões.

    Cada missão de carga leva vários recursos de uma colônia para outra; ao
    descarregar, a nave assume a próxima tarefa da fila em vez de replanejar o
    mundo inteiro do zero.
    """

    MAX_QUEUED_MISSIONS = 3

    def __init__(self, resource='Minerals', **kwargs):
        super().__init__(**kwargs)
        self.resource = resource
        self.cargo_hold = {}
        self.population_cargo = 0.0
        self.mission = None
        self.mission_queue = []
        self.source = None
        self.destination = None
        self._prefer_population = True

    # ---------- porão ----------
    @property
    def used_cargo(self) -> float:
        return sum(self.cargo_hold.values())

    @property
    def load(self) -> float:
        """Total de recursos no porão (mantém painéis e leituras antigas)."""
        return self.used_cargo

    def cargo_summary(self) -> str:
        parts = [f"{amount:.0f} {resource}"
                 for resource, amount in sorted(self.cargo_hold.items())]
        if self.population_cargo > 1e-6:
            parts.append(f"{self.population_cargo:.0f} migrantes")
        return ' · '.join(parts) if parts else 'vazio'

    def scheduled_missions(self):
        """Missões contratadas — a atual e as enfileiradas."""
        missions = []
        if self.mission is not None:
            missions.append(self.mission)
        missions.extend(self.mission_queue)
        return missions

    def _has_cargo(self) -> bool:
        return self.used_cargo > 1e-6 or self.population_cargo > 1e-6

    def _clear_mission(self):
        self.mission = None
        self.source = None
        self.destination = None

    # ---------- planejamento ----------
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

    def plan_missions(self):
        """Fila de tarefas da nave: rotas de carga e migração de população."""
        logistics = self.faction.logistics_manager
        runs = logistics.plan_freight_runs(
            self.cargo, count=self.MAX_QUEUED_MISSIONS,
            origin=self.current_position, reachable=self._route_is_reachable)
        missions = [{'kind': 'freight', 'source': run['source'],
                     'destination': run['destination'], 'legs': run['legs'],
                     'payload': run['payload']} for run in runs]
        migration = self.plan_population_transfer()
        if migration is not None:
            source, destination, amount = migration
            population = {'kind': 'population', 'source': source,
                          'destination': destination, 'amount': amount,
                          'legs': []}
            if self._prefer_population and missions:
                missions.insert(1, population)
            else:
                missions.insert(0, population)
        return missions[:self.MAX_QUEUED_MISSIONS]

    def _route_is_reachable(self, source, destination):
        return (
            nx.has_path(
                self.map_G, self.current_position.name,
                source.parent_star.name)
            and nx.has_path(
                self.map_G, source.parent_star.name,
                destination.parent_star.name)
        )

    # ---------- carga e entrega ----------
    def _load_population(self, source, amount):
        with source.lock:
            if (source.faction is not self.faction
                    or not source.is_colonized):
                return False
            available = max(
                0.0, source.population
                - max(100.0, source.population * 0.1))
            loaded = min(amount, available, self.cargo - self.used_cargo)
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
        yield from self.travel_path(path)
        return True

    # ---------- corrotinas ----------
    def _collect_missions(self):
        """Busca a primeira missão viável da fila e enche o porão."""
        while self.running and self.alive:
            if not self.mission_queue:
                self.mission_queue = self.plan_missions()
            if not self.mission_queue:
                return False
            mission = self.mission_queue.pop(0)
            self.mission = mission
            self.source = mission['source']
            self.destination = mission['destination']
            self.activity = (
                "indo buscar migrantes"
                if mission['kind'] == 'population'
                else f"indo buscar carga para {mission['destination'].name}")
            if not (yield from self._travel_to_planet(mission['source'])):
                self._clear_mission()
                return False
            loaded = (
                self._load_population(mission['source'], mission['amount'])
                if mission['kind'] == 'population'
                else self.faction.logistics_manager.load_cargo(
                    self, mission['source'], mission['legs']) > 0.0)
            if loaded:
                return True
            self._clear_mission()
        return False

    def _deliver_cargo(self):
        """Descarrega no destino; sobra é redirecionada para outra colônia."""
        logistics = self.faction.logistics_manager
        destination = self.destination
        if destination is None:
            return None
        if not (yield from self._travel_to_planet(destination)):
            return False
        delivered = (
            self._deliver_population(destination)
            if self.population_cargo > 1e-6 and self.mission is not None
            and self.mission['kind'] == 'population'
            else logistics.deliver_cargo(self, destination))
        self.activity = (
            f"entregue {delivered:.0f} em {destination.name}"
            if delivered > 0 else f"{destination.name} sem espaço")
        if not self._has_cargo():
            return True
        if self.population_cargo > 1e-6:
            self.destination = self._find_population_destination(self.source)
        else:
            self.resource = max(
                self.cargo_hold, key=self.cargo_hold.get,
                default=self.resource)
            self.destination = logistics.plan_hold_release(self)
        return True

    def ai(self):
        while self.running and self.alive:
            if (yield from self._handle_order()):
                continue
            if not self._has_cargo():
                if not (yield from self._collect_missions()):
                    if not self.running or not self.alive:
                        return
                    yield from self._wait_game_time(3)
                    continue
                self.activity = f"transportando {self.cargo_summary()}"
            delivered = yield from self._deliver_cargo()
            if delivered is None:
                self.mission_queue = []
                yield from self._wait_game_time(3)
                continue
            if not delivered:
                if not self.running or not self.alive:
                    return
                yield from self._wait_game_time(3)
                continue
            if not self._has_cargo():
                mission = self.mission
                self._clear_mission()
                if (mission is not None
                        and mission.get('kind') == 'population'):
                    self._prefer_population = not self._prefer_population
            yield from self._wait_game_time(1)


class Warship(Ship):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def ai(self):
        while self.running and self.alive:
            if self.shields < self.max_shields:
                self.shields = min(self.max_shields,
                                   self.shields + self.max_shields * 0.02)
            if (yield from self._handle_order()):
                continue
            target = self._pick_enemy_star()
            if target is not None:
                path = self.find_path_to_star(target) or [target]
                if not (yield from self.travel_path(
                        path, activity=f"-> {target.name}")):
                    if not self.running or not self.alive:
                        return
                    continue
                yield from self._wait_game_time(2)
                continue
            patrol = list(self.faction.controlled_stars.values())
            if patrol:
                dest = random.choice(patrol)
                if dest is not self.current_position:
                    path = self.find_path_to_star(dest)
                    if path and not (yield from self.travel_path(
                            path, activity=f"patrulhando {dest.name}")):
                        if not self.running or not self.alive:
                            return
                        continue
            yield from self._wait_game_time(2)

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
            