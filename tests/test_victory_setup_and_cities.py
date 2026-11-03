import random
import unittest
from types import SimpleNamespace

import networkx as nx
import numpy as np
import pygame

from game_state import GameState
from graphics.generate_map import init_map
from graphics.planet_generator import (
    generate_city_light_texture,
    generate_planet_land_mask,
)
from graphics.star import Planet, Star
from controllers.player import PlayerController
from main import GALAXY_LAYOUTS
from players.factions import (
    DESIGNS,
    GALACTIC_WONDERS,
    TECH_CAPS,
    Faction,
    FactionType,
)
from players.ships import Transport
from ui.faction_selection import FactionCustomizationScreen
from ui.galaxy_selection import (
    GalaxySelectionScreen,
    VictorySelectionScreen,
)
from ui.interface import GameUI


def make_faction(name):
    planet = SimpleNamespace(
        name=f"{name}-home",
        planet_resources={},
        storage_capacity={"Credits": 10_000},
        production=1.0,
        developement=0.3,
        defense=500.0,
        is_colonized=True,
    )
    star = SimpleNamespace(name=f"{name}-star")
    return Faction(name, FactionType.HUMAN, planet, star)


class NewGameSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_all_galaxy_sizes_are_selectable(self):
        screen = pygame.Surface((900, 600))
        selection = GalaxySelectionScreen(screen)
        selection.draw()
        self.assertEqual(len(selection.OPTIONS), 5)
        self.assertEqual(
            [option[0] for option in selection.OPTIONS],
            ["tiny", "compact", "medium", "large", "giant"])
        self.assertEqual(
            set(GALAXY_LAYOUTS),
            {option[0] for option in selection.OPTIONS})
        self.assertTrue(all(
            0 <= rect.left < rect.right <= 900
            for rect in selection.option_rects))

    def test_all_galaxy_sizes_generate_distinct_star_systems(self):
        random_state = random.getstate()
        random.seed(20261101)
        try:
            for name, (star_count, sector_size, min_distance, _) in (
                    GALAXY_LAYOUTS.items()):
                with self.subTest(galaxy=name):
                    graph, stars = init_map(
                        star_count, sector_size, min_distance)
                    star_names = [star.name for star in stars]
                    self.assertEqual(len(stars), star_count)
                    self.assertEqual(len(graph), star_count)
                    self.assertEqual(len(set(star_names)), star_count)
        finally:
            random.setstate(random_state)

    def test_victory_selection_covers_all_nine_modes(self):
        selection = VictorySelectionScreen(pygame.Surface((900, 600)))
        selection.draw()
        self.assertEqual(len(selection.OPTIONS), 9)
        self.assertEqual(
            {option[0] for option in selection.OPTIONS},
            set(GameState.VICTORY_MODES))
        self.assertEqual(
            set(GALACTIC_WONDERS),
            set(GameState.VICTORY_MODES) - {"any"})
        self.assertEqual(
            selection.handle_event(pygame.event.Event(
                pygame.KEYDOWN, key=pygame.K_RETURN)), "standard")

    def test_victory_options_fit_common_window_sizes(self):
        for size in ((1400, 820), (900, 600), (480, 560)):
            with self.subTest(size=size):
                selection = VictorySelectionScreen(
                    pygame.Surface(size))
                selection.draw()
                self.assertEqual(len(selection.option_rects), 9)
                self.assertTrue(all(
                    0 <= rect.left < rect.right <= size[0]
                    and 0 <= rect.top < rect.bottom <= size[1]
                    for rect in selection.option_rects))

    def test_in_game_button_requests_a_new_game(self):
        faction = make_faction("Player")
        state = GameState(None, [], [faction])
        ui = GameUI(
            pygame.Surface((1400, 820)), state, PlayerController(faction))
        restart = ui._top_buttons[-1]

        ui.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=restart.rect.center))

        self.assertTrue(ui.restart_requested)

    def test_topbar_status_text_does_not_extend_under_planet_filters(self):
        faction = make_faction("Player")
        state = GameState(None, [], [faction])
        ui = GameUI(
            pygame.Surface((1400, 820)), state, PlayerController(faction))

        status_clip = ui._topbar_status_clip_rect()

        self.assertLess(
            status_clip.right, ui._filter_buttons[0].rect.left)

    def test_custom_faction_can_change_name_and_traits(self):
        faction = make_faction("Original")
        selection = FactionCustomizationScreen(
            pygame.Surface((900, 600)), faction)
        selection._cycle_trait("advantage", 1)
        selection._cycle_trait("disadvantage", -1)
        selection.name = "Nova"

        self.assertIs(selection.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_RETURN, unicode="")), faction)
        self.assertEqual(faction.name, "Nova")
        self.assertNotEqual(faction.advantage, faction.disadvantage)


class VictoryAndCalendarTests(unittest.TestCase):
    def setUp(self):
        self.player = make_faction("Player")
        self.opponent = make_faction("Opponent")

    def make_state(self, mode):
        return GameState(
            None, [], [self.player, self.opponent], victory_mode=mode)

    def test_calendar_starts_in_january_2150_and_advances_by_month(self):
        state = self.make_state("standard")
        self.assertEqual(state.date, "Janeiro 2150")
        state.time = 1.0
        self.assertEqual(state.date, "Fevereiro 2150")
        state.time = 12.0
        self.assertEqual(state.date, "Janeiro 2151")

    def test_domination_requires_a_single_remaining_faction(self):
        state = self.make_state("domination")
        state._check_victory()
        self.assertIsNone(state.winner)

        self.opponent.eliminated = True
        state._check_victory()
        self.assertIs(state.winner, self.player)

    def test_diplomatic_victory_requires_all_active_factions_as_allies(self):
        state = self.make_state("diplomatic")
        self.player.allies.add(self.opponent.name)
        state._check_victory()
        self.assertIs(state.winner, self.player)

    def test_diplomatic_mode_raises_alliance_threshold(self):
        state = self.make_state("diplomatic")
        self.player.treaties[self.opponent.name] = {"trade"}
        self.opponent.treaties[self.player.name] = {"trade"}
        self.player.relations[self.opponent.name] = 75
        self.opponent.relations[self.player.name] = 75
        self.assertFalse(self.player.propose_alliance(self.opponent))
        self.player.relations[self.opponent.name] = 85
        self.opponent.relations[self.player.name] = 85
        self.assertTrue(self.player.propose_alliance(self.opponent))

    def test_scientific_victory_checks_every_capped_technology(self):
        state = self.make_state("scientific")
        for field in self.player.tech_tree:
            self.player.tech_tree[field] = TECH_CAPS[field]
        state._check_victory()
        self.assertIs(state.winner, self.player)

    def test_scientific_mode_makes_research_more_expensive(self):
        standard = self.make_state("standard")
        standard_cost = self.player.get_research_cost("ftl")
        scientific = self.make_state("scientific")
        scientific_cost = self.player.get_research_cost("ftl")
        self.assertGreater(scientific_cost, standard_cost)

    def test_only_the_selected_victory_condition_ends_the_match(self):
        state = self.make_state("standard")
        self.player.allies.add(self.opponent.name)
        for field in self.player.tech_tree:
            self.player.tech_tree[field] = TECH_CAPS[field]
        self.player.home_planet.planet_resources["Credits"] = 10_000
        self.player._recompute_resources()

        state._check_victory()
        self.assertIsNone(state.winner)

        state.time = 850 * 12
        self.player.home_planet.defense = 1000
        self.opponent.home_planet.defense = 100
        state._check_victory()
        self.assertIs(state.winner, self.player)

    def test_economic_victory_requires_dominating_rivals(self):
        state = self.make_state("economic")
        self.player.home_planet.planet_resources["Credits"] = 10_000
        self.player._recompute_resources()
        state._check_victory()
        self.assertIs(state.winner, self.player)

    def test_trade_agreements_generate_credits(self):
        state = self.make_state("economic")
        self.player.treaties[self.opponent.name] = {"trade"}
        self.opponent.treaties[self.player.name] = {"trade"}
        state._process_trade_income(0.5)
        self.assertGreater(
            self.player.home_planet.planet_resources["Credits"], 100)

    def test_trade_agreements_increase_research_income(self):
        self.player.add_research_income(1.0)
        without_trade = self.player.research_income_pool
        self.player.research_income_pool = 0.0
        self.player.treaties[self.opponent.name] = {"trade"}
        self.player.add_research_income(1.0)
        self.assertGreater(self.player.research_income_pool, without_trade)

    def test_standard_and_expansion_winners_are_decided_in_3000(self):
        for mode, winner in (
                ("standard", self.player), ("expansion", self.opponent)):
            self.player.eliminated = False
            self.opponent.eliminated = False
            self.player.home_planet.defense = 1000
            self.opponent.home_planet.defense = 100
            self.player.home_planet.population = 100
            self.opponent.home_planet.population = 1000
            state = self.make_state(mode)
            state.time = 850 * 12
            state._check_victory()
            self.assertIs(state.winner, winner)

    def test_biotech_improves_population_growth_in_expansion_mode(self):
        def colony(name):
            planet = Planet(
                n_planet_resources=0, planet_resources={},
                abs_position=(0.0, 0.0),
                life_suitability={"Human": 1.0},
                production=1.0, developement=0.3,
                distance_from_star=1.0, radius=1.0,
                is_colonized=False, name=name, star_position=(0.0, 0.0))
            planet.post_init()
            return planet

        slower, faster = colony("slow"), colony("fast")
        slow_faction = Faction(
            "Slow", FactionType.HUMAN, slower, SimpleNamespace(name="slow"),
            advantage="expansion")
        fast_faction = Faction(
            "Fast", FactionType.HUMAN, faster, SimpleNamespace(name="fast"),
            advantage="expansion")
        GameState(None, [], [slow_faction], victory_mode="expansion")
        GameState(None, [], [fast_faction], victory_mode="expansion")
        fast_faction.tech_tree["biotech"] = 5

        slower.develop(6.0)
        faster.develop(6.0)

        self.assertGreater(faster.population, slower.population)

    def test_wonders_are_unique_and_apply_their_bonus(self):
        state = self.make_state("standard")
        wonder = GALACTIC_WONDERS["domination"]
        self.player.home_planet.planet_resources.update(wonder["cost"])
        self.opponent.home_planet.planet_resources.update(wonder["cost"])
        self.player._recompute_resources()
        self.opponent._recompute_resources()

        self.assertTrue(self.player.build_wonder("domination"))
        self.assertFalse(self.opponent.build_wonder("domination"))
        self.assertIn("domination", self.player.wonders)
        self.assertEqual(state.wonders_built["domination"], self.player.name)

    def test_terraforming_victory_requires_twelve_expansion_tiers(self):
        state = self.make_state("terraforming")
        self.player.home_planet.terraform_level = 11
        state._check_victory()
        self.assertIsNone(state.winner)

        self.player.home_planet.terraform_level = 12
        state._check_victory()
        self.assertIs(state.winner, self.player)
        self.assertEqual(state.winner_condition, "Ecopoese")

    def test_habitat_victory_requires_twenty_four_stations(self):
        state = self.make_state("habitat")
        self.player.home_planet.habitats = 23
        state._check_victory()
        self.assertIsNone(state.winner)

        self.player.home_planet.habitats = 24
        state._check_victory()
        self.assertIs(state.winner, self.player)
        self.assertEqual(
            state.winner_condition, "Habitação Orbital")

    def test_combined_mode_is_won_by_the_first_condition_met(self):
        state = self.make_state("any")
        self.opponent.eliminated = True
        state._check_victory()
        self.assertIs(state.winner, self.player)
        self.assertIn(
            state.winner_condition, ("Diplomática", "Dominação"))

    def test_combined_mode_falls_back_to_strength_in_3000(self):
        state = self.make_state("any")
        state.time = 850 * 12
        self.player.home_planet.defense = 1000
        self.opponent.home_planet.defense = 100
        state._check_victory()
        self.assertIs(state.winner, self.player)
        self.assertIn("3000", state.winner_condition)

    def test_ecopoese_and_habitat_wonders_exist_for_their_modes(self):
        for mode in ("terraforming", "habitat"):
            self.assertIn(mode, GALACTIC_WONDERS)
            self.assertIn("cost", GALACTIC_WONDERS[mode])


class CityGenerationTests(unittest.TestCase):
    def test_economic_development_rewards_construction_and_trade(self):
        def developed_value(construction, trade_partners):
            planet = Planet(
                n_planet_resources=0, planet_resources={},
                abs_position=(0.0, 0.0),
                life_suitability={"Human": 1.0},
                production=1.0, developement=0.3,
                distance_from_star=1.0, radius=1.0,
                is_colonized=False, name="industry",
                star_position=(0.0, 0.0))
            planet.post_init()
            faction = Faction(
                f"Faction-{construction}-{trade_partners}",
                FactionType.HUMAN, planet,
                SimpleNamespace(name="industry"))
            faction.tech_tree["construction"] = construction
            faction.treaties = {
                f"partner-{index}": {"trade"}
                for index in range(trade_partners)}
            GameState(None, [], [faction], victory_mode="economic")
            planet.develop(6.0)
            return planet.developement

        base = developed_value(1, 0)
        developed = developed_value(10, 5)
        self.assertGreater(developed, base)

    def test_economic_mode_uses_industrial_inputs_and_trade_credits(self):
        def industry(mode):
            planet = Planet(
                n_planet_resources=0, planet_resources={},
                abs_position=(0.0, 0.0),
                life_suitability={"Human": 1.0},
                production=1.0, developement=0.3,
                distance_from_star=1.0, radius=1.0,
                is_colonized=False, name=mode, star_position=(0.0, 0.0))
            planet.post_init()
            faction = Faction(
                mode, FactionType.HUMAN, planet,
                SimpleNamespace(name=mode))
            if mode == "economic":
                faction.tech_tree["construction"] = 10
            GameState(None, [], [faction], victory_mode=mode)
            planet.produce()
            return planet

        standard = industry("standard")
        economic = industry("economic")
        self.assertLess(
            economic.planet_resources["Minerals"],
            standard.planet_resources["Minerals"])
        self.assertGreater(
            economic.planet_resources["Electronics"],
            standard.planet_resources["Electronics"])
        self.assertEqual(economic.planet_resources["Credits"], 100)

    def test_city_lights_are_seeded_and_stay_on_land(self):
        suitability = {
            "Human": 0.9, "Alien": 0.2, "Hybrid": 0.4, "Robot": 0.1}
        size = (128, 64)
        land = generate_planet_land_mask("city-test", size)
        first = generate_city_light_texture(
            suitability, "city-test", size, detail_level=2)
        second = generate_city_light_texture(
            suitability, "city-test", size, detail_level=2)
        alpha = pygame.surfarray.array_alpha(first).T

        np.testing.assert_array_equal(
            pygame.surfarray.array_alpha(first),
            pygame.surfarray.array_alpha(second))
        self.assertTrue(np.all(alpha[~land] == 0))
        self.assertTrue(np.any(alpha[land] > 0))


class TransportUtilityTests(unittest.TestCase):
    def setUp(self):
        self.graph = nx.Graph()
        self.source_star = Star(
            "Source", 1000, 10, 10, (0.0, 0.0), [])
        self.destination_star = Star(
            "Destination", 1000, 10, 10, (100.0, 0.0), [])

        def make_planet(name, star):
            planet = Planet(
                n_planet_resources=0, planet_resources={},
                abs_position=star.position,
                life_suitability={"Human": 1.0},
                production=1.0, developement=0.3,
                distance_from_star=1.0, radius=1.0,
                is_colonized=False, name=name,
                star_position=star.position)
            planet.post_init()
            planet.parent_star = star
            star.planets.append(planet)
            return planet

        home = make_planet("Home", self.source_star)
        self.faction = Faction(
            "Migrants", FactionType.HUMAN, home, self.source_star)
        destination = make_planet("Colony", self.destination_star)
        self.faction.establish_colony(self.destination_star, destination)
        self.graph.add_edge(
            self.source_star.name, self.destination_star.name, weight=100.0)
        self.faction.map_G = self.graph
        self.faction.all_stars = [self.source_star, self.destination_star]
        GameState(
            self.graph, self.faction.all_stars, [self.faction])
        self.transport = Transport(
            ship_id="MIG-001", faction=self.faction, map_G=self.graph,
            current_position=self.source_star,
            total_stars=self.faction.all_stars, design_key="transport",
            **DESIGNS["transport"]["stats"])

    def test_transporters_move_surplus_population_between_colonies(self):
        source = self.faction.home_planet
        destination = self.faction.colonies["Colony"]
        source.population = 1000
        destination.population = 100
        initial_population = source.population + destination.population

        route = self.transport.plan_population_transfer()
        self.assertIsNotNone(route)
        planned_source, planned_destination, amount = route
        self.assertIs(planned_source, source)
        self.assertIs(planned_destination, destination)

        self.assertTrue(self.transport._load_population(source, amount))
        self.assertGreater(
            self.transport._deliver_population(destination), 0)
        self.assertAlmostEqual(
            source.population + destination.population, initial_population)
        self.assertEqual(self.transport.population_cargo, 0)
        self.assertGreaterEqual(source.population, 100)

    def test_transporters_balance_food_as_well_as_minerals(self):
        source = self.faction.home_planet
        destination = self.faction.colonies["Colony"]
        source.planet_resources["Food"] = 1500

        runs = self.faction.logistics_manager.plan_freight_runs(
            self.transport.cargo, count=1, origin=self.source_star)

        self.assertTrue(runs)
        run = runs[0]
        self.assertIs(run['source'], source)
        self.assertIs(run['destination'], destination)
        self.assertIn('Food', [resource for resource, _ in run['legs']])

    def test_transporter_loads_several_resources_in_one_run(self):
        source = self.faction.home_planet
        destination = self.faction.colonies["Colony"]
        source.planet_resources.update(
            {'Food': 4000.0, 'Energy': 9000.0, 'Alloys': 800.0})
        destination.planet_resources.update(
            {'Food': 450.0, 'Energy': 950.0, 'Alloys': 90.0})
        destination.queue_task({
            'kind': 'ship', 'label': 'Corveta', 'build_time': 4.0,
            'cost': {'Food': 120.0, 'Energy': 90.0, 'Alloys': 60.0}})

        missions = self.transport.plan_missions()
        freight = [m for m in missions if m['kind'] == 'freight']
        self.assertTrue(freight)
        mission = freight[0]
        self.assertIs(mission['source'], source)
        self.assertIs(mission['destination'], destination)
        legs = dict(mission['legs'])
        self.assertTrue({'Food', 'Energy'} <= set(legs))
        self.assertLessEqual(sum(legs.values()), self.transport.cargo)

        loaded = self.faction.logistics_manager.load_cargo(
            self.transport, source, mission['legs'])
        self.assertAlmostEqual(
            loaded, sum(leg_amount for _, leg_amount in mission['legs']),
            places=6)
        self.assertEqual(set(self.transport.cargo_hold), set(legs))
        self.assertAlmostEqual(self.transport.load, loaded)

        self.faction.logistics_manager.deliver_cargo(
            self.transport, destination)
        self.assertEqual(self.transport.cargo_hold, {})
        self.assertGreater(
            destination.planet_resources['Energy'], 950.0)

    def test_transporter_keeps_a_queue_of_next_tasks(self):
        source = self.faction.home_planet
        source.planet_resources.update({'Food': 4000.0, 'Minerals': 8000.0})
        missions = self.transport.plan_missions()
        self.assertTrue(missions)
        self.transport.mission = missions[0]
        self.transport.mission_queue = missions[1:]
        self.assertEqual(self.transport.scheduled_missions(), missions)

    def test_overload_is_reported_when_the_fleet_cannot_carry(self):
        destination = self.faction.colonies["Colony"]
        destination.queue_task({
            'kind': 'ship', 'label': 'Colonizadora', 'build_time': 6.0,
            'cost': {'Minerals': 5_000.0}})
        status = self.faction.logistics_manager.overload_status()
        self.assertTrue(status['overloaded'])
        self.assertGreaterEqual(status['missing_transports'], 1)
        self.assertIn(destination, status['starved'])


class ShipyardDistributionTests(unittest.TestCase):
    """Construção de naves repartida entre as colônias armadas."""

    def setUp(self):
        self.graph = nx.Graph()
        self.faction = None
        self.colonies = []
        names = ('Capital', 'Forja', 'Porto', 'Estaleiro')
        for index, name in enumerate(names):
            star = Star(name, 1000, 10, 10, (index * 120.0, 0.0), [])
            planet = Planet(
                n_planet_resources=0, planet_resources={},
                abs_position=star.position,
                life_suitability={"Human": 1.0},
                production=1.0, developement=0.6,
                distance_from_star=1.0, radius=1.0,
                is_colonized=False, name=name,
                star_position=star.position)
            planet.post_init()
            planet.parent_star = star
            star.planets.append(planet)
            self.graph.add_node(star.name)
            if index:
                self.graph.add_edge(names[index - 1], star.name, weight=120.0)
            if self.faction is None:
                self.faction = Faction(
                    'Smiths', FactionType.HUMAN, planet, star)
            else:
                self.faction.establish_colony(star, planet)
            planet.production = 1.0
            planet.developement = 0.6
            planet.can_build_ships = True
            self.colonies.append(planet)
        self.faction.map_G = self.graph
        self.faction.all_stars = [p.parent_star for p in self.colonies]
        GameState(self.graph, self.faction.all_stars, [self.faction])

    def queue_works(self, planet, count):
        for _ in range(count):
            planet.queue_task({'kind': 'ship', 'label': 'obra', 'cost': {}})

    def test_shipyard_is_the_least_loaded_colony(self):
        capital, forja, porto = self.colonies[:3]
        self.queue_works(capital, 3)
        self.queue_works(forja, 1)
        self.assertIs(self.faction.pick_shipyard(), porto)
        self.assertTrue(self.faction.build_ship('scout', planet=porto))
        self.assertEqual(len(porto.build_queue), 1)
        self.assertEqual(len(capital.build_queue), 3)

    def test_automatic_choice_avoids_the_capital(self):
        capital = self.colonies[0]
        self.queue_works(capital, 4)
        self.assertTrue(self.faction.build_ship('scout'))
        self.assertEqual(len(capital.build_queue), 4)
        elsewhere = sum(
            len(p.build_queue) for p in self.faction.colonies.values()
            if p is not capital)
        self.assertEqual(elsewhere, 1)

    def test_unarmed_colonies_are_not_shipyards(self):
        for planet in self.faction.colonies.values():
            planet.can_build_ships = False
        self.assertIsNone(self.faction.pick_shipyard())
        self.assertFalse(self.faction.build_ship('scout'))

    def test_full_queues_push_work_to_the_next_colony(self):
        from graphics.star import MAX_BUILD_QUEUE
        capital, forja = self.colonies[0], self.colonies[1]
        self.queue_works(capital, MAX_BUILD_QUEUE)
        self.assertIs(self.faction.pick_shipyard(), forja)


if __name__ == "__main__":
    unittest.main()
