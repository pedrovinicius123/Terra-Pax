import threading
import time
import math
from queue import Empty

from players.factions import DiplomacyStatus
from players.ships import Warship


class GameState:
    START_YEAR = 2150
    MONTH_NAMES = (
        "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
        "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
    )
    VICTORY_MODES = {
        "diplomatic": "Diplomática",
        "domination": "Dominação",
        "economic": "Econômica",
        "expansion": "Expansão",
        "scientific": "Científica",
        "terraforming": "Ecopoese",
        "habitat": "Habitação Orbital",
        "standard": "Padrão",
        "any": "Todas as Condições",
    }
    # Soma de níveis de expansão (terraformação) necessária para Ecopoese.
    TERRAFORM_VICTORY_TIERS = 12
    # Total de habitats orbitais necessários para Habitação Orbital.
    HABITAT_VICTORY_COUNT = 24

    def __init__(self, map_G, stars, factions, tick_interval=0.5,
                 victory_mode="standard"):
        if victory_mode not in self.VICTORY_MODES:
            raise ValueError(f"Modo de vitória inválido: {victory_mode}")
        self.event_log = []
        self.map_G = map_G
        self.stars = stars
        self.factions = factions
        self.victory_mode = victory_mode
        self.stars_by_name = {s.name: s for s in stars}
        self.time = 0.0
        self.speed = 1.0
        self.paused = False
        self.running = False
        self.game_over = False
        self.winner = None
        self.winner_condition = None
        self.wonders_built = {}
        self.tick_interval = tick_interval
        self.lock = threading.RLock()
        self._thread = None
        for f in factions:
            f.game_state = self

    @property
    def year(self):
        return self.START_YEAR + math.floor(
            (self.time + 1e-9) / 12)

    @property
    def month_index(self):
        return math.floor(self.time + 1e-9) % 12

    @property
    def month(self):
        return self.MONTH_NAMES[self.month_index]

    @property
    def date(self):
        return f"{self.month} {self.year}"

    def log_event(self, msg):
        self.event_log.append((self.time, msg))
        print(f"[{self.date}] {msg}")
        
    def start(self):
        self.running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self.running:
            if not self.paused and not self.game_over:
                self.tick(self.tick_interval * self.speed)
            time.sleep(self.tick_interval)

    def tick(self, dt):
        with self.lock:
            if self.game_over:
                return
            self.time += dt

            # 1. Crescimento e producao
            for star in self.stars:
                for planet in star.planets:
                    if planet.is_colonized and planet.faction:
                        try:
                            planet.develop(dt)
                        except Exception as e:
                            print(f"[planet {planet.name}] {e}")

            # 2. Descolonizacao por populacao zero
            for star in self.stars:
                for planet in star.planets:
                    if (planet.is_colonized
                            and planet.faction is not None
                            and (planet.population <= 0 or planet.developement < 0.05)):
                        planet.faction.decolonize_planet(planet)

            # 3. Pesquisa e economia
            for f in self.factions:
                if f.eliminated:
                    continue
                try:
                    f._recompute_resources()
                    f.process_research(dt)
                    f.logistics_manager.update()
                except Exception as e:
                    print(f"[faction {f.name}] {e}")

            # 4. Combate e cercos
            self._resolve_combat(dt)
            self._resolve_sieges(dt)
            self._process_wonders(dt)

            # 5. Controllers (IA / jogador)
            for f in self.factions:
                if f.eliminated or f.controller is None:
                    continue
                try:
                    f.controller.update(self, dt)
                except Exception as e:
                    print(f"[ctrl {f.name}] {e}")

            self._process_trade_income(dt)
            self._check_victory()

    def _process_trade_income(self, dt):
        trade_factor = 4.0 if self.victory_mode == "economic" else 1.0
        processed = set()
        for faction in self.factions:
            if faction.eliminated:
                continue
            for other_name, treaties in faction.treaties.items():
                if "trade" not in treaties:
                    continue
                pair = frozenset((faction.name, other_name))
                if pair in processed:
                    continue
                processed.add(pair)
                other = next(
                    (candidate for candidate in self.factions
                     if candidate.name == other_name and not candidate.eliminated),
                    None)
                if other is None:
                    continue
                output = min(
                    sum(p.production * p.developement
                        for p in faction.colonies.values()),
                    sum(p.production * p.developement
                        for p in other.colonies.values()),
                )
                for partner in (faction, other):
                    planet = partner.home_planet
                    if planet is not None:
                        credits = (
                            output * partner.economy_multiplier * 0.1
                            * dt * trade_factor)
                        planet.planet_resources["Credits"] = min(
                            planet.storage_capacity["Credits"],
                            planet.planet_resources.get("Credits", 0.0)
                            + credits)

    def _process_wonders(self, dt):
        if "diplomatic" not in self.wonders_built:
            return
        builder_name = self.wonders_built["diplomatic"]
        builder = next(
            (faction for faction in self.factions
             if faction.name == builder_name and not faction.eliminated),
            None)
        if builder is None:
            return
        for other in self.factions:
            if other is builder or other.eliminated:
                continue
            if builder.diplomacy.get(other.name) == DiplomacyStatus.WAR:
                continue
            builder.adjust_relation(other, 0.05 * dt)

    CONDITIONAL_MODES = ("diplomatic", "domination", "economic",
                         "scientific", "terraforming", "habitat")

    def _cond_diplomatic(self, active):
        for faction in active:
            if all(
                    other is faction
                    or other.name in faction.allies
                    or other.eliminated
                    for other in self.factions):
                return faction
        return None

    def _cond_domination(self, active):
        return active[0] if len(active) == 1 else None

    def _cond_economic(self, active):
        ranked = sorted(
            active, key=lambda faction: faction.economy_score(),
            reverse=True)
        if ranked[0].economy_score() >= sum(
                faction.economy_score() for faction in ranked[1:]) * 2:
            return ranked[0]
        return None

    def _cond_scientific(self, active):
        return next(
            (faction for faction in active
             if all(faction.is_tech_capped(field)
                    for field in faction.tech_tree)),
            None)

    def _cond_terraforming(self, active):
        return next(
            (faction for faction in active
             if sum(getattr(p, 'terraform_level', 0)
                    for p in faction.colonies.values()
                    if p.faction is faction)
             >= self.TERRAFORM_VICTORY_TIERS),
            None)

    def _cond_habitat(self, active):
        return next(
            (faction for faction in active
             if faction.habitat_total() >= self.HABITAT_VICTORY_COUNT),
            None)

    def _check_victory(self):
        active = [faction for faction in self.factions
                  if not faction.eliminated]
        if not active:
            return

        checkers = {
            "diplomatic": self._cond_diplomatic,
            "domination": self._cond_domination,
            "economic": self._cond_economic,
            "scientific": self._cond_scientific,
            "terraforming": self._cond_terraforming,
            "habitat": self._cond_habitat,
        }

        winner = None
        condition = None
        if self.victory_mode == "standard":
            if self.year >= 3000:
                winner = max(
                    active,
                    key=lambda faction: faction.compute_strength()["total"])
                condition = self.VICTORY_MODES["standard"]
        elif self.victory_mode == "expansion":
            if self.year >= 3000:
                winner = max(
                    active,
                    key=lambda faction: sum(
                        planet.population
                        for planet in faction.colonies.values()))
                condition = self.VICTORY_MODES["expansion"]
        else:
            modes = (self.CONDITIONAL_MODES
                     if self.victory_mode == "any"
                     else (self.victory_mode,))
            for mode in modes:
                winner = checkers[mode](active)
                if winner is not None:
                    condition = self.VICTORY_MODES[mode]
                    break
            if (winner is None and self.victory_mode == "any"
                    and self.year >= 3000):
                winner = max(
                    active,
                    key=lambda faction: faction.compute_strength()["total"])
                condition = f"{self.VICTORY_MODES['any']} (3000)"

        if winner is None:
            return

        self.winner = winner
        self.winner_condition = condition
        self.game_over = True
        self.paused = True
        self.log_event(
            f"{winner.name} venceu: {condition}")

    def _resolve_combat(self, dt):
        warships = []
        for f in self.factions:
            if f.eliminated:
                continue
            for s in list(f.ships.values()):
                if isinstance(s, Warship) and s.alive:
                    warships.append(s)
        for i, s1 in enumerate(warships):
            if not s1.alive:
                continue
            for s2 in warships[i + 1:]:
                if not s2.alive or s1.faction is s2.faction:
                    continue
                if s2.faction.name not in s1.faction.war_declarations:
                    continue
                if s2.faction.name in s1.faction.allies:
                    continue
                if math.dist(s1.abs_position, s2.abs_position) > 100:
                    continue
                s1.take_damage(
                    s2.weapons * s2.faction.combat_multiplier * dt / 12.0)
                s2.take_damage(
                    s1.weapons * s1.faction.combat_multiplier * dt / 12.0)
                if not s1.alive or not s2.alive:
                    break

    def _resolve_sieges(self, dt):
        siege_range = 200
        for f in self.factions:
            if f.eliminated:
                continue
            enemy_names = {n for n, st in f.diplomacy.items()
                           if st == DiplomacyStatus.WAR}
            if not enemy_names:
                continue
            warships = [s for s in f.ships.copy().values()
                        if isinstance(s, Warship) and s.alive]
            if not warships:
                continue
            damage_by_planet = {}
            for ws in warships:
                for star in self.stars:
                    if math.dist(ws.abs_position, star.position) > siege_range:
                        continue
                    found = False
                    for planet in star.planets:
                        if not planet.is_colonized:
                            continue
                        if (planet.faction is None or planet.faction is f
                                or planet.faction.eliminated):
                            continue
                        if planet.faction.name not in enemy_names:
                            continue
                        dmg = (
                            ws.weapons * ws.faction.combat_multiplier
                            * dt * 0.5 / 12.0)
                        damage_by_planet[planet] = (
                            damage_by_planet.get(planet, 0.0) + dmg)
                        found = True
                        break
                    if found:
                        break
            for planet, dmg in damage_by_planet.items():
                planet.defense = max(0.0, planet.defense - dmg)
                if planet.defense <= 0:
                    self._capture_planet(planet, f)

    def _capture_planet(self, planet, attacker):
        defender = planet.faction
        if defender is None or defender is attacker:
            return
        # Transfere
        planet.faction = attacker
        planet.population *= 0.5
        planet.developement *= 0.7
        planet.defense = planet.max_defense * 0.3
        planet.habitat_building = False
        # Limpa fila de construção
        while True:
            try:
                planet.const_queue.get_nowait()
            except Empty:
                break
        # Remove do defensor, adiciona ao atacante
        defender.colonies.pop(planet.name, None)
        attacker.colonies[planet.name] = planet
        attacker.stats['planets_captured'] += 1
        # Home planet caiu?
        if defender.home_planet is planet and defender.colonies:
            defender.home_planet = next(iter(defender.colonies.values()))
        # Explorado
        attacker.explored_stars.add(planet.parent_star.name)
        # Elimina defensor se ficou sem colônias
        if not defender.colonies:
            defender.eliminated = True
            for s in list(defender.ships.values()):
                s.alive = False
                s.running = False
        # Recalcula controle de sistemas e recursos
        self._recompute_control()
        attacker._recompute_resources()
        defender._recompute_resources()
        self.log_event(f"{attacker.name} conquistou {planet.name} de "
                       f"{defender.name}")
        if defender.eliminated:
            self.log_event(f"{defender.name} foi eliminada!")

    def _recompute_control(self):
        for f in self.factions:
            f.controlled_stars = {}
        for star in self.stars:
            for planet in star.planets:
                if planet.is_colonized and planet.faction:
                    planet.faction.controlled_stars[star.name] = star

    def stop(self):
        self.running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=max(1.0, self.tick_interval * 2))
        