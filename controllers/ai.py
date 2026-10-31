from controllers.base import BaseController
from players.factions import DiplomacyStatus, DESIGNS
from players.ships import Warship


class AIController(BaseController):
    def __init__(self, faction, aggression=0.4, think_interval=1.5):
        super().__init__(faction)
        self.aggression = aggression
        self.think_interval = think_interval
        self.timer = 0.0
        self.faction.auto_colonize = True

    def update(self, state, dt):
        if self.faction.eliminated:
            return
        self.timer += dt
        if self.timer < self.think_interval:
            return
        self.timer = 0.0
        with state.lock:
            self._manage_research(state)
            self._manage_scouts(state)
            self._manage_terraforming(state)
            self.faction.auto_expand_step(state)
            self._manage_fleet(state)
            self._manage_diplomacy(state)

    def _manage_research(self, state):
        f = self.faction
        if f.current_research is not None or not f.research_queue.empty():
            return
        priorities = {
            'exploration': 10 - f.tech_tree['exploration'],
            'propulsion': 9 - f.tech_tree['propulsion'],
            'ftl': 9 - f.tech_tree['ftl'],
            'sensors': 7 - f.tech_tree['sensors'],
            'construction': 6 - f.tech_tree['construction'],
            'shields': 5 - f.tech_tree['shields'],
            'weapons': 4 + int(3 * self.aggression) - f.tech_tree['weapons'],
        }
        f.queue_research(max(priorities, key=priorities.get))

    def _manage_scouts(self, state):
        f = self.faction
        if not f.scout_manager:
            return
        max_scouts = 3 + f.tech_tree['exploration']
        if len(f.scout_manager.active_scouts) < max_scouts:
            f.build_ship('scout')

    def _manage_terraforming(self, state):
        f = self.faction
        if f.resources.get('Minerals', 0) < 400:
            return
        for p in f.colonies.copy().values():
            if f.can_terraform(p):
                f.terraform(p)
                break

    def _manage_fleet(self, state):
        f = self.faction
        if len(f.colonies) >= 2:
            has_transport = any(s.design_key == 'transport'
                                for s in f.ships.values())
            if not has_transport and f.can_afford(DESIGNS['transport']['cost']):
                f.build_ship('transport')
        warships = [s for s in f.ships.values() if isinstance(s, Warship)]
        at_war = bool(f.war_declarations)
        desired = int(1 + self.aggression * 4
                      + f.tech_tree['weapons'] + (3 if at_war else 0))
        if len(warships) < desired:
            for key in ('cruiser', 'destroyer', 'corvette'):
                if f.can_afford(DESIGNS[key]['cost']):
                    f.build_ship(key)
                    break

    def _manage_diplomacy(self, state):
        f = self.faction
        for other in state.factions:
            if other is f or other.eliminated:
                continue
            status = f.diplomacy.get(other.name, DiplomacyStatus.NEUTRAL)
            if status == DiplomacyStatus.WAR:
                continue  # não faz paz sozinha
            if status == DiplomacyStatus.ALLY:
                continue
            ratio = (len(f.ships) + 1) / (len(other.ships) + 1)
            if ratio > 2.5 and self.aggression > 0.7:
                f.update_diplomacy(other, DiplomacyStatus.WAR)
