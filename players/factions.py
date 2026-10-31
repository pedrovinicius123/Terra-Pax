import threading
from typing import Dict, Optional
from enum import Enum
from queue import Queue

import networkx as nx

from graphics.star import Star, Planet
from players.ships import Scout, ColonyShip, Transport, Warship


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

        self.auto_colonize = False
        self.eliminated = False

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

        self.resources = {}
        self.colonies = {self.home_planet.name: self.home_planet}
        self._recompute_resources()

        self.ships = {}
        self._ship_counter = 0
        self.stations = {}
        self.scout_manager = None

        self.tech_tree = {'ftl': 1, 'exploration': 1, 'propulsion': 1,
                          'weapons': 1, 'shields': 1, 'sensors': 1,
                          'construction': 1}
        self.research_queue = Queue()
        self.current_research = None
        self.research_progress = 0.0

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

    def build_ship(self, design_key, planet=None):
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
                'id': self._next_ship_id(), 'planet': planet}
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
                and not s.assigned.is_set()]

    def _pending_colony_ships(self):
        count = 0
        for p in self.colonies.values():
            for task in list(p.const_queue.queue):
                if task.get('design_key') == 'colony':
                    count += 1
        return count

    # ---------- Auto-colonização ----------
    def find_best_colony_target(self, game_state):
        best_score, best = 0.0, None
        for star in game_state.stars:
            if star.name not in self.explored_stars:
                continue
            for planet in star.planets:
                if planet.is_colonized:
                    continue
                score = planet.get_suitability(self)
                if score > best_score:
                    best_score, best = score, (star, planet)
        return best if best_score > 0.25 else None

    def auto_expand_step(self, game_state):
        """Executa um passo de auto-colonização. Retorna True se agiu."""
        idle = self.idle_colony_ships()
        if idle:
            target = self.find_best_colony_target(game_state)
            if target:
                idle[0].assign_target(*target)
                return True
        if len(idle) + self._pending_colony_ships() >= 1:
            return False
        if self.can_afford(DESIGNS['colony']['cost']):
            target = self.find_best_colony_target(game_state)
            if target:
                self.build_ship('colony')
                return True
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
    def queue_research(self, tech_field):
        if tech_field in self.tech_tree:
            self.research_queue.put(tech_field)

    def set_research_focus(self, tech_field):
        if tech_field not in self.tech_tree:
            return False
        while not self.research_queue.empty():
            try:
                self.research_queue.get_nowait()
            except Exception:
                break
        self.current_research = None
        self.research_progress = 0.0
        self.research_queue.put(tech_field)
        return True

    def process_research(self, dt=1.0):
        if self.current_research is None and not self.research_queue.empty():
            self.current_research = self.research_queue.get()
            self.research_progress = 0.0
        if self.current_research:
            cost = self.get_research_cost(self.current_research)
            if self.research_progress >= cost:
                self.tech_tree[self.current_research] += 1
                self.stats['research_completed'] += 1
                self.current_research = None
                self.research_progress = 0.0

    def get_research_cost(self, tech_field):
        base = {'exploration': 100, 'propulsion': 120, 'weapons': 150,
                'shields': 140, 'sensors': 110, 'construction': 130,
                'ftl': 140}
        return base.get(tech_field, 100) * self.tech_tree.get(tech_field, 1)

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

    # ---------- Diplomacia (bilateral) ----------
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

    # ---------- Status ----------
    def get_status_report(self):
        return {'name': self.name, 'faction_type': self.faction_type.value,
                'resources': dict(self.resources),
                'tech_levels': dict(self.tech_tree),
                'colonies': len(self.colonies), 'ships': len(self.ships),
                'stars_explored': len(self.explored_stars),
                'current_research': self.current_research}

    def stop_faction(self):
        if self.scout_manager:
            self.scout_manager.stop_manager()
        for s in list(self.ships.values()):
            s.stop()
