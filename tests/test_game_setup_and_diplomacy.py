import unittest
from types import SimpleNamespace

import pygame

from controllers.ai import AIController
from main import COMPACT_GALAXY_FACTION_INDICES, FACTION_DEFS
from players.factions import DiplomacyStatus, Faction, FactionType
from ui.galaxy_selection import GalaxySelectionScreen


def make_faction(name, is_human=False):
    planet = SimpleNamespace(
        name=f"{name}-home",
        planet_resources={},
        production=1.0,
        developement=0.3,
        defense=500.0,
        is_colonized=True,
    )
    star = SimpleNamespace(name=f"{name}-star")
    return Faction(
        name, FactionType.HUMAN, planet, star, is_human=is_human)


class GalaxySelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1), flags=pygame.HIDDEN)

    def test_selects_compact_galaxy_with_keyboard(self):
        screen = pygame.Surface((900, 600))
        selection = GalaxySelectionScreen(screen)
        selection.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_RIGHT))
        result = selection.handle_event(pygame.event.Event(
            pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertEqual(result, "compact")

    def test_compact_roster_keeps_all_faction_types(self):
        compact_factions = [
            FACTION_DEFS[index]
            for index in COMPACT_GALAXY_FACTION_INDICES
        ]
        self.assertEqual(len(compact_factions), 6)
        self.assertEqual(
            {faction[1] for faction in compact_factions},
            set(FactionType),
        )

    def test_compact_option_is_mouse_selectable(self):
        selection = GalaxySelectionScreen(pygame.Surface((900, 600)))
        selection.draw()
        result = selection.handle_event(pygame.event.Event(
            pygame.MOUSEBUTTONDOWN,
            button=1,
            pos=selection.option_rects[1].center,
        ))
        self.assertEqual(result, "compact")

    def test_options_fit_a_narrow_window(self):
        selection = GalaxySelectionScreen(pygame.Surface((480, 560)))
        selection.draw()
        self.assertTrue(all(
            rect.left >= 0 and rect.right <= 480
            for rect in selection.option_rects
        ))


class PeaceOfferTests(unittest.TestCase):
    def setUp(self):
        self.player = make_faction("Player", is_human=True)
        self.ai = make_faction("AI")
        self.player.update_diplomacy(self.ai, DiplomacyStatus.WAR)

    def test_player_can_accept_ai_peace_offer(self):
        self.assertTrue(self.ai.propose_peace(self.player))
        self.assertIn(self.ai.name, self.player.pending_peace_offers)

        self.assertTrue(self.player.respond_to_peace_offer(self.ai, True))

        self.assertEqual(
            self.player.diplomacy[self.ai.name], DiplomacyStatus.PEACE)
        self.assertEqual(
            self.ai.diplomacy[self.player.name], DiplomacyStatus.PEACE)
        self.assertNotIn(self.ai.name, self.player.pending_peace_offers)

    def test_player_can_reject_and_block_repeat_offer_for_this_war(self):
        self.assertTrue(self.ai.propose_peace(self.player))
        self.assertTrue(self.player.respond_to_peace_offer(self.ai, False))

        self.assertEqual(
            self.player.diplomacy[self.ai.name], DiplomacyStatus.WAR)
        self.assertFalse(self.ai.propose_peace(self.player))
        self.assertNotIn(self.ai.name, self.player.pending_peace_offers)

    def test_new_war_clears_previous_rejection(self):
        self.assertTrue(self.ai.propose_peace(self.player))
        self.assertTrue(self.player.respond_to_peace_offer(self.ai, False))

        self.player.update_diplomacy(self.ai, DiplomacyStatus.PEACE)
        self.player.update_diplomacy(self.ai, DiplomacyStatus.WAR)

        self.assertTrue(self.ai.propose_peace(self.player))

    def test_ai_offers_peace_instead_of_ending_players_war(self):
        self.ai.home_planet.defense = 100.0
        self.player.home_planet.defense = 1000.0
        self.ai.update_diplomacy(self.player, DiplomacyStatus.WAR)
        self.ai.adjust_relation(self.player, 10)
        controller = AIController(self.ai, aggression=0.5)
        state = SimpleNamespace(factions=(self.ai, self.player))

        controller._manage_diplomacy(state)

        self.assertIn(self.ai.name, self.player.pending_peace_offers)
        self.assertEqual(
            self.player.diplomacy[self.ai.name], DiplomacyStatus.WAR)


if __name__ == "__main__":
    unittest.main()
