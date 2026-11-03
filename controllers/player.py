from controllers.base import BaseController
from players.factions import DESIGNS, DiplomacyStatus


class PlayerController(BaseController):
    def __init__(self, faction):
        super().__init__(faction)
        self.selected_star = None
        self.selected_planet = None
        self.selected_ship = None

    def update(self, state, dt):
        if self.faction.eliminated:
            return
        if self.faction.auto_colonize:
            self.faction.auto_expand_step(state)
        if self.faction.auto_habitat:
            self.faction.auto_habitat_step()

    def select(self, star, planet=None):
        self.selected_star = star
        self.selected_planet = planet

    def set_research_weight(self, field, weight):
        return self.faction.set_research_weight(field, weight)

    def reset_research_weights(self):
        self.faction.reset_research_weights()

    def build_ship(self, design_key):
        return self.faction.build_ship(design_key)

    def propose_alliance(self, other):
        return self.faction.propose_alliance(other)

    def propose_trade_offer(self, other):
        return self.faction.propose_trade_offer(other)

    def break_alliance(self, other):
        return self.faction.break_alliance(other)

    def improve_relations(self, other):
        return self.faction.improve_relations(other)

    def offer_treaty(self, other, treaty):
        return self.faction.offer_treaty(other, treaty)

    def send_colony_ship(self, star, planet):
        if planet is None or planet.is_colonized:
            return False
        if planet.name in self.faction.reserved_targets:
            return False
        idle = self.faction.idle_colony_ships()
        if not idle:
            return False
        self.faction.reserved_targets.add(planet.name)
        if idle[0].assign_target(star, planet):
            return True
        self.faction.reserved_targets.discard(planet.name)
        return False

    def has_idle_colony_ship(self):
        return bool(self.faction.idle_colony_ships())

    def build_habitat(self, planet=None):
        return self.faction.build_habitat(planet)

    def can_build_habitat(self, planet):
        return self.faction.can_build_habitat(planet)

    def toggle_auto_colonize(self):
        self.faction.auto_colonize = not self.faction.auto_colonize
        return self.faction.auto_colonize

    def toggle_auto_habitat(self):
        self.faction.auto_habitat = not self.faction.auto_habitat
        return self.faction.auto_habitat

    def pick_shipyard(self, design):
        return self.faction.pick_shipyard(design)

    def declare_war(self, other):
        self.faction.update_diplomacy(other, DiplomacyStatus.WAR)

    def make_peace(self, other):
        self.faction.update_diplomacy(other, DiplomacyStatus.PEACE)

    def respond_to_peace_offer(self, other, accept):
        return self.faction.respond_to_peace_offer(other, accept)

    def respond_to_trade_offer(self, other, accept):
        return self.faction.respond_to_trade_offer(other, accept)
