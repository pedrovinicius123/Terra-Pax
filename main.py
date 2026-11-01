import random
import pygame
import sys

from graphics.generate_map import init_map
from players.factions import Faction, FactionType
from game_state import GameState
from controllers.player import PlayerController
from controllers.ai import AIController
from ui.galaxy_selection import (
    GalaxySelectionScreen,
    VictorySelectionScreen,
)
from ui.faction_selection import (
    FactionCustomizationScreen,
    FactionSelectionScreen,
)
from ui.interface import GameUI


def pick_home_planet(stars, faction_type, used_names):
    """Sorteia entre os melhores planetas para o tipo, com ruído."""
    candidates = [(s, p) for s in stars for p in s.planets
                  if not p.is_colonized and p.name not in used_names]
    if not candidates:
        return None
    key = faction_type.value
    scored = [(p.life_suitability.get(key, 0.0), s, p)
              for s, p in candidates]
    scored.sort(key=lambda t: t[0], reverse=True)
    top = scored[:max(3, len(scored) // 10)]  # top 10%
    _, star, planet = random.choice(top)
    return star, planet


# (nome, tipo, is_human, cor, aggression_base, descricao)
FACTION_DEFS = [
    ("Federacao Humana",   FactionType.HUMAN,  True,  "#3498db", 0.40,
     "Diplomatas exploradores"),
    ("Coletivo Xar'ki",    FactionType.ALIEN,  False, "#e74c3c", 0.75,
     "Guerreiros impiedosos"),
    ("Nexus Sintetico",    FactionType.ROBOT,  False, "#bdc3c7", 0.30,
     "Mentes maquina coletivas"),
    ("Consorcio de Vesta", FactionType.HUMAN,  False, "#e67e22", 0.20,
     "Mercadores pragmaticos"),
    ("Irmandade Ciborgue", FactionType.HYBRID, False, "#9b59b6", 0.50,
     "Meio carne, meio maquina"),
    ("Enxame Silencioso",  FactionType.ALIEN,  False, "#2ecc71", 0.60,
     "Mente coletiva voraz"),
    ("Diretoria de Órion", FactionType.ROBOT, False, "#1abc9c", 0.35,
     "Consciência sintética descentralizada"),
    ("Pacto de Lótus", FactionType.HYBRID, False, "#f39c12", 0.45,
     "Aliança entre espécies"),
    ("Liga de Proxima", FactionType.HUMAN, False, "#e91e63", 0.30,
     "Colônias independentes"),
    ("Ninhada Vórtice", FactionType.ALIEN, False, "#16a085", 0.70,
     "Exploradores de mundos extremos"),
]
COMPACT_GALAXY_FACTION_INDICES = (0, 1, 2, 4, 5, 7)
TINY_GALAXY_FACTION_INDICES = (0, 1, 2, 4)
FACTION_TRAIT_ASSIGNMENTS = (
    ("diplomacy", "military"),
    ("military", "economy"),
    ("science", "expansion"),
    ("economy", "military"),
    ("expansion", "diplomacy"),
    ("expansion", "science"),
    ("science", "economy"),
    ("diplomacy", "expansion"),
    ("economy", "science"),
    ("military", "diplomacy"),
)
GALAXY_LAYOUTS = {
    "tiny": (20, 1800, 260, TINY_GALAXY_FACTION_INDICES),
    "compact": (30, 2600, 320, COMPACT_GALAXY_FACTION_INDICES),
    "medium": (60, 4000, 440, None),
    "large": (100, 5200, 500, None),
    "giant": (160, 7000, 560, None),
}


def main():
    try:
        pygame.init()
        W, H = 1400, 820
        screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
        pygame.display.set_caption("Terra Pax")
        clock = pygame.time.Clock()

        def select_value(selection):
            nonlocal W, H, screen
            while True:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        return None
                    if event.type == pygame.VIDEORESIZE:
                        W, H = event.w, event.h
                        screen = pygame.display.set_mode(
                            (W, H), pygame.RESIZABLE)
                        selection.on_resize(screen)
                        continue
                    choice = selection.handle_event(event)
                    if choice is not None:
                        return choice
                selection.draw()
                pygame.display.flip()
                clock.tick(60)

        while True:
            galaxy_size = select_value(GalaxySelectionScreen(screen))
            if galaxy_size is None:
                break
            victory_mode = select_value(VictorySelectionScreen(screen))
            if victory_mode is None:
                break

            n_stars, sector_size, min_dist, faction_indices = (
                GALAXY_LAYOUTS[galaxy_size])
            game_map, stars = init_map(n_stars, sector_size, min_dist)
            faction_defs = (
                [FACTION_DEFS[index] for index in faction_indices]
                if faction_indices is not None else FACTION_DEFS)

            factions = []
            aggression_by_faction = {}
            used_names = set()
            for name, ftype, is_human, color, aggression, desc in faction_defs:
                home = pick_home_planet(stars, ftype, used_names)
                if not home:
                    print(f"Sem planetas livres para {name}; pulando.")
                    continue
                star, planet = home
                used_names.add(planet.name)
                faction_index = next(
                    index for index, definition in enumerate(FACTION_DEFS)
                    if definition[0] == name)
                advantage, disadvantage = FACTION_TRAIT_ASSIGNMENTS[faction_index]
                faction = Faction(
                    name, ftype, home_planet=planet, home_star=star,
                    is_human=is_human, color=color, description=desc,
                    advantage=advantage, disadvantage=disadvantage)
                factions.append(faction)
                aggression_by_faction[id(faction)] = aggression

            if not factions:
                print("Nenhuma facção criada.")
                break

            player_faction = select_value(
                FactionSelectionScreen(screen, factions))
            if player_faction is None:
                break
            player_faction = select_value(
                FactionCustomizationScreen(
                    screen, player_faction,
                    (faction.name for faction in factions
                    if faction is not player_faction)))
            if player_faction is None:
                break

            for faction in factions:
                faction.initialize_scout_manager(game_map, stars)

            player_ctrl = PlayerController(player_faction)
            for faction in factions:
                faction.is_human = faction is player_faction
                if faction is player_faction:
                    faction.controller = player_ctrl
                else:
                    base = aggression_by_faction[id(faction)]
                    aggression = max(
                        0.1, min(0.95, base + random.uniform(-0.1, 0.1)))
                    faction.controller = AIController(
                        faction, aggression=aggression)

            for faction in factions:
                faction.spawn_ship('scout')

            state = GameState(
                game_map, stars, factions, tick_interval=0.5,
                victory_mode=victory_mode)
            state.start()
            state.log_event(
                f"{len(factions)} facções emergiram na galáxia "
                f"({GameState.VICTORY_MODES[victory_mode]})")

            ui = GameUI(screen, state, player_ctrl)
            ui.log_msg(f"Bem-vindo a Terra Pax — {len(factions)} facções")

            is_fullscreen = False
            running = True
            try:
                while running and not ui.restart_requested:
                    for event in pygame.event.get():
                        if event.type == pygame.QUIT:
                            running = False
                        elif (event.type == pygame.KEYDOWN
                            and event.key == pygame.K_F11):
                            is_fullscreen = not is_fullscreen
                            screen = pygame.display.set_mode(
                                (0, 0) if is_fullscreen else (W, H),
                                pygame.FULLSCREEN if is_fullscreen
                                else pygame.RESIZABLE)
                            ui.on_resize(screen)
                        elif (event.type == pygame.VIDEORESIZE
                            and not is_fullscreen):
                            W, H = event.w, event.h
                            screen = pygame.display.set_mode(
                                (W, H), pygame.RESIZABLE)
                            ui.on_resize(screen)
                        else:
                            ui.handle_event(event)
                    ui.render()
                    pygame.display.flip()
                    clock.tick(60)
            finally:
                state.stop()
                for faction in factions:
                    faction.stop_faction()
                if ui.restart_requested and is_fullscreen:
                    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)

            if not ui.restart_requested:
                break

        pygame.quit()
    except Exception as err:
        print(err)
        sys.exit()


if __name__ == "__main__":
    main()
