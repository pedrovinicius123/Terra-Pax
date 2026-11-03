import threading
import math

from enum import Enum
from graphics.star import SIMULATION_STEP_YEARS
from players.ships import Scout, ColonyShip, Transport, Warship
from logistics.modules.logistics_manager import LogisticsManager
from players.fleets import FleetManager

RESEARCH_SCALE = 1.0
BASE_COLONIZATION_RANGE = 1050.0
COLONIZATION_RANGE_PER_FTL_LEVEL = 70.0

# Custo base de um habitat orbital; escala com os já existentes no mundo.
HABITAT_BASE_COST = {'Minerals': 250, 'Energy': 200, 'Electronics': 100,
                     'Alloys': 60}
HABITAT_COST_GROWTH = 0.6
HABITAT_BUILD_TIME = 18.0  # meses de jogo

TECH_CAPS = {
    'ftl': 20, 'exploration': 20, 'propulsion': 20,
    'weapons': 20, 'shields': 20, 'sensors': 20,
    'construction': 20, 'biotech': 20,
}

FACTION_TRAITS = {
    'diplomacy': ('Diplomacia', 'Relações diplomáticas +20%'),
    'economy': ('Economia', 'Produção e renda comercial +20%'),
    'expansion': ('Expansão', 'Crescimento populacional +20%'),
    'military': ('Militar', 'Força de combate +20%'),
    'science': ('Ciência', 'Pesquisa +20%'),
}

GALACTIC_WONDERS = {
    'diplomatic': {
        'name': 'Assembleia das Estrelas',
        'description': 'Melhora relações diplomáticas continuamente.',
        'cost': {'Minerals': 1200, 'Energy': 900, 'Electronics': 300,
                 'Alloys': 250, 'Credits': 100},
    },
    'domination': {
        'name': 'Forja de Guerra Galáctica',
        'description': 'Aumenta em 35% a força de combate.',
        'cost': {'Minerals': 1800, 'Energy': 700, 'Electronics': 250,
                 'Alloys': 500, 'Credits': 100},
    },
    'economic': {
        'name': 'Mercado da Via Láctea',
        'description': 'Aumenta em 50% a pontuação econômica.',
        'cost': {'Minerals': 1000, 'Energy': 1000, 'Electronics': 400,
                 'Alloys': 250, 'Credits': 150},
    },
    'expansion': {
        'name': 'Berço de Novos Mundos',
        'description': 'Aumenta em 35% o crescimento populacional.',
        'cost': {'Minerals': 1500, 'Energy': 800, 'Electronics': 250,
                 'Alloys': 300, 'Credits': 100},
    },
    'scientific': {
        'name': 'Arquivo do Conhecimento',
        'description': 'Aumenta em 50% a pesquisa.',
        'cost': {'Minerals': 1000, 'Energy': 1200, 'Electronics': 500,
                 'Alloys': 200, 'Credits': 100},
    },
    'terraforming': {
        'name': 'Jardins de Éter',
        'description': 'Acelera em 25% a expansão terraformadora.',
        'cost': {'Minerals': 1400, 'Energy': 900, 'Electronics': 300,
                 'Chemicals': 600, 'Credits': 150},
    },
    'habitat': {
        'name': 'Cinturão de Vulcanos',
        'description': 'Potencializa em 25% os efeitos dos habitats.',
        'cost': {'Minerals': 1600, 'Energy': 800, 'Electronics': 450,
                 'Alloys': 350, 'Credits': 150},
    },
    'standard': {
        'name': 'Monumento do Triunfo',
        'description': 'Aumenta em 25% a força total da facção.',
        'cost': {'Minerals': 1500, 'Energy': 1000, 'Electronics': 350,
                 'Alloys': 400, 'Credits': 125},
    },
}

class FactionType(Enum):
    HUMAN = "Human"
    ALIEN = "Alien"
    ROBOT = "Robot"
    HYBRID = "Hybrid"


class DiplomacyStatus(Enum):
    WAR = "War"
    CONFLICT = "Conflict"
    TRADE = "Trade"
    NEUTRAL = "Neutral"
    PEACE = "Peace"
    ALLY = "Ally"


DESIGNS = {
    'scout': {
        'class': Scout, 'display': 'Scout',
        'description': 'Nave civil de exploração', 'build_time': 3,
        'cost': {'Minerals': 10, 'Food': 2, 'Electronics': 5, 'Chemicals': 10},
        'stats': {'speed': 8, 'hull': 20, 'shields': 0, 'weapons': 0,
                  'cargo': 0, 'scan_time': 1.0},
        'sprite': 'spaceShips_008.png',
    },
    'colony': {
        'class': ColonyShip, 'display': 'Colonizadora',
        'description': 'Funda novas colonias', 'build_time': 8,
        'cost': {'Minerals': 200, 'Food': 100, 'Electronics': 50,
                 'Chemicals': 50},
        'stats': {'speed': 3, 'hull': 60, 'shields': 10, 'weapons': 0,
                  'cargo': 100},
        'sprite': 'spaceShips_009.png',
    },
    'transport': {
        'class': Transport, 'display': 'Transporte',
        'description': 'Move recursos e população', 'build_time': 4,
        'cost': {'Minerals': 50, 'Food': 20, 'Electronics': 20},
        'stats': {'speed': 5, 'hull': 40, 'shields': 5, 'weapons': 0,
                  'cargo': 500, 'resource': 'Minerals'},
        'sprite': 'spaceShips_002.png',
    },
    'corvette': {
        'class': Warship, 'display': 'Corveta',
        'description': 'Guerra leve', 'build_time': 4,
        'cost': {'Minerals': 80, 'Alloys': 20, 'Electronics': 30,
                 'Chemicals': 20},
        'stats': {'speed': 6, 'hull': 100, 'shields': 20, 'weapons': 15,
                  'cargo': 20},
        'sprite': 'spaceShips_001.png',
    },
    'frigate': {
        'class': Warship, 'display': 'Fragata',
        'description': 'Escolta rápida de frota', 'build_time': 6,
        'cost': {'Minerals': 120, 'Alloys': 35, 'Electronics': 45,
                 'Chemicals': 30},
        'stats': {'speed': 6, 'hull': 145, 'shields': 35, 'weapons': 22,
                  'cargo': 24},
        'sprite': 'spaceShips_003.png',
    },
    'destroyer': {
        'class': Warship, 'display': 'Destroier',
        'description': 'Guerra media', 'build_time': 8,
        'cost': {'Minerals': 160, 'Alloys': 50, 'Electronics': 80,
                 'Chemicals': 40},
        'stats': {'speed': 5, 'hull': 200, 'shields': 50, 'weapons': 30,
                  'cargo': 30},
        'sprite': 'spaceShips_004.png',
    },
    'cruiser': {
        'class': Warship, 'display': 'Cruzador',
        'description': 'Guerra pesada', 'build_time': 15,
        'cost': {'Minerals': 320, 'Alloys': 120, 'Electronics': 160,
                 'Chemicals': 100},
        'stats': {'speed': 4, 'hull': 400, 'shields': 100, 'weapons': 60,
                  'cargo': 50},
        'sprite': 'spaceShips_005.png',
    },
    'battleship': {
        'class': Warship, 'display': 'Encouraçado',
        'description': 'Nave de linha fortemente armada', 'build_time': 22,
        'cost': {'Minerals': 480, 'Alloys': 190, 'Electronics': 210,
                 'Chemicals': 150},
        'stats': {'speed': 3.5, 'hull': 620, 'shields': 170, 'weapons': 90,
                  'cargo': 65},
        'sprite': 'spaceShips_006.png',
    },
    'dreadnought': {
        'class': Warship, 'display': 'Cruzador de batalha',
        'description': 'Nave capital de assalto', 'build_time': 32,
        'cost': {'Minerals': 700, 'Alloys': 300, 'Electronics': 300,
                 'Chemicals': 240},
        'stats': {'speed': 3, 'hull': 900, 'shields': 260, 'weapons': 130,
                  'cargo': 80},
        'sprite': 'spaceShips_007.png',
    },
}


class Faction:
    def __init__(self, name, faction_type, home_planet, home_star,
             starting_resources=None, is_human=False,
             color=None, description="", advantage="science",
             disadvantage="military"):
        if advantage not in FACTION_TRAITS:
            raise ValueError(f"Vantagem de facção inválida: {advantage}")
        if disadvantage not in FACTION_TRAITS:
            raise ValueError(f"Desvantagem de facção inválida: {disadvantage}")
        if advantage == disadvantage:
            raise ValueError("Vantagem e desvantagem devem ser diferentes")
        
        self.name = name
        self.faction_type = faction_type
        self.home_star = home_star
        self.home_planet = home_planet
        self.color = color or self._generate_faction_color()
        self.description = description
        self.advantage = advantage
        self.disadvantage = disadvantage
        self.is_human = is_human
        self.lock = threading.RLock()

        self.map_G = None
        self.all_stars = None
        self.game_state = None
        self.controller = None

        # Toggles controlados por controller/UI
        self.auto_colonize = False
        self.auto_habitat = False
        self.eliminated = False

        # Reservas de alvos (colony ships em construção/em voo)
        self.reserved_targets = set()

        start = {'Minerals': 500, 'Food': 200, 'Energy': 300,
                 'Electronics': 100, 'Chemicals': 100, 'Alloys': 50,
                 'Credits': 100, 'Research': 0.0}
        if starting_resources:
            start.update(starting_resources)

        self.home_planet.planet_resources = dict(start)
        self.home_planet.is_colonized = True
        self.home_planet.faction = self
        self.home_planet.population = 1000
        self.home_planet.production = 1.0
        self.home_planet.developement = 0.3
        self.home_planet.can_build_ships = True
        self.home_planet.defense = 500.0
        self.home_planet.max_defense = 500.0

        self.colonies = {self.home_planet.name: self.home_planet}
        self.resources = {}
        self._recompute_resources()

        self.ships = {}
        self._ship_counter = 0
        self.logistics_manager = LogisticsManager(self)
        self.fleet_manager = FleetManager(self)
        
        self.stations = {}
        self.scout_manager = None

        self.tech_tree = {'ftl': 1, 'exploration': 1, 'propulsion': 1,
                          'weapons': 1, 'shields': 1, 'sensors': 1,
                          'construction': 1, 'biotech': 1}
        
        self.research_weights = {k: 1.0 for k in self.tech_tree}
        self.research_progress = {k: 0.0 for k in self.tech_tree}
        self.research_income_pool = 0.0
        self.colonization_rng = BASE_COLONIZATION_RANGE

        self.diplomacy = {}
        self.relations = {}
        self.treaties = {}
        
        self.war_declarations = set()
        self.allies = set()
        self.wonders = set()
        self.pending_peace_offers = set()
        self.pending_trade_offers = set()
        self.declined_peace_offers = set()

        self.controlled_stars = {home_star.name: home_star}
        self.explored_stars = {home_star.name}
        self.in_exploration = set()

        self.stats = {'ships_built': 0, 'stations_built': 0,
                      'colonies_established': 0, 'stars_explored': 0,
                      'battles_won': 0, 'battles_lost': 0,
                      'research_completed': 0,
                      'planets_captured': 0}

    def _set_colonization_rng(self):
        self.colonization_rng = (
            BASE_COLONIZATION_RANGE
            + (self.tech_tree['ftl'] - 1) * COLONIZATION_RANGE_PER_FTL_LEVEL
        )

    def _generate_faction_color(self):
        """Fallback: cor derivada do nome — nunca repete entre facções."""
        palette = [
            "#3498db", "#e74c3c", "#bdc3c7", "#e67e22",
            "#9b59b6", "#2ecc71", "#1abc9c", "#f39c12",
            "#e91e63", "#7f8c8d", "#16a085", "#d35400",
        ]
        idx = sum(ord(c) for c in self.name) % len(palette)
        return palette[idx]

    # ---------- Recursos ----------
    def trait_multiplier(self, trait):
        if self.advantage == trait:
            return 1.2
        if self.disadvantage == trait:
            return 0.8
        return 1.0

    @property
    def economy_multiplier(self):
        wonder_bonus = 1.5 if 'economic' in self.wonders else 1.0
        return self.trait_multiplier('economy') * wonder_bonus

    @property
    def research_multiplier(self):
        wonder_bonus = 1.5 if 'scientific' in self.wonders else 1.0
        return self.trait_multiplier('science') * wonder_bonus

    @property
    def combat_multiplier(self):
        wonder_bonus = 1.35 if 'domination' in self.wonders else 1.0
        return self.trait_multiplier('military') * wonder_bonus

    @property
    def population_growth_multiplier(self):
        wonder_bonus = 1.35 if 'expansion' in self.wonders else 1.0
        return self.trait_multiplier('expansion') * wonder_bonus

    def _recompute_resources(self):
        totals = {}
        for p in self.colonies.values():
            for k, v in p.planet_resources.items():
                totals[k] = totals.get(k, 0.0) + v
        self.resources = totals

    def can_afford(self, cost):
        return all(self.resources.get(r, 0) >= a for r, a in cost.items())

    def empire_income(self) -> dict:
        """Saldo anual do império: o que sobra depois do consumo das colônias."""
        income = {}
        for planet in self.colonies.values():
            outputs = planet.resource_output()
            demand = planet.consumption()
            for resource, amount in outputs.items():
                if resource in ('Research', 'Credits'):
                    continue
                income[resource] = (
                    income.get(resource, 0.0) + amount
                    - demand.get(resource, 0.0))
        return {resource: max(0.0, amount)
                for resource, amount in income.items()}

    def can_fund(self, cost, horizon_years: float = 6.0) -> bool:
        """Dá para pagar a obra hoje ou com o que o império produz no prazo?"""
        income = self.empire_income()
        return all(
            self.resources.get(resource, 0.0)
            + income.get(resource, 0.0) * horizon_years >= amount
            for resource, amount in cost.items())

    def queued_ship_count(self, design_key=None):
        total = 0
        for planet in self.colonies.values():
            for task in planet.queued_tasks():
                if task.get('kind') == 'habitat':
                    continue
                if design_key is None or task.get('design_key') == design_key:
                    total += 1
        return total

    def pay_cost(self, cost):
        if not self.can_afford(cost):
            return False
        for r, amount in cost.items():
            remaining = amount
            for p in self.colonies.values():
                if remaining <= 0:
                    break
                have = p.planet_resources.get(r, 0.0)
                take = min(have, remaining)
                p.planet_resources[r] = have - take
                remaining -= take
        self._recompute_resources()
        return True

    # ---------- Naves ----------
    def _next_ship_id(self):
        self._ship_counter += 1
        return f"{self.name[:3].upper()}-{self._ship_counter:03d}"

    def build_ship(self, design_key, planet=None,
                   target_planet=None, target_star=None):
        """Enfileira a nave na colônia; o custo é pago quando a obra começa.

        Escassez local não barra a obra: ela entra na fila e os transportes
        trazem o que falta de outras colônias.
        """
        if design_key not in DESIGNS:
            return False
        design = DESIGNS[design_key]
        if not self.colonies:
            return False
        if planet is None:
            planet = self.pick_shipyard(design)
            if not planet:
                return False

        if planet is None or not planet.can_build_ships:
            return False
        if planet.queue_is_full():
            return False
        task_id = self._next_ship_id()
        task = {'design_key': design_key,
                'label': f"{design['display']} {task_id}",
                'build_time': design['build_time'],
                'cost': dict(design['cost']),
                'kind': 'ship',
                'id': task_id,
                'planet': planet,
                'target_planet': target_planet,
                'target_star': target_star}
        planet.queue_task(task)
        return planet

    def pick_shipyard(self, needed:dict):
        resource_score = []
        for col in self.colonies.values():
            resources_available = 0
            for k, v in needed['cost'].items():
                resources_available += col.planet_resources.get(k, 0) / v
            resource_score.append((len(col.build_queue), resources_available, col))            
        
        for r in sorted(resource_score, key=lambda x:x[:2]):
            if r[2].queue_is_full():
                continue
            return r[2]

    def spawn_ship(self, design_key, at_star=None):
        design = DESIGNS[design_key]
        star = at_star or self.home_star
        ship = design['class'](
            ship_id=self._next_ship_id(), faction=self,
            map_G=self.map_G, current_position=star,
            total_stars=self.all_stars, design_key=design_key,
            **design['stats'])
        self.ships[ship.ship_id] = ship
        ship.start()
        return ship

    def idle_colony_ships(self):
        return [s for s in self.ships.values()
                if isinstance(s, ColonyShip) and s.alive
                and s.target_planet is None]

    # ---------- Auto-colonização ----------
    def find_best_colony_target(self, game_state,
                            respect_reservations=True,
                            max_distance=None):
        """Escolhe planeta por suitability ajustada por distância.

        score = (0.1 + suitability) × (1 - 0.5 × dist/max_dist)
        → mundos hostis (asteroides, gigantes gasosos) são colonizáveis
        quando não há alternativa melhor; expansão eleva a suitability.
        """
        if not self.colonies:
            return None
        if max_distance is None:
            max_distance = self.colonization_rng
        frontier = list(self.colonies.values())

        def dist_to_empire(planet):
            return min(math.dist(planet.abs_position, c.abs_position)
                    for c in frontier)

        best_score, best = 0.0, None
        for star in game_state.stars:
            if star.name not in self.explored_stars:
                continue
            for planet in star.planets:
                if planet.is_colonized:
                    continue
                if (respect_reservations
                        and planet.name in self.reserved_targets):
                    continue
                d = dist_to_empire(planet)
                if d > max_distance:
                    continue
                suit = planet.get_suitability(self)
                score = ((0.1 + suit)
                         * (1.0 - 0.5 * min(1.0, d / max_distance)))
                if score > best_score:
                    best_score, best = score, (star, planet)
        return best

    def auto_expand_step(self, game_state):
        """Um passo de auto-colonização. Cap = 1 colonizadora comprometida.

        `reserved_targets` rastreia alvos já prometidos a uma nave
        (em construção ou em voo). Como cada build adiciona 1 e cada
        destroy remove 1, o império nunca tem mais de 1 nave sendo
        produzida por vez.
        """
        # 1. Atribui alvos a naves ociosas (ex.: construídas manualmente)
        idle = self.idle_colony_ships()
        if idle:
            target = self.find_best_colony_target(game_state)
            if target:
                star, planet = target
                self.reserved_targets.add(planet.name)
                if idle[0].assign_target(star, planet):
                    return True
                self.reserved_targets.discard(planet.name)

        # 2. Cap: não construir se já há reserva ativa
        if self.reserved_targets:
            return False

        # 3. Checa alvo; o custo da obra é pago quando ela puder começar
        target = self.find_best_colony_target(game_state)
        if not target:
            return False

        star, planet = target
        self.reserved_targets.add(planet.name)
        if not self.build_ship('colony', target_planet=planet,
                               target_star=star):
            self.reserved_targets.discard(planet.name)
            return False
        return True

    # ---------- Habitats orbitais ----------
    def habitat_cost(self, planet):
        n = getattr(planet, 'habitats', 0) + getattr(
            planet, 'habitat_building', False)
        scale = 1.0 + HABITAT_COST_GROWTH * n
        cost = {r: a * scale for r, a in HABITAT_BASE_COST.items()}
        if 'habitat' in self.wonders:
            cost = {r: a * 0.8 for r, a in cost.items()}
        return {r: round(a, 1) for r, a in cost.items()}

    def can_build_habitat(self, planet):
        from graphics.star import HABITAT_MAX_PER_PLANET
        return (planet is not None
                and planet.is_colonized
                and planet.faction is self
                and planet.habitats < HABITAT_MAX_PER_PLANET
                and not planet.habitat_building
                and not planet.queue_is_full())

    def build_habitat(self, planet=None):
        """Enfileira a construção de um habitat na colônia indicada."""
        if planet is None:
            candidates = [
                p for p in self.colonies.values()
                if self.can_build_habitat(p)]
            if not candidates:
                return False
            planet = max(candidates, key=lambda p: p.population)
        if not self.can_build_habitat(planet):
            return False
        planet.habitat_building = True
        planet.queue_task({
            'kind': 'habitat',
            'label': f"Habitat orbital de {planet.name}",
            'build_time': HABITAT_BUILD_TIME,
            'cost': self.habitat_cost(planet),
            'faction': self,
            'id': f"HAB-{self.name[:3].upper()}-{planet.habitats + 1}",
        })
        return True

    def auto_habitat_step(self):
        """Constrói habitat na colônia mais pressionada (auto button/AI)."""
        from graphics.star import HABITAT_MAX_PER_PLANET
        best, best_pressure = None, 0.0
        for p in self.colonies.values():
            if p.habitats >= HABITAT_MAX_PER_PLANET or p.habitat_building:
                continue
            if not self.can_build_habitat(p):
                continue
            _, max_pop = p._compute_caps()
            pressure = p.population / max(1.0, max_pop)
            if pressure > best_pressure:
                best, best_pressure = p, pressure
        if best is None:
            return False
        return self.build_habitat(best)

    def habitat_total(self):
        return sum(getattr(p, 'habitats', 0)
                   for p in self.colonies.values()
                   if p.faction is self)

    # ---------- Scouts ----------
    def initialize_scout_manager(self, map_G, total_stars):
        from players.managers import ScoutManager
        self.map_G = map_G
        self.all_stars = total_stars
        self.scout_manager = ScoutManager(self)
        self.scout_manager.start_manager()

    def queue_scout_construction(self):
        return self.build_ship('scout')

    # ---------- Pesquisa ----------
    def add_research_income(self, amount: float):
        """Chamado por Planet.produce(). Acumula no pool."""
        trade_partners = sum(
            'trade' in treaties for treaties in self.treaties.values())
        trade_multiplier = 1.0 + min(0.5, trade_partners * 0.05)
        self.research_income_pool += (
            amount * RESEARCH_SCALE * self.research_multiplier
            * trade_multiplier)

    def process_research(self, dt=1.0):
        pool = self.research_income_pool
        if pool <= 0:
            return
        self.research_income_pool = 0.0

        # Apenas campos não-capados competem pelo pool
        uncapped = [f for f in self.tech_tree
                    if not self.is_tech_capped(f)]
        if not uncapped:
            return

        total_weight = sum(self.research_weights.get(f, 0) for f in uncapped)
        if total_weight <= 0:
            # Todos os pesos zerados — distribui igualmente
            for f in uncapped:
                self.research_weights[f] = 1.0
            total_weight = float(len(uncapped))

        for field in uncapped:
            weight = self.research_weights.get(field, 1.0)
            if weight <= 0:
                continue
            share = pool * (weight / total_weight)
            self.research_progress[field] += share

            for _ in range(20):
                if self.is_tech_capped(field):
                    self.research_progress[field] = 0.0
                    break
                cost = self.get_research_cost(field)
                if cost <= 0 or self.research_progress[field] < cost:
                    break

                self.research_progress[field] -= cost
                self.tech_tree[field] += 1
                self._set_colonization_rng()

                self.stats['research_completed'] += 1

    def set_research_weight(self, field: str, weight: float):
        if field not in self.tech_tree:
            return False
        self.research_weights[field] = max(0.0, min(10.0, float(weight)))
        return True

    def reset_research_weights(self):
        for k in self.research_weights:
            self.research_weights[k] = 1.0

    def compute_research_rate(self) -> float:
        gs = self.game_state
        if gs is None or gs.paused or gs.tick_interval <= 0:
            return 0.0
        if all(self.is_tech_capped(f) for f in self.tech_tree):
            return 0.0
        per_tick = sum(p.production * p.developement
                       for p in self.colonies.values()
                       if p.is_colonized and p.faction is self)
        per_tick *= RESEARCH_SCALE * self.economy_multiplier
        per_tick *= self.research_multiplier
        trade_partners = sum(
            'trade' in treaties for treaties in self.treaties.values())
        per_tick *= 1.0 + min(0.5, trade_partners * 0.05)
        return per_tick / SIMULATION_STEP_YEARS
    
    def get_research_cost(self, tech_field):
        base = {'exploration': 100, 'propulsion': 120, 'weapons': 150,
                'shields': 140, 'sensors': 110, 'construction': 130,
                'ftl': 140, 'biotech': 125}
        level = self.tech_tree.get(tech_field, 1)
        # Curva geométrica: 100, 170, 289, 491, ... 11859 (Lv10)
        cost = base.get(tech_field, 100) * math.pow(1.7, level - 1)
        if (self.game_state is not None
                and self.game_state.victory_mode == 'scientific'):
            cost *= 2.5
        return cost

    def is_tech_capped(self, field):
        return self.tech_tree.get(field, 1) >= TECH_CAPS.get(field, 10)
    
    # ---------- Colonização ----------
    def establish_colony(self, star, planet):
        planet.is_colonized = True
        planet.faction = self
        planet_type = getattr(planet, 'planet_type', 'terrestrial')
        founding = {
            'terrestrial': (500, 0.5),
            'asteroid': (240, 0.8),
            'gas_giant': (140, 0.6),
        }.get(planet_type, (500, 0.5))
        planet.population = founding[0]
        planet.production = founding[1]
        planet.developement = 0.1
        planet.can_build_ships = False
        planet.defense = 200.0
        planet.max_defense = 200.0
        initial_resources = {
            'terrestrial': {'Minerals': 100, 'Food': 200, 'Energy': 100,
                            'Electronics': 20, 'Chemicals': 20,
                            'Alloys': 10},
            'asteroid': {'Minerals': 800, 'Food': 60, 'Energy': 80,
                         'Electronics': 10, 'Chemicals': 10,
                         'Alloys': 60},
            'gas_giant': {'Minerals': 30, 'Food': 20, 'Energy': 900,
                          'Electronics': 10, 'Chemicals': 150,
                          'Alloys': 5},
        }.get(planet_type, {'Minerals': 100, 'Food': 200, 'Energy': 100,
                            'Electronics': 20, 'Chemicals': 20,
                            'Alloys': 10})
        initial_resources.update({'Credits': 0.0, 'Research': 0.0})
        planet.planet_resources = initial_resources
        self.colonies[planet.name] = planet
        self.controlled_stars[star.name] = star
        self.stats['colonies_established'] += 1
        # Limpa reservas obsoletas de TODAS as facções
        if self.game_state is not None:
            for f in self.game_state.factions:
                f.reserved_targets.discard(planet.name)
        self._recompute_resources()
        return True

    def decolonize_planet(self, planet):
        """Remove a colonia do imperio (pop chegou a zero). O planeta volta
        a ser 'livre' e pode ser re-colonizado no futuro.

        Efeitos colaterais:
        - remove do dict colonies e do controle de sistemas
        - zera population, defense, developement, recursos e fila
        - mantem terraform_level (a atmosfera continua terraformada)
        - se for a ultima colonia, marca a faccao como eliminada
        """
        if planet is None or planet.faction is not self:
            return False

        # Desvincula o planeta
        self.colonies.pop(planet.name, None)
        planet.faction = None
        planet.is_colonized = False
        planet.population = 0.0
        planet.defense = 0.0
        planet.developement = 0.0
        planet.production = 1.0
        planet.can_build_ships = False
        planet.habitats = 0
        planet.habitat_building = False
        planet.famine = 0.0
        # Zera recursos (foram consumidos na agonia)
        for k in planet.planet_resources:
            planet.planet_resources[k] = 0.0

        # Limpa fila de construcao pendente
        planet.clear_build_queue()

        # Notifica o estado global
        if self.game_state is not None:
            for f in self.game_state.factions:
                f.reserved_targets.discard(planet.name)
            self.game_state._recompute_control()
            self.game_state.log_event(
                f"{self.name} perdeu {planet.name} (populacao zero)")

        # Reassenta capital se necessario
        if self.home_planet is planet and self.colonies:
            self.home_planet = next(iter(self.colonies.values()))

        # Eliminacao
        if not self.colonies:
            self.eliminated = True
            for s in list(self.ships.values()):
                s.alive = False
                s.running = False
            if self.game_state is not None:
                self.game_state.log_event(f"{self.name} foi eliminada!")

        self._recompute_resources()
        return True

    # ---------- Diplomacia ----------
    def get_relation(self, other):
        return self.relations.get(other.name, 50)

    def adjust_relation(self, other, amount):
        amount *= self.trait_multiplier('diplomacy')
        if 'diplomatic' in self.wonders:
            amount *= 1.25
        relation = max(0, min(100, self.get_relation(other) + amount))
        self.relations[other.name] = relation
        other.relations[self.name] = relation
        return relation

    def has_treaty(self, other, treaty):
        return treaty in self.treaties.get(other.name, set())

    def _can_negotiate(self, other):
        return (
            other is not self
            and not self.eliminated
            and not other.eliminated
            and self.diplomacy.get(
                other.name, DiplomacyStatus.NEUTRAL) != DiplomacyStatus.WAR
        )
    
    def _cancel_treaty(self, other, treaty):
        self.treaties.setdefault(other.name, set()).remove(treaty)
        other.treaties.setdefault(self.name, set().remove(treaty))

    def improve_relations(self, other):
        cost = {'Energy': 25}
        if (not self._can_negotiate(other)
                or self.get_relation(other) >= 100
                or not self.pay_cost(cost)):
            return False
        self.adjust_relation(other, 10)
        return True
    ## NOTE!!! THIS METHOD WILL BE OBSOLETE SOON!
    def offer_treaty(self, other, treaty):
        thresholds = {'non_aggression': 45, 'trade': 55}
        if treaty not in thresholds or not self._can_negotiate(other):
            return False
        if self.has_treaty(other, treaty):
            if self.logistics_manager.overload_status().get("overloaded", False):
                self._cancel_treaty(other, treaty)
            return True
        if self.get_relation(other) < thresholds[treaty]:
            return False

        self.treaties.setdefault(other.name, set()).add(treaty)
        other.treaties.setdefault(self.name, set()).add(treaty)
        return True

    def propose_peace(self, other):
        if (other is self or self.eliminated or other.eliminated
                or self.diplomacy.get(other.name) != DiplomacyStatus.WAR
                or self.name in other.declined_peace_offers):
            return False
        other.pending_peace_offers.add(self.name)
        return True

    def propose_trade_offer(self, other):
        if (other is self or self.eliminated or other.eliminated
                or self.diplomacy.get(other.name) != DiplomacyStatus.WAR
                or self.name in other.declined_peace_offers):
            return False
        other.pending_trade_offers.add(self.name)
        return True

    def respond_to_peace_offer(self, other, accept):
        if other.name not in self.pending_peace_offers:
            return False
        self.pending_peace_offers.discard(other.name)
        if accept:
            if self.diplomacy.get(other.name) != DiplomacyStatus.WAR:
                return False
            self.update_diplomacy(other, DiplomacyStatus.PEACE)
        else:
            self.declined_peace_offers.add(other.name)
        return True

    def respond_to_trade_offer(self, other, accept):
        if other.name not in self.pending_trade_offers or self.diplomacy[other.name] == DiplomacyStatus.WAR:
            return False
        if accept and self.is_human:
            if self.diplomacy.get(other.name) == DiplomacyStatus.TRADE:
                return False

            self.treaties.setdefault(other.name, set()).add('trade')
            other.treaties.setdefault(self.name, set()).add('trade')

        elif not self.is_human and self.logistics_manager.overload_status().get('overloaded', False):
            print("Recusado!")
            return False

        self.treaties.setdefault(other.name, set()).add('trade')
        other.treaties.setdefault(self.name, set()).add('trade')
        return True

    def update_diplomacy(self, other, new_status):
        old_status = self.diplomacy.get(other.name, DiplomacyStatus.NEUTRAL)
        self.diplomacy[other.name] = new_status
        other.diplomacy[self.name] = new_status

        if new_status == DiplomacyStatus.WAR:
            self.pending_peace_offers.discard(other.name)
            other.pending_peace_offers.discard(self.name)
            self.declined_peace_offers.discard(other.name)
            other.declined_peace_offers.discard(self.name)
            self.war_declarations.add(other.name)
            other.war_declarations.add(self.name)
            self.allies.discard(other.name)
            other.allies.discard(self.name)
            self.treaties.pop(other.name, None)
            other.treaties.pop(self.name, None)
            if old_status != DiplomacyStatus.WAR:
                self.adjust_relation(other, -20)
        elif new_status == DiplomacyStatus.ALLY:
            self.allies.add(other.name)
            other.allies.add(self.name)
            self.war_declarations.discard(other.name)
            other.war_declarations.discard(self.name)
        elif new_status in (DiplomacyStatus.NEUTRAL,
                            DiplomacyStatus.PEACE):
            self.pending_peace_offers.discard(other.name)
            other.pending_peace_offers.discard(self.name)
            self.declined_peace_offers.discard(other.name)
            other.declined_peace_offers.discard(self.name)
            self.war_declarations.discard(other.name)
            other.war_declarations.discard(self.name)
            self.allies.discard(other.name)
            other.allies.discard(self.name)
            if (old_status == DiplomacyStatus.WAR
                    and new_status == DiplomacyStatus.PEACE):
                self.adjust_relation(other, 10)

    def compute_strength(self) -> dict:
        """Força total comparável entre facções.
        military: poder de fogo das naves de guerra
        defense:  soma das defesas de colônias
        economy:  produção × desenvolvimento × 10
        tech:     níveis de tech × 5 (vantagem tecnológica)
        """
        mil = 0.0
        for s in self.ships.values():
            if not s.alive:
                continue
            w = getattr(s, 'weapons', 0)
            if w > 0:
                mil += (w * (s.hull / 100.0)
                        * (1.0 + s.max_shields / 100.0)
                        * self.combat_multiplier)
        defs = sum(p.defense for p in self.colonies.values() if p.is_colonized)
        econ = sum(p.production * p.developement
                   for p in self.colonies.values() if p.is_colonized) * 10.0
        econ *= self.economy_multiplier
        tech = sum(self.tech_tree.values()) * 5.0
        total = mil + defs + econ + tech
        if 'standard' in self.wonders:
            total *= 1.25
        return {'military': mil, 'defense': defs, 'economy': econ,
                'tech': tech, 'total': total}

    def economy_score(self):
        production = sum(
            planet.production * planet.developement
            for planet in self.colonies.values() if planet.is_colonized)
        stockpiles = sum(
            amount * (2.0 if resource == 'Credits' else 0.5)
            for resource, amount in self.resources.items()
            if resource != 'Research')
        trade_partners = sum(
            'trade' in treaties for treaties in self.treaties.values())
        trade_bonus = 1.0 + min(1.0, trade_partners * 0.2)
        return (
            production * 100.0 + stockpiles
        ) * trade_bonus * self.economy_multiplier

    def build_wonder(self, wonder_type):
        if wonder_type not in GALACTIC_WONDERS:
            return False
        state = self.game_state
        if state is None:
            return False
        with state.lock:
            if (self.eliminated or wonder_type in self.wonders
                    or wonder_type in state.wonders_built):
                return False
            cost = GALACTIC_WONDERS[wonder_type]['cost']
            if not self.can_afford(cost):
                return False
            if not self.pay_cost(cost):
                return False
            self.wonders.add(wonder_type)
            state.wonders_built[wonder_type] = self.name
            self._recompute_resources()
            state.log_event(
                f"{self.name} construiu {GALACTIC_WONDERS[wonder_type]['name']}")
            return True

    def propose_alliance(self, other) -> bool:
        if other is self or other.eliminated:
            return False
        status = self.diplomacy.get(other.name, DiplomacyStatus.NEUTRAL)
        if status == DiplomacyStatus.WAR:
            return False
        if status == DiplomacyStatus.ALLY:
            return True
        minimum_relation = 85 if (
            self.game_state is not None
            and self.game_state.victory_mode == 'diplomatic') else 70
        if (self.get_relation(other) < minimum_relation
                or not self.has_treaty(other, 'trade')):
            return False
        self.update_diplomacy(other, DiplomacyStatus.ALLY)
        self.adjust_relation(other, 10)
        return True

    def break_alliance(self, other) -> bool:
        if self.diplomacy.get(other.name) != DiplomacyStatus.ALLY:
            return False
        self.update_diplomacy(other, DiplomacyStatus.NEUTRAL)
        self.adjust_relation(other, -15)
        return True
    

    def get_status_report(self):
        return {'name': self.name,
                'faction_type': self.faction_type.value,
                'description': self.description,
                'advantage': self.advantage,
                'disadvantage': self.disadvantage,
                'wonders': sorted(self.wonders),
                'resources': dict(self.resources),
                'tech_levels': dict(self.tech_tree),
                'research_weights': dict(self.research_weights),
                'colonies': len(self.colonies),
                'ships': len(self.ships),
                'stars_explored': len(self.explored_stars)}

    def stop_faction(self):
        if self.scout_manager:
            self.scout_manager.stop_manager()
        for s in list(self.ships.values()):
            s.stop()
