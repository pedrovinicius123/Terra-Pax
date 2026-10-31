from controllers.base import BaseController
from players.factions import DESIGNS


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

    def select(self, star, planet=None):
        self.selected_star = star
        self.selected_planet = planet

    def set_research(self, tech):
        return self.faction.set_research_focus(tech)

    def build_ship(self, design_key):
        return self.faction.build_ship(design_key)

    def send_colony_ship(self, star, planet):
        if planet is None or planet.is_colonized:
            return False
        idle = self.faction.idle_colony_ships()
        if not idle:
            return False
        return idle[0].assign_target(star, planet)

    def has_idle_colony_ship(self):
        return bool(self.faction.idle_colony_ships())

    def terraform(self):
        f = self.faction
        if f.resources.get('Minerals', 0) < 400:
            return
        for p in f.colonies.copy().values():
            if f.can_terraform(p):
                f.terraform(p)
                break

    def toggle_auto_colonize(self):
        self.faction.auto_colonize = not self.faction.auto_colonize
        return self.faction.auto_colonize

    def declare_war(self, other):
        from players.factions import DiplomacyStatus
        self.faction.update_diplomacy(other, DiplomacyStatus.WAR)

    def make_peace(self, other):
        from players.factions import DiplomacyStatus
        self.faction.update_diplomacy(other, DiplomacyStatus.PEACE)

