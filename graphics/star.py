from dataclasses import dataclass
from typing import Tuple, Dict, List
from queue import Queue, Empty
import threading
import time


SIMULATION_STEP_YEARS = 0.5


@dataclass(eq=False)
class Planet:
    n_planet_resources: int
    planet_resources: Dict[str, float]
    abs_position: Tuple[float, float]
    life_suitability: Dict[str, float]
    production: float
    developement: float
    distance_from_star: float
    radius: float
    is_colonized: bool
    name: str
    star_position:tuple


    def post_init(self):
        self.const_queue = Queue()
        self.developement = 0.1
        self.can_build_ships = True
        self.lock = threading.Lock()
        self.population = 0
        self.storage_capacity = {
            'Minerals': 10_000, 'Food': 5_000, 'Energy': 10_000,
            'Electronics': 2_000, 'Chemicals': 2_000, 'Alloys': 1_000,
            'Research': float('inf'),
        }
        self.faction = None
        self.ships = []
        self.parent_star = None
        self.terraform_level = 0
        self.max_terraform_level = 6
        self.defense = 0.0
        self.max_defense = 100.0
        for k in ('Minerals', 'Food', 'Energy', 'Electronics',
                  'Chemicals', 'Alloys', 'Research'):
            self.planet_resources.setdefault(k, 0.0)

    def get_suitability(self, faction) -> float:
        key = faction.faction_type.value if hasattr(faction, 'faction_type') else None
        if key and key in self.life_suitability:
            return self.life_suitability[key]
        return 0.0

    def _compute_caps(self):
        """Teto de desenvolvimento e população por nível de terraformação."""
        tier = min(getattr(self, 'terraform_level', 0), 5)
        caps = [(3.0, 3_000), (7.0, 8_000), (14.0, 20_000), (25.0, 50_000), (50.0, 100_000), (75.0, 1_000_000)]
        return caps[tier]

    def capacity_info(self) -> dict:
        max_dev, max_pop = self._compute_caps()
        return {
            'max_dev': max_dev,
            'max_pop': max_pop,
            'dev_capped': self.developement >= max_dev - 1e-6,
            'pop_capped': self.population >= max_pop - 1e-6,
        }

    def develop(self, dt: float = SIMULATION_STEP_YEARS):
        step_scale = dt / SIMULATION_STEP_YEARS
        growth_factor = 1.02 ** step_scale
        max_dev, max_pop = self._compute_caps()

        if self.developement < max_dev:
            self.developement = min(max_dev,
                                    self.developement * growth_factor)
        if self.population < max_pop:
            self.population = min(max_pop, self.population * growth_factor)

        # Libera construção assim que a colônia cresce um pouco
        if self.developement > 0.3:
            self.can_build_ships = True

        # Regen de defesa
        if (self.is_colonized and self.max_defense > 0
                and self.defense < self.max_defense):
            self.defense = min(self.max_defense,
                               self.defense
                               + 1.5 * self.developement * step_scale)

        self.const()
        self.produce(step_scale)

    def can_afford(self, cost: Dict[str, float]) -> bool:
        for resource, amount in cost.items():
            if self.planet_resources.get(resource, 0) < amount:
                return False
        return True

    def pay_cost(self, cost: Dict[str, float]) -> bool:
        if not self.can_afford(cost):
            return False
        for resource, amount in cost.items():
            self.planet_resources[resource] -= amount
        return True

    def const(self):
        try:
            task = self.const_queue.get_nowait()
        except Empty:
            return
        if self.faction is None:
            self.const_queue.put(task)
            return
        threading.Thread(target=self._build_ship, args=(task,),
                         daemon=True).start()

    def _build_ship(self, task):
        try:
            from players.factions import DESIGNS
        except Exception:
            return
        try:
            build_time = float(task.get('build_time', 5))
            state = getattr(self.faction, 'game_state', None)
            if state is not None:
                t0 = state.time
                while state.time - t0 < build_time:
                    time.sleep(0.05)
            else:
                time.sleep(build_time)

            if self.faction is None or self.faction.eliminated:
                return

            design = DESIGNS.get(task.get('design_key'))
            if design is None:
                return

            ship = design['class'](
                ship_id=task['id'], faction=self.faction,
                map_G=self.faction.map_G,
                current_position=self.parent_star,
                total_stars=self.faction.all_stars,
                design_key=task['design_key'],
                **design['stats'])

            # Alvo pré-atribuído (reserva feita no build_ship)
            target_star = task.get('target_star')
            target_planet = task.get('target_planet')
            if (target_star is not None and target_planet is not None
                    and hasattr(ship, 'assign_target')):
                if target_planet.is_colonized:
                    # Alguém tomou o planeta enquanto estávamos construindo
                    self.faction.reserved_targets.discard(target_planet.name)
                else:
                    ship.assign_target(target_star, target_planet)

            self.ships.append(ship)
            self.faction.ships[ship.ship_id] = ship
            ship.start()
            print(f"[{self.name}] {design['display']} {ship.ship_id} pronta")
        except Exception as e:
            print(f"[{self.name}] erro construindo: {e}")

    def produce(self, step_scale: float = 1.0):
        if self.faction is None:
            return
        prod = self.production * self.developement * step_scale
        for resource in list(self.planet_resources.keys()):
            if resource == 'Research':
                self.faction.add_research_income(prod)
                continue

            cap = self.storage_capacity.get(resource, 0)

            if resource == 'Food':
                # Produção primeiro (limitada ao cap)
                if self.planet_resources[resource] < cap:
                    room = cap - self.planet_resources[resource]
                    self.planet_resources[resource] += min(prod, room)
                # Consumo
                self.planet_resources[resource] -= (
                    self.population * 1e-4 * step_scale)
                # Déficit → fome
                if self.planet_resources[resource] < 0:
                    deficit = -self.planet_resources[resource]
                    self.planet_resources[resource] = 0.0
                    self.population -= deficit * 1000.0
                    if self.population < 0:
                        self.population = 0.0
                continue

            if self.planet_resources[resource] >= cap:
                continue
            self.planet_resources[resource] += prod


    def remove_resource(self, resource_type: str, amount: float) -> bool:
        if resource_type not in self.planet_resources:
            return False
        if self.planet_resources[resource_type] >= amount:
            self.planet_resources[resource_type] -= amount
            return True
        return False


@dataclass
class Star:
    name: str
    total_resources: float
    radius: float
    green_zone: float
    position: Tuple[float, float]
    planets: List[Planet]
