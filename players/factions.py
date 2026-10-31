import threading
from typing import Dict, Optional
from enum import Enum
from queue import Queue

import networkx as nx

from graphics.star import Star, Planet
from players.ships import Scout, ColonyShip, Transport, Warship

RESEARCH_SCALE = 15.0

TECH_CAPS = {
    'ftl': 10, 'exploration': 10, 'propulsion': 10,
    'weapons': 10, 'shields': 10, 'sensors': 10,
    'construction': 10,
}

class FactionType(Enum):
    HUMAN = "Human"
    ALIEN = "Alien"
    ROBOT = "Robot"
    HYBRID = "Hybrid"


class DiplomacyStatus(Enum):
    WAR = "War"
    CONFLICT = "Conflict"
    NEUTRAL = "Neutral"
    PEACE = "Peace"
    ALLY = "Ally"


DESIGNS = {
    'scout': {
        'class': Scout, 'display': 'Scout',
        'description': 'Explorador rapido', 'build_time': 3,
        'cost': {'Minerals': 10, 'Food': 2, 'Electronics': 5, 'Chemicals': 10},
        'stats': {'speed': 8, 'hull': 20, 'shields': 0, 'weapons': 0,
                  'cargo': 0, 'scan_time': 1.0},
    },
    'colony': {
        'class': ColonyShip, 'display': 'Colonizadora',
        'description': 'Funda novas colonias', 'build_time': 8,
        'cost': {'Minerals': 200, 'Food': 100, 'Electronics': 50,
                 'Chemicals': 50},
        'stats': {'speed': 3, 'hull': 60, 'shields': 10, 'weapons': 0,
                  'cargo': 100},
    },
    'transport': {
        'class': Transport, 'display': 'Transporte',
        'description': 'Move recursos', 'build_time': 4,
        'cost': {'Minerals': 50, 'Food': 20, 'Electronics': 20},
        'stats': {'speed': 5, 'hull': 40, 'shields': 5, 'weapons': 0,
                  'cargo': 500, 'resource': 'Minerals'},
    },
    'corvette': {
        'class': Warship, 'display': 'Corveta',
        'description': 'Guerra leve', 'build_time': 4,
        'cost': {'Minerals': 80, 'Alloys': 20, 'Electronics': 30,
                 'Chemicals': 20},
        'stats': {'speed': 6, 'hull': 100, 'shields': 20, 'weapons': 15,
                  'cargo': 20},
    },
    'destroyer': {
        'class': Warship, 'display': 'Destroier',
        'description': 'Guerra media', 'build_time': 8,
        'cost': {'Minerals': 160, 'Alloys': 50, 'Electronics': 80,
                 'Chemicals': 40},
        'stats': {'speed': 5, 'hull': 200, 'shields': 50, 'weapons': 30,
                  'cargo': 30},
    },
    'cruiser': {
        'class': Warship, 'display': 'Cruzador',
        'description': 'Guerra pesada', 'build_time': 15,
        'cost': {'Minerals': 320, 'Alloys': 120, 'Electronics': 160,
                 'Chemicals': 100},
        'stats': {'speed': 4, 'hull': 400, 'shields': 100, 'weapons': 60,
                  'cargo': 50},
    },
}


class Faction:
    def __init__(self, name, faction_type, home_planet, home_star,
                 starting_resources=None, is_human=False):
        self.name = name
        self.faction_type = faction_type
        self.home_star = home_star
        self.home_planet = home_planet
        self.color = self._generate_faction_color()
        self.is_human = is_human
        self.lock = threading.RLock()

        self.map_G = None
        self.all_stars = None
        self.game_state = None
        self.controller = None

        # Toggles controlados por controller/UI
        self.auto_colonize = False
        self.auto_terraform = False
        self.eliminated = False

        # Reservas de alvos (colony ships em construção/em voo)
        self.reserved_targets = set()

        start = {'Minerals': 500, 'Food': 200, 'Energy': 300,
                 'Electronics': 100, 'Chemicals': 100, 'Alloys': 50,
                 'Research': 0.0}
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
        
        self.stations = {}
        self.scout_manager = None

        self.tech_tree = {'ftl': 1, 'exploration': 1, 'propulsion': 1,
                          'weapons': 1, 'shields': 1, 'sensors': 1,
                          'construction': 1}
        
        self.research_weights = {k: 1.0 for k in self.tech_tree}
        self.research_progress = {k: 0.0 for k in self.tech_tree}
        self.research_income_pool = 0.0

        self.diplomacy = {}
        self.war_declarations = set()
        self.allies = set()

        self.controlled_stars = {home_star.name: home_star}
        self.explored_stars = {home_star.name}
        self.in_exploration = set()

        self.stats = {'ships_built': 0, 'stations_built': 0,
                      'colonies_established': 0, 'stars_explored': 0,
                      'battles_won': 0, 'battles_lost': 0,
                      'research_completed': 0,
                      'planets_captured': 0}

    def _generate_faction_color(self):
        return {FactionType.HUMAN: "#3498db",
                FactionType.ALIEN: "#e74c3c",
                FactionType.ROBOT: "#95a5a6",
                FactionType.HYBRID: "#9b59b6"}.get(self.faction_type, "#fff")

    # ---------- Recursos ----------
    def _recompute_resources(self):
        totals = {}
        for p in self.colonies.values():
            for k, v in p.planet_resources.items():
                totals[k] = totals.get(k, 0.0) + v
        self.resources = totals

    def can_afford(self, cost):
        return all(self.resources.get(r, 0) >= a for r, a in cost.items())

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
        if design_key not in DESIGNS:
            return False
        design = DESIGNS[design_key]
        if planet is None:
            planet = max(self.colonies.values(),
                         key=lambda p: p.production * p.developement)
        if not planet.can_afford(design['cost']):
            return False
        planet.pay_cost(design['cost'])
        self._recompute_resources()
        task = {'design_key': design_key,
                'build_time': design['build_time'],
                'id': self._next_ship_id(),
                'planet': planet,
                'target_planet': target_planet,
                'target_star': target_star}
        planet.const_queue.put(task)
        return True

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
                                respect_reservations=True):
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
                score = planet.get_suitability(self)
                if score > best_score:
                    best_score, best = score, (star, planet)
        return best if best_score > 0.25 else None

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

        # 3. Checa recursos e alvo
        if not self.can_afford(DESIGNS['colony']['cost']):
            return False
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

    # ---------- Auto-terraformação ----------
    def auto_terraform_step(self, threshold_minerals=400):
        """Tenta terraformar uma colônia. Retorna True se agiu."""
        if len(self.colonies) < 3: return False
        if self.resources.get('Minerals', 0) < threshold_minerals:
            return False
        for p in self.colonies.values():
            if self.can_terraform(p):
                return self.terraform(p)
        return False

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
        self.research_income_pool += amount * RESEARCH_SCALE

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
        per_tick *= RESEARCH_SCALE
        return per_tick / gs.tick_interval * gs.speed
    
    def get_research_cost(self, tech_field):
        base = {'exploration': 100, 'propulsion': 120, 'weapons': 150,
                'shields': 140, 'sensors': 110, 'construction': 130,
                'ftl': 140}
        level = self.tech_tree.get(tech_field, 1)
        # Curva geométrica: 100, 170, 289, 491, ... 11859 (Lv10)
        return base.get(tech_field, 100) * (1.7 ** (level - 1))

    def is_tech_capped(self, field):
        return self.tech_tree.get(field, 1) >= TECH_CAPS.get(field, 10)
    
    # ---------- Colonização ----------
    def establish_colony(self, star, planet):
        planet.is_colonized = True
        planet.faction = self
        planet.population = 500
        planet.production = 0.5
        planet.developement = 0.1
        planet.can_build_ships = False
        planet.defense = 200.0
        planet.max_defense = 200.0
        planet.planet_resources = {
            'Minerals': 100, 'Food': 200, 'Energy': 100,
            'Electronics': 20, 'Chemicals': 20, 'Alloys': 10,
            'Research': 0.0}
        self.colonies[planet.name] = planet
        self.controlled_stars[star.name] = star
        self.stats['colonies_established'] += 1
        # Limpa reservas obsoletas de TODAS as facções
        if self.game_state is not None:
            for f in self.game_state.factions:
                f.reserved_targets.discard(planet.name)
        self._recompute_resources()
        return True

    # ---------- Terraformação ----------
    def terraform_cost(self, planet):
        lvl = getattr(planet, 'terraform_level', 0)
        return {'Minerals': 150 * (lvl + 1),
                'Energy': 80 * (lvl + 1),
                'Chemicals': 40 * (lvl + 1),
                'Electronics': 50 * (lvl + 1)}

    def can_terraform(self, planet):
        return (planet is not None
                and planet.is_colonized
                and planet.faction is self
                and planet.terraform_level < planet.max_terraform_level
                and self.can_afford(self.terraform_cost(planet)))

    def terraform(self, planet):
        if not self.can_terraform(planet):
            return False
        self.pay_cost(self.terraform_cost(planet))
        planet.terraform_level += 1
        for k in list(planet.life_suitability.keys()):
            planet.life_suitability[k] = min(
                1.0, planet.life_suitability[k] + 0.15)
        planet.production *= 1.15
        return True

    # ---------- Diplomacia ----------
    def update_diplomacy(self, other, new_status):
        self.diplomacy[other.name] = new_status
        other.diplomacy[self.name] = new_status
        if new_status == DiplomacyStatus.WAR:
            self.war_declarations.add(other.name)
            other.war_declarations.add(self.name)
            self.allies.discard(other.name)
            other.allies.discard(self.name)
        elif new_status == DiplomacyStatus.ALLY:
            self.allies.add(other.name)
            other.allies.add(self.name)
            self.war_declarations.discard(other.name)
            other.war_declarations.discard(self.name)
        elif new_status in (DiplomacyStatus.NEUTRAL,
                            DiplomacyStatus.PEACE):
            self.war_declarations.discard(other.name)
            other.war_declarations.discard(self.name)
            self.allies.discard(other.name)
            other.allies.discard(self.name)

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
                mil += w * (s.hull / 100.0) * (1.0 + s.max_shields / 100.0)
        defs = sum(p.defense for p in self.colonies.values() if p.is_colonized)
        econ = sum(p.production * p.developement
                   for p in self.colonies.values() if p.is_colonized) * 10.0
        tech = sum(self.tech_tree.values()) * 5.0
        return {'military': mil, 'defense': defs, 'economy': econ,
                'tech': tech, 'total': mil + defs + econ + tech}

    def propose_alliance(self, other) -> bool:
        if other is self or other.eliminated:
            return False
        status = self.diplomacy.get(other.name, DiplomacyStatus.NEUTRAL)
        if status == DiplomacyStatus.WAR:
            return False
        if status == DiplomacyStatus.ALLY:
            return True
        self.update_diplomacy(other, DiplomacyStatus.ALLY)
        return True

    def break_alliance(self, other) -> bool:
        if self.diplomacy.get(other.name) != DiplomacyStatus.ALLY:
            return False
        self.update_diplomacy(other, DiplomacyStatus.NEUTRAL)
        return True
    

    def get_status_report(self):
        return {'name': self.name, 'faction_type': self.faction_type.value,
                'resources': dict(self.resources),
                'tech_levels': dict(self.tech_tree),
                'research_weights': dict(self.research_weights),
                'colonies': len(self.colonies), 'ships': len(self.ships),
                'stars_explored': len(self.explored_stars)}

    def stop_faction(self):
        if self.scout_manager:
            self.scout_manager.stop_manager()
        for s in list(self.ships.values()):
            s.stop()
