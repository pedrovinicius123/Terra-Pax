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
        faction.auto_habitat = True

    def update(self, state, dt):
        if self.faction.eliminated:
            return
        self.timer += dt
        if self.timer < self.think_interval:
            return
        self.timer = 0.0
        with state.lock:
            self._manage_research(state)
            self._manage_wonders(state)
            self._manage_scouts(state)
            self.faction.auto_habitat_step()
            self.faction.auto_expand_step(state)
            self._manage_fleet(state)
            self._manage_diplomacy(state)

    
    def _manage_research(self, state):
        f = self.faction
        aggression_bonus = int(3 * self.aggression)
        base_priority = {
            'exploration': 10, 'propulsion': 9, 'ftl': 9,
            'sensors': 7, 'construction': 6, 'shields': 5,
            'weapons': 4 + aggression_bonus, 'biotech': 6,
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

    def _manage_wonders(self, state):
        wonder = {
            'diplomatic': 'diplomatic',
            'domination': 'domination',
            'economic': 'economic',
            'expansion': 'expansion',
            'scientific': 'scientific',
            'terraforming': 'terraforming',
            'habitat': 'habitat',
            'standard': 'standard',
            'any': 'standard',
        }.get(state.victory_mode)
        if wonder is not None and wonder not in state.wonders_built:
            self.faction.build_wonder(wonder)

    def _manage_scouts(self, state):
        f = self.faction
        if not f.scout_manager:
            return
        max_scouts = 3 + f.tech_tree['exploration']
        planned = len(f.scout_manager.active_scouts) + f.queued_ship_count(
            'scout')
        if planned < max_scouts:
            f.build_ship('scout')

    def _manage_fleet(self, state):
        f = self.faction
        warships = [s for s in f.ships.values() if isinstance(s, Warship)]
        pending = sum(f.queued_ship_count(key) for key in (
            'dreadnought', 'battleship', 'cruiser', 'destroyer', 'frigate',
            'corvette'))
        at_war = bool(f.war_declarations)
        desired = int(1 + self.aggression * 4
                      + f.tech_tree['weapons'] + (3 if at_war else 0))
        if len(warships) + pending >= desired:
            return
        for key in (
                'dreadnought', 'battleship', 'cruiser', 'destroyer',
                'frigate', 'corvette'):
            if f.can_fund(DESIGNS[key]['cost']):
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
            their_power = other.compute_strength()['total']
            relation = f.get_relation(other)

            if status == DiplomacyStatus.WAR:
                if relation < 35 and their_power > my_power * 1.1:
                    relation = f.adjust_relation(other, 1)
                if (relation >= 35 and their_power > my_power * 1.1
                        and other.name not in other.declined_peace_offers):
                    if other.is_human:
                        f.propose_peace(other)
                    else:
                        f.update_diplomacy(other, DiplomacyStatus.PEACE)
                continue

            if status == DiplomacyStatus.ALLY:
                continue

            # Buscar apoio diplomático contra adversários mais fortes.
            if at_war and their_power > my_power * 1.1 and f.propose_alliance(other):
                continue

            alliance_threshold = (
                85 if state.victory_mode == 'diplomatic' else 70)
            if (self.aggression < 0.7 or state.victory_mode == 'diplomatic') and relation < alliance_threshold:
                relation = f.adjust_relation(other, 1)
            if relation >= 45:
                f.offer_treaty(other, 'non_aggression')
            if relation >= 55:
                f.propose_trade_offer(other)
            if (relation >= alliance_threshold
                    and f.has_treaty(other, 'trade')):
                f.propose_alliance(other)

            # Declarar guerra com vantagem esmagadora
            ratio = (my_power + 1) / (their_power + 1)
            if ratio > 2.0 and self.aggression > 0.7 and not at_war:
                f.update_diplomacy(other, DiplomacyStatus.WAR)
