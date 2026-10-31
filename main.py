import random
import pygame

from graphics.generate_map import init_map
from players.factions import Faction, FactionType
from game_state import GameState
from controllers.player import PlayerController
from controllers.ai import AIController
from ui.interface import GameUI


def pick_free_planet(stars):
    choices = [(s, p) for s in stars for p in s.planets
               if not p.is_colonized]
    return random.choice(choices) if choices else None


def main():
    pygame.init()
    W, H = 1400, 820
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption("Terra Pax")
    clock = pygame.time.Clock()

    game_map, stars = init_map(60, 1500, 220)

    factions = []
    defs = [
        ("Federacao Humana", FactionType.HUMAN, True),
        ("Coletivo Xar'ki",  FactionType.ALIEN, False),
        ("Nexus Sintetico",  FactionType.ROBOT, False),
    ]
    for name, ftype, is_human in defs:
        sp = pick_free_planet(stars)
        if not sp:
            break
        star, planet = sp
        factions.append(Faction(name, ftype,
                                home_planet=planet,
                                home_star=star,
                                is_human=is_human))

    if not factions:
        print("Sem planetas para fundar faccoes.")
        pygame.quit()
        return

    for f in factions:
        f.initialize_scout_manager(game_map, stars)

    player_faction = factions[0]
    player_ctrl = PlayerController(player_faction)
    player_faction.controller = player_ctrl

    for f in factions[1:]:
        f.controller = AIController(f, aggression=random.uniform(0.2, 0.8))

    for f in factions:
        f.spawn_ship('scout')

    state = GameState(game_map, stars, factions, tick_interval=0.5)
    state.start()

    ui = GameUI(screen, state, player_ctrl)
    ui.log_msg("Bem-vindo a Terra Pax")

    is_fullscreen = False
    running = True
    try:
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif (event.type == pygame.KEYDOWN
                      and event.key == pygame.K_F11):
                    is_fullscreen = not is_fullscreen
                    if is_fullscreen:
                        screen = pygame.display.set_mode(
                            (0, 0), pygame.FULLSCREEN)
                    else:
                        screen = pygame.display.set_mode(
                            (W, H), pygame.RESIZABLE)
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
        pygame.quit()


if __name__ == "__main__":
    main()
    