from dataclasses import dataclass
from typing import Tuple, Dict, List
import math
import threading
import time


SIMULATION_STEP_YEARS = 0.5
SIMULATION_STEP_MONTHS = 0.5
ECONOMIC_RECIPES = {
    'Electronics': {'Minerals': 0.35, 'Energy': 0.3},
    'Chemicals': {'Energy': 0.4, 'Food': 0.15},
    'Alloys': {'Minerals': 0.5, 'Energy': 0.2},
}

PLANET_TYPES = ('terrestrial', 'gas_giant', 'asteroid')

# Multiplicadores de produção por recurso — asteroides são mundos
# mineradores, gigantes gasosos coletores de energia.
TYPE_RESOURCE_YIELDS = {
    'terrestrial': {},
    'asteroid': {'Minerals': 2.6, 'Alloys': 1.5, 'Food': 0.25,
                 'Energy': 0.7, 'Chemicals': 0.6},
    'gas_giant': {'Energy': 3.0, 'Chemicals': 1.6, 'Food': 0.15,
                  'Minerals': 0.25, 'Electronics': 0.5},
}

# (desenvolvimento, população) relativos aos limites terrestres.
TYPE_CAPACITY_SCALE = {
    'terrestrial': (1.0, 1.0),
    'asteroid': (0.6, 0.12),
    'gas_giant': (0.45, 0.05),
}

# A expansão da colônia terraforma qualquer mundo — inclusive
# asteroides e gigantes gasosos. Não há mais ação manual de terraformação.
TYPE_MAX_TERRAFORM = {'terrestrial': 6, 'asteroid': 6, 'gas_giant': 6}

# Período base de 1000 anos para o primeiro nível; cada nível seguinte
# custa metade do tempo do anterior (1000, 500, 250, 125, ...).
TERRAFORM_BASE_YEARS = 1000.0
TERRAFORM_TIER_FACTOR = 0.5
TERRAFORM_SUIT_GAIN = 0.10
TERRAFORM_PRODUCTION_GAIN = 1.08
# A colonização avança a terraformação de 0.2 a 3 anos de progresso por
# ano de jogo conforme a colônia se expande (desenvolvimento + população).
TERRAFORM_RATE_MIN = 0.2
TERRAFORM_RATE_MAX = 3.0
# Mundos naturalmente habitáveis já nasceram metade do caminho: cada ponto
# de habitabilidade natural acelera a terraformação da colônia.
TERRAFORM_HABITABILITY_GAIN = 1.5

# Retrato do planeta: 0 = rocha estéril, 1 = Gaia.
GREENING_BASE = 0.18
GREENING_SUIT_WEIGHT = 0.42
GREENING_EXPANSION_WEIGHT = 0.40

# Foco de cada colônia: como o esforço local é distribuído.
COLONY_FOCUSES = ('balanced', 'industry', 'growth', 'defense', 'science')
FOCUS_EFFECTS = {
    'balanced': {},
    'industry': {'development': 1.30, 'output': 1.15, 'population': 0.85},
    'growth': {'population': 1.35, 'development': 0.85},
    'defense': {'defense': 3.0, 'development': 0.90, 'population': 0.95},
    'science': {'research': 1.30, 'output': 0.90},
}
FOCUS_LABELS = {
    'balanced': 'Equilibrado', 'industry': 'Indústria',
    'growth': 'Crescimento', 'defense': 'Defesa', 'science': 'Ciência',
}


def terraform_years_needed(tier: int) -> float:
    """Anos de progresso necessários para sair do `tier` atual."""
    return TERRAFORM_BASE_YEARS * TERRAFORM_TIER_FACTOR ** max(0, tier)


def greening_from_suitability(suitability) -> float:
    """Retrato mínimo de um mundo apenas pela sua habitabilidade natural."""
    best = max(suitability.values(), default=0.0) if suitability else 0.0
    return min(1.0, max(0.0, GREENING_BASE + GREENING_SUIT_WEIGHT * best))


# 1 unidade de população = 1 milhão de habitantes. A produção é obra do
# trabalho humano: cada pessoa em idade ativa multiplica o rendimento do
# mundo, com retornos levemente decrescentes (escala de produção
# mundial ~ pop^0.75).
POP_MILLIONS = 1_000_000.0
WORK_PRODUCTIVITY = 0.02
WORK_EXPONENT = 0.75
POP_FOOD_PER_YEAR = 0.0025  # unidades de alimento por milhão de pessoas

HABITAT_MAX_PER_PLANET = 10
HABITAT_POP_BONUS = 0.12     # +12% teto de população por habitat
HABITAT_DEV_BONUS = 0.08     # +8% teto de desenvolvimento por habitat
HABITAT_OUTPUT_BONUS = 0.05  # +5% produção por habitat

# Requisito de cada colônia vem da sua própria produção: manter a base
# industrial ativa queima insumos na proporção do que ela rende.
MAINTENANCE_INTENSITY = {
    'Energy': 0.10, 'Chemicals': 0.03, 'Electronics': 0.02, 'Alloys': 0.015,
}
RESERVE_YEARS = 2.0      # estoque-alvo: anos de consumo que a colônia quer ter
STORAGE_FILL_TARGET = 0.10  # piso de enchimento dos armazéns
SUPPLY_STRAIN_PENALTY = 0.35  # perda de produção quando falta insumo
MAX_BUILD_QUEUE = 12     # obras enfileiradas por colônia
BUILD_DELIVERY_YEARS = 2.0  # prazo em que uma carga precisa chegar para a obra


def planet_label_for(planet_type: str) -> str:
    return {'terrestrial': 'mundo terrestre',
            'gas_giant': 'gigante gasoso',
            'asteroid': 'asteroide'}.get(planet_type, 'mundo')


def format_population(population) -> str:
    """Formata unidades de população (1 = 1 milhão) em PT-BR."""
    persons = max(0.0, float(population)) * POP_MILLIONS
    if persons >= 1e12:
        return f"{persons / 1e12:.2f} tri"
    if persons >= 1e9:
        return f"{persons / 1e9:.2f} bi"
    if persons >= 1e6:
        return f"{persons / 1e6:.1f} mi"
    if persons >= 1e3:
        return f"{persons / 1e3:.0f} mil"
    return f"{persons:.0f}"


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
    planet_type: str = 'terrestrial'


    def post_init(self):
        self.developement = 0.1
        self.can_build_ships = True
        self.lock = threading.Lock()
        self.population = 0
        self.storage_capacity = {
            'Minerals': 10_000, 'Food': 5_000, 'Energy': 10_000,
            'Electronics': 2_000, 'Chemicals': 2_000, 'Alloys': 1_000,
            'Credits': 10_000, 'Research': float('inf'),
        }
        self.faction = None
        self.ships = []
        self.parent_star = None
        self.terraform_level = 0
        self.terraform_progress = 0.0
        self.max_terraform_level = TYPE_MAX_TERRAFORM.get(
            self.planet_type, 6)
        # Habitabilidade natural, capturada antes de qualquer ganho de nível:
        # define quanto mais rápido um mundo já habitável chega a Gaia.
        self.base_suitability = max(
            self.life_suitability.values(), default=0.0)
        self.focus = 'balanced'
        self.build_queue = []
        self.building_task = None
        self.active_ship_builds = []
        self.defense = 0.0
        self.max_defense = 100.0
        self.has_rings = False
        self.habitats = 0
        self.habitat_building = False
        self.famine = 0.0
        self.supply_strain = 0.0
        if self.planet_type == 'asteroid':
            self.storage_capacity['Minerals'] = 30_000
            self.storage_capacity['Alloys'] = 4_000
            self.storage_capacity['Food'] = 2_500
        elif self.planet_type == 'gas_giant':
            self.storage_capacity['Energy'] = 30_000
            self.storage_capacity['Chemicals'] = 6_000
            self.storage_capacity['Food'] = 1_500
        for k in ('Minerals', 'Food', 'Energy', 'Electronics',
                  'Chemicals', 'Alloys', 'Research'):
            self.planet_resources.setdefault(k, 0.0)

    def get_suitability(self, faction) -> float:
        key = faction.faction_type.value if hasattr(faction, 'faction_type') else None
        if key and key in self.life_suitability:
            return self.life_suitability[key]
        return 0.0

    def _compute_caps(self):
        """Teto de desenvolvimento e população por nível de expansão."""
        tier = min(getattr(self, 'terraform_level', 0), 5)
        caps = [(3.0, 6_000), (7.0, 10_000), (14.0, 20_000), (25.0, 50_000), (50.0, 100_000), (75.0, 1_000_000)]
        max_dev, max_pop = caps[tier]
        dev_scale, pop_scale = TYPE_CAPACITY_SCALE.get(
            getattr(self, 'planet_type', 'terrestrial'), (1.0, 1.0))
        habitats = getattr(self, 'habitats', 0)
        if habitats:
            faction = getattr(self, 'faction', None)
            wonders = getattr(faction, 'wonders', set())
            habitat_scale = 1.25 if 'habitat' in wonders else 1.0
            max_dev *= 1.0 + HABITAT_DEV_BONUS * habitat_scale * habitats
            max_pop *= 1.0 + HABITAT_POP_BONUS * habitat_scale * habitats
        return max_dev * dev_scale, max_pop * pop_scale

    def expansion_ratio(self) -> float:
        """Quão cheia a colônia está (0 vazio → 1 saturada)."""
        max_dev, max_pop = self._compute_caps()
        dev_share = min(1.0, self.developement / max(1e-6, max_dev))
        pop_share = min(1.0, self.population / max(1e-6, max_pop))
        return 0.5 * dev_share + 0.5 * pop_share

    def expansion_info(self) -> dict:
        """Progresso da terraformação automática por expansão."""
        level = int(getattr(self, 'terraform_level', 0))
        max_level = int(getattr(self, 'max_terraform_level', 6))
        progress = float(getattr(self, 'terraform_progress', 0.0))
        rate = self.expansion_rate()
        if level >= max_level:
            return {'level': level, 'max': max_level, 'years_left': 0.0,
                    'percent': 1.0, 'needed': 0.0, 'rate': rate,
                    'eta_years': 0.0}
        needed = terraform_years_needed(level)
        remaining = max(0.0, needed - progress)
        return {'level': level, 'max': max_level,
                'years_left': remaining,
                'percent': min(1.0, progress / needed), 'needed': needed,
                'rate': rate,
                'eta_years': (remaining / rate) if rate > 0 else float('inf')}

    def expansion_rate(self) -> float:
        """Anos de progresso terraformador por ano de jogo, no mundo atual."""
        ratio = self.expansion_ratio()
        return ((TERRAFORM_RATE_MIN
                 + (TERRAFORM_RATE_MAX - TERRAFORM_RATE_MIN) * ratio)
                * self.habitability_factor())

    def habitability_factor(self) -> float:
        """Mundos já habitáveis terraformam mais rápido."""
        return 1.0 + TERRAFORM_HABITABILITY_GAIN * min(
            1.0, max(0.0, float(getattr(self, 'base_suitability', 0.0))))

    def terraforming_stage(self) -> float:
        """Retrato do mundo: 0 = rocha estéril, 1 = Gaia."""
        max_level = max(1, int(getattr(self, 'max_terraform_level', 6)))
        level = min(int(getattr(self, 'terraform_level', 0)), max_level)
        if level >= max_level:
            tier = 1.0
        else:
            needed = terraform_years_needed(level)
            tier = (level + min(
                1.0, float(getattr(self, 'terraform_progress', 0.0))
                / max(1e-6, needed))) / max_level
        suit = max(self.life_suitability.values(), default=0.0)
        return min(1.0, max(0.0, GREENING_BASE
                            + GREENING_SUIT_WEIGHT * suit
                            + GREENING_EXPANSION_WEIGHT * tier))

    def focus_effects(self) -> dict:
        return FOCUS_EFFECTS.get(getattr(self, 'focus', 'balanced'), {})

    def set_focus(self, focus) -> bool:
        if focus not in COLONY_FOCUSES:
            return False
        self.focus = focus
        return True

    def growth_projection(self) -> dict:
        """Projeção simples de crescimento para o planejador de colônias."""
        max_dev, max_pop = self._compute_caps()
        effects = self.focus_effects()
        growth_rate = 0.03 * effects.get('population', 1.0)
        if self.faction is not None:
            growth_rate *= self.faction.population_growth_multiplier
        growth_rate *= 1.0 - 0.75 * getattr(self, 'famine', 0.0)
        headroom_pop = max(0.0, max_pop - self.population)
        years_to_cap = float('inf')
        if growth_rate > 0 and 0 < self.population < max_pop:
            years_to_cap = (math.log(max_pop / self.population)
                            / math.log(1.0 + growth_rate))
        return {
            'max_pop': max_pop, 'max_dev': max_dev,
            'pop_growth_rate': growth_rate,
            'years_to_pop_cap': years_to_cap,
            'pop_headroom': headroom_pop,
            'food_balance': self.food_balance(),
        }

    def food_balance(self) -> float:
        """Alimento produzido menos consumido, em unidades por ano."""
        yearly = self.annual_output() * self.focus_effects().get(
            'output', 1.0)
        yield_rate = yearly * TYPE_RESOURCE_YIELDS.get(
            self.planet_type, {}).get('Food', 1.0)
        demand = POP_FOOD_PER_YEAR * max(0.0, self.population)
        return yield_rate - demand

    def resource_output(self) -> dict:
        """Produção anual estimada de cada recurso, já com o foco aplicado."""
        yearly = self.annual_output() * self.focus_effects().get(
            'output', 1.0)
        yields = TYPE_RESOURCE_YIELDS.get(self.planet_type, {})
        return {resource: yearly * yields.get(resource, 1.0)
                for resource in self.planet_resources}

    def population_demand(self) -> float:
        return POP_FOOD_PER_YEAR * max(0.0, self.population)

    def maintenance_demand(self) -> dict:
        """Insumos que a base industrial consome por ano, dados pela produção."""
        output = self.annual_output() * self.focus_effects().get(
            'output', 1.0)
        return {resource: output * intensity
                for resource, intensity in MAINTENANCE_INTENSITY.items()
                if resource in self.planet_resources}

    def consumption(self) -> dict:
        """Requisito anual da colônia: manutenção industrial e alimento."""
        demand = dict(self.maintenance_demand())
        food = self.population_demand()
        if food > 0.0:
            demand['Food'] = demand.get('Food', 0.0) + food
        return demand

    def target_stock(self) -> dict:
        """Estoque-alvo: anos de consumo, nunca abaixo do piso de armazém."""
        targets = {}
        for resource, amount in self.consumption().items():
            reserve = amount * RESERVE_YEARS
            cap = self.storage_capacity.get(resource, 0.0)
            if math.isfinite(cap) and cap > 0.0:
                reserve = min(
                    cap, max(reserve, cap * STORAGE_FILL_TARGET))
            targets[resource] = reserve
        return targets

    def build_requirement(self) -> dict:
        """Recursos que as obras ainda na fila vão exigir neste mundo."""
        total = {}
        for task in self.build_queue:
            for resource, amount in (task.get('cost') or {}).items():
                if resource in self.planet_resources:
                    total[resource] = total.get(resource, 0.0) + amount
        return total

    def blocked_need(self) -> dict:
        """Falta das obras travadas, já descontando o que o mundo produz.

        Medida pela maior obra parada, não pela fila inteira: o que a colônia
        faz sozinha dentro do prazo não precisa chegar de outro lugar.
        """
        yearly = self.resource_output()
        need = {}
        for task in self.build_queue:
            for resource, missing in self.task_shortfall(task).items():
                gap = max(
                    0.0,
                    missing - yearly.get(resource, 0.0) * BUILD_DELIVERY_YEARS)
                if gap > need.get(resource, 0.0):
                    need[resource] = gap
        return need

    def import_need(self, inbound=None) -> dict:
        """Quanto falta chegar para manter reservas e obras paradas."""
        targets = self.target_stock()
        yearly = self.resource_output()
        needed = {
            resource: max(
                0.0,
                target - self.planet_resources.get(resource, 0.0)
                - yearly.get(resource, 0.0) * RESERVE_YEARS)
            for resource, target in targets.items()}
        for resource, gap in self.blocked_need().items():
            needed[resource] = max(needed.get(resource, 0.0), gap)
        for resource, incoming in (inbound or {}).items():
            if resource in needed:
                needed[resource] = max(
                    0.0, needed[resource] - incoming)
        return {resource: amount for resource, amount in needed.items()
                if amount > 1e-6}

    def export_surplus(self) -> dict:
        """O que o mundo pode emprestar sem furar suas reservas nem suas obras."""
        reserve = self.target_stock()
        claim = self.build_requirement()
        surplus = {}
        for resource, stored in self.planet_resources.items():
            keep = max(reserve.get(resource, 0.0), claim.get(resource, 0.0))
            available = stored - keep
            if available > 1e-6:
                surplus[resource] = available
        return surplus

    def awaiting_resources(self) -> dict:
        """Custo ainda não pago da primeira obra bloqueada da fila."""
        for task in self.build_queue:
            missing = self.task_shortfall(task)
            if missing:
                return {'label': task.get('label', 'obra'),
                        'missing': missing,
                        'since': float(task.get('queued_at', 0.0))}
        return {}

    def task_shortfall(self, task) -> dict:
        """O que falta neste mundo para a obra poder começar."""
        return {resource: amount - self.planet_resources.get(resource, 0.0)
                for resource, amount in (task.get('cost') or {}).items()
                if amount > self.planet_resources.get(resource, 0.0)}

    def _consume_maintenance(self, step_scale: float):
        """Queima os insumos da produção e mede o desabastecimento local."""
        required = {resource: amount * step_scale
                    for resource, amount in self.maintenance_demand().items()}
        total = sum(required.values())
        if total <= 0.0:
            self.supply_strain = 0.0
            return
        unmet = 0.0
        for resource, amount in required.items():
            stored = self.planet_resources.get(resource, 0.0)
            burnt = min(stored, amount)
            self.planet_resources[resource] = stored - burnt
            unmet += amount - burnt
        self.supply_strain = min(1.0, unmet / total)

    def _advance_expansion(self, years: float, wonder_bonus: float = 1.0):
        """A colonização avança a terraformação; níveis sobem sozinhos."""
        if self.terraform_level >= self.max_terraform_level:
            self.terraform_progress = 0.0
            return
        self.terraform_progress += years * self.expansion_rate() * wonder_bonus
        while (self.terraform_progress >=
               terraform_years_needed(self.terraform_level)
               and self.terraform_level < self.max_terraform_level):
            self.terraform_progress -= terraform_years_needed(
                self.terraform_level)
            self.terraform_level += 1
            for key in list(self.life_suitability.keys()):
                self.life_suitability[key] = min(
                    1.0, self.life_suitability[key] + TERRAFORM_SUIT_GAIN)
            self.production *= TERRAFORM_PRODUCTION_GAIN
            game_state = getattr(self.faction, 'game_state', None)
            if game_state is not None and self.faction is not None:
                game_state.log_event(
                    f"{self.faction.name}: {self.name} atingou nível "
                    f"{self.terraform_level} de expansão "
                    f"({planet_label_for(self.planet_type)})")

    def annual_output(self) -> float:
        """Unidades/ano estimadas para o mundo atual (índice realista)."""
        if self.faction is None:
            return 0.0
        return (self.production * self.developement
                * self._workforce_factor() * 2.0
                * self.faction.economy_multiplier)

    def _workforce_factor(self) -> float:
        habitats = getattr(self, 'habitats', 0)
        factor = 1.0 + (WORK_PRODUCTIVITY
                        * max(0.0, self.population) ** WORK_EXPONENT)
        if habitats:
            factor *= 1.0 + HABITAT_OUTPUT_BONUS * habitats
        return factor

    def capacity_info(self) -> dict:
        max_dev, max_pop = self._compute_caps()
        return {
            'max_dev': max_dev,
            'max_pop': max_pop,
            'dev_capped': self.developement >= max_dev - 1e-6,
            'pop_capped': self.population >= max_pop - 1e-6,
        }

    def develop(self, dt: float = SIMULATION_STEP_MONTHS):
        step_scale = dt / (12.0 * SIMULATION_STEP_YEARS)
        years = dt / 12.0
        game_state = getattr(self.faction, 'game_state', None)
        economic_mode = (
            game_state is not None
            and game_state.victory_mode == 'economic')
        development_rate = 0.035
        if economic_mode:
            construction = self.faction.tech_tree.get('construction', 1)
            trade_partners = sum(
                'trade' in treaties
                for treaties in self.faction.treaties.values())
            development_rate = (
                0.02
                + min(0.02, max(0, construction - 1) * 0.002)
                + min(0.01, trade_partners * 0.002))
        famine = getattr(self, 'famine', 0.0)
        effects = self.focus_effects()
        development_rate *= (1.0 - 0.6 * famine) * effects.get(
            'development', 1.0)
        growth_factor = (1.0 + development_rate) ** step_scale
        max_dev, max_pop = self._compute_caps()

        if self.developement < max_dev:
            self.developement = min(max_dev,
                                    self.developement * growth_factor)
        if self.population < max_pop:
            if (self.faction is not None and game_state is not None
                    and game_state.victory_mode == 'expansion'):
                growth_rate = 0.01 + max(
                    0, self.faction.tech_tree.get('biotech', 1) - 1) * 0.008
            else:
                growth_rate = 0.03
            if self.faction is not None:
                growth_rate *= self.faction.population_growth_multiplier
            growth_rate *= (effects.get('population', 1.0)
                            * (1.0 - 0.75 * famine))
            if famine >= 1.0:
                # Inanição: a população encolhe ~0.6%/ano
                growth_rate = -0.006
            population_growth = (1.0 + growth_rate) ** step_scale
            self.population = min(
                max_pop, self.population * population_growth)

        # Libera construção assim que a colônia cresce um pouco
        if self.developement > 0.3:
            self.can_build_ships = True

        # Regen de defesa
        if (self.is_colonized and self.max_defense > 0
                and self.defense < self.max_defense):
            self.defense = min(
                self.max_defense,
                self.defense + 1.5 * self.developement * step_scale
                * effects.get('defense', 1.0))

        # Terraformação automática por expansão da colônia.
        wonders = getattr(self.faction, 'wonders', set()) if (
            self.faction is not None) else set()
        wonder_bonus = 1.25 if 'terraforming' in wonders else 1.0
        self._advance_expansion(years, wonder_bonus)

        self.const()
        self._advance_ship_builds()
        self.produce(step_scale)

    def _advance_ship_builds(self):
        """Conclui obras de nave cujo prazo (em tempo de jogo) venceu."""
        if not self.active_ship_builds:
            return
        game_state = getattr(self.faction, 'game_state', None)
        if game_state is None:
            return
        now = game_state.time
        for task in list(self.active_ship_builds):
            if task.get('cancelled'):
                self.active_ship_builds.remove(task)
                continue
            if now >= task.get('build_deadline', now):
                self._build_ship(task)

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

    def queue_task(self, task: dict) -> dict:
        """Enfileira uma obra; ela espera recursos, não é barrada por eles."""
        task.setdefault('id', f"{self.name}:{len(self.build_queue)}")
        task.setdefault(
            'queued_at',
            getattr(getattr(self.faction, 'game_state', None), 'time', 0.0))
        self.build_queue.append(task)
        return task

    def queued_tasks(self):
        return list(self.build_queue)

    def queue_is_full(self) -> bool:
        return len(self.build_queue) >= MAX_BUILD_QUEUE

    def cancel_queued(self, task) -> bool:
        """Remove uma obra da fila; nada foi pago ainda, então nada devolve."""
        if task is None or task not in self.build_queue:
            return False
        self.build_queue.remove(task)
        task['cancelled'] = True
        if task.get('kind') == 'habitat':
            self.habitat_building = False
        return True

    def clear_build_queue(self):
        """Esquece as obras pendentes — usado quando a colônia muda de dono."""
        for task in self.build_queue:
            task['cancelled'] = True
        self.build_queue.clear()

    def building_progress(self) -> dict:
        """Obra em execução: rótulo e anos de jogo restantes."""
        task = getattr(self, 'building_task', None)
        if not task:
            return {}
        state = getattr(self.faction, 'game_state', None) if (
            self.faction is not None) else None
        started = float(task.get('started_at', 0.0))
        duration = float(task.get('build_time', 0.0))
        smooth = getattr(state, 'smooth_time', None)
        now = smooth() if callable(smooth) else getattr(
            state, 'time', started + duration)
        remaining = max(0.0, started + duration - now)
        return {'label': task.get('label', 'obra'),
                'years_left': remaining / 12.0,
                'months_left': remaining,
                'percent': (min(1.0, max(0.0, (now - started) / duration))
                            if duration > 0 else 1.0),
                'kind': task.get('kind', 'ship')}

    def const(self):
        """Inicia a primeira obra da fila que o mundo já possa pagar.

        O custo é pago aqui, não no enfileiramento: uma obra pedida a uma
        colônia pobre entra na fila e espera a carga chegar de outra colônia.
        """
        if self.faction is None or self.queue_is_full():
            return
        for task in list(self.build_queue):
            if task.get('cancelled'):
                self.build_queue.remove(task)
                continue
            cost = task.get('cost') or {}
            if not self.pay_cost(cost):
                task['awaiting'] = self.task_shortfall(task)
                continue
            task.pop('awaiting', None)
            self._start_task(task)

    def _start_task(self, task):
        try:
            self.build_queue.remove(task)
        except ValueError:
            pass
        task['started_at'] = getattr(
            self.faction.game_state, 'time', 0.0)
        self.building_task = task
        if task.get('kind') == 'habitat':
            threading.Thread(target=self._build_habitat, args=(task,),
                             daemon=True).start()
            return
        # Construção de nave: concluída pelo relógio do jogo em develop(),
        # não por uma thread que dorme build_time e disputa o GIL.
        state = getattr(self.faction, 'game_state', None)
        if state is None:
            self._build_ship(task)
            return
        task['build_deadline'] = task['started_at'] + float(
            task.get('build_time', 5))
        self.active_ship_builds.append(task)

    def _finish_task(self, task):
        """Esquece a obra concluída para o painel não mostrá-la como ativa."""
        if getattr(self, 'building_task', None) is task:
            self.building_task = None

    def _build_habitat(self, task):
        try:
            build_time = float(task.get('build_time', 18))
            state = getattr(self.faction, 'game_state', None)
            if state is not None:
                t0 = state.time
                while state.time - t0 < build_time:
                    if self.faction is None or self.faction.eliminated:
                        return
                    time.sleep(0.05)
            else:
                time.sleep(min(1.0, build_time))
            if self.faction is None or self.faction.eliminated:
                return
            if (self.faction is not task.get('faction')
                    or not self.is_colonized):
                return
            if self.habitats < HABITAT_MAX_PER_PLANET:
                self.habitats += 1
                self.habitat_building = False
                if state is not None:
                    state.log_event(
                        f"{self.faction.name}: habitat orbital concluído "
                        f"em {self.name} ({self.habitats}/"
                        f"{HABITAT_MAX_PER_PLANET})")
            else:
                self.habitat_building = False
        except Exception as e:
            self.habitat_building = False
            print(f"[{self.name}] erro construindo habitat: {e}")
        finally:
            self._finish_task(task)

    def _build_ship(self, task):
        try:
            from players.factions import DESIGNS
        except Exception:
            return
        try:
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
        finally:
            if task in self.active_ship_builds:
                self.active_ship_builds.remove(task)
            self._finish_task(task)

    def produce(self, step_scale: float = 1.0):
        if self.faction is None:
            return
        effects = self.focus_effects()
        strain = 1.0 - SUPPLY_STRAIN_PENALTY * getattr(
            self, 'supply_strain', 0.0)
        prod = (
            self.production * self.developement * step_scale
            * self.faction.economy_multiplier * self._workforce_factor()
            * effects.get('output', 1.0) * strain)
        yields = TYPE_RESOURCE_YIELDS.get(self.planet_type, {})
        game_state = getattr(self.faction, 'game_state', None)
        economic_mode = (
            game_state is not None
            and game_state.victory_mode == 'economic')
        manufacturing_efficiency = 1.0
        if economic_mode:
            construction = self.faction.tech_tree.get('construction', 1)
            manufacturing_efficiency += min(
                0.45, max(0, construction - 1) * 0.05)
        for resource in list(self.planet_resources.keys()):
            rate = prod * yields.get(resource, 1.0)
            if resource == 'Research':
                self.faction.add_research_income(
                    rate * effects.get('research', 1.0))
                continue
            if resource == 'Credits':
                continue

            cap = self.storage_capacity.get(resource, 0)
            if economic_mode and resource in ECONOMIC_RECIPES:
                recipe = ECONOMIC_RECIPES[resource]
                output = min(
                    rate * manufacturing_efficiency,
                    max(0.0, cap - self.planet_resources[resource]))
                for ingredient, units_per_output in recipe.items():
                    output = min(
                        output,
                        self.planet_resources.get(ingredient, 0.0)
                        / units_per_output)
                for ingredient, units_per_output in recipe.items():
                    self.planet_resources[ingredient] -= (
                        output * units_per_output)
                self.planet_resources[resource] += output
                continue

            if resource == 'Food':
                # Produção primeiro (limitada ao cap)
                if self.planet_resources[resource] < cap:
                    room = cap - self.planet_resources[resource]
                    self.planet_resources[resource] += min(rate, room)
                # Consumo: 0.0025 un/ano por milhão de habitantes
                demand = POP_FOOD_PER_YEAR * max(
                    0.0, self.population) * step_scale * 0.5
                self.planet_resources[resource] -= demand
                if self.planet_resources[resource] < 0:
                    deficit = -self.planet_resources[resource]
                    self.planet_resources[resource] = 0.0
                    # Fome: razão entre déficit e demanda — penaliza o
                    # crescimento em develop(), não mata por pop kill.
                    self.famine = (
                        1.0 if demand <= 0
                        else min(1.0, deficit / demand))
                else:
                    self.famine = 0.0
                continue

            if self.planet_resources[resource] >= cap:
                continue
            self.planet_resources[resource] += rate

        self._consume_maintenance(step_scale)

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
