from controllers.base import BaseController
from players.factions import DiplomacyStatus, DESIGNS
from players.ships import Warship


class AIController(BaseController):
    def __init__(self, faction, aggression=0.4, think_interval=1.5):
        super().__init__(faction)
        self.aggression = aggression
        self.think_interval = think_interval
        self.timer = 0.0
        faction.auto_colonize = True
        faction.auto_terraform = True

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
            self.faction.auto_terraform_step()
            self.faction.auto_expand_step(state)
            self._manage_fleet(state)
            self._manage_diplomacy(state)

    
    def _manage_research(self, state):
        f = self.faction
        aggression_bonus = int(3 * self.aggression)
        base_priority = {
            'exploration': 10, 'propulsion': 9, 'ftl': 9,
            'sensors': 7, 'construction': 6, 'shields': 5,
            'weapons': 4 + aggression_bonus,
        }
        priorities = {}
        for field in f.tech_tree:
            if f.is_tech_capped(field):
                f.research_weights[field] = 0.0
                continue
            priorities[field] = base_priority.get(field, 5) - f.tech_tree[field]

        if not priorities:
            return
        min_p = min(priorities.values())
        for field, p in priorities.items():
            f.research_weights[field] = max(0.5, p - min_p + 1.0)

    def _manage_scouts(self, state):
        f = self.faction
        if not f.scout_manager:
            return
        max_scouts = 3 + f.tech_tree['exploration']
        if len(f.scout_manager.active_scouts) < max_scouts:
            f.build_ship('scout')

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
        my_power = f.compute_strength()['total']
        at_war = len(f.war_declarations) > 0

        for other in state.factions:
            if other is f or other.eliminated:
                continue
            status = f.diplomacy.get(other.name, DiplomacyStatus.NEUTRAL)
            if status in (DiplomacyStatus.WAR, DiplomacyStatus.ALLY):
                continue  # não mexe em guerra nem aliança existente

            their_power = other.compute_strength()['total']

            # Buscar aliança se em guerra e o outro é mais forte
            if at_war and their_power > my_power * 1.1:
                f.propose_alliance(other)
                continue

            # Declarar guerra com vantagem esmagadora
            ratio = (my_power + 1) / (their_power + 1)
            if ratio > 2.0 and self.aggression > 0.7 and not at_war:
                f.update_diplomacy(other, DiplomacyStatus.WAR)
