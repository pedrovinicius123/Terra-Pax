import random
import pygame

from graphics.generate_map import init_map
from players.factions import Faction, FactionType
from game_state import GameState
from controllers.player import PlayerController
from controllers.ai import AIController
from ui.faction_selection import FactionSelectionScreen
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


def main():
    pygame.init()
    W, H = 1400, 820
    screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    pygame.display.set_caption("Terra Pax")
    clock = pygame.time.Clock()

    game_map, stars = init_map(60, 4000, 440)

    factions = []
    used_names = set()
    for name, ftype, is_human, color, _agg, desc in FACTION_DEFS:
        sp = pick_home_planet(stars, ftype, used_names)
        
        if not sp:
            print(f"Sem planetas livres para {name}; pulando.")
            continue
        star, planet = sp
        used_names.add(planet.name)
        factions.append(Faction(name, ftype,
                                home_planet=planet, home_star=star,
                                is_human=is_human,
                                color=color, description=desc))

    if not factions:
        print("Nenhuma facção criada.")
        pygame.quit()
        return

    for f in factions:
        f.initialize_scout_manager(game_map, stars)

    selection_screen = FactionSelectionScreen(screen, factions)
    player_faction = None
    selecting_faction = True
    while selecting_faction:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                selecting_faction = False
                break
            if event.type == pygame.VIDEORESIZE:
                W, H = event.w, event.h
                screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
                selection_screen.on_resize(screen)
                continue
            chosen = selection_screen.handle_event(event)
            if chosen is not None:
                player_faction = chosen
                selecting_faction = False
                break
        if selecting_faction:
            selection_screen.draw()
            pygame.display.flip()
            clock.tick(60)

    if player_faction is None:
        pygame.quit()
        return

    player_ctrl = PlayerController(player_faction)
    agg_map = {d[0]: d[4] for d in FACTION_DEFS}
    for f in factions:
        f.is_human = f is player_faction
        if f is player_faction:
            f.controller = player_ctrl
        else:
            base = agg_map.get(f.name, 0.4)
            agg = max(0.1, min(0.95, base + random.uniform(-0.1, 0.1)))
            f.controller = AIController(f, aggression=agg)

    for f in factions:
        f.spawn_ship('scout')

    state = GameState(game_map, stars, factions, tick_interval=0.5)
    state.start()
    state.log_event(f"{len(factions)} facções emergiram na galáxia")

    ui = GameUI(screen, state, player_ctrl)
    ui.log_msg(f"Bem-vindo a Terra Pax — {len(factions)} faccoes")

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
                    screen = pygame.display.set_mode(
                        (0, 0) if is_fullscreen else (W, H),
                        pygame.FULLSCREEN if is_fullscreen
                        else pygame.RESIZABLE)
                    ui.on_resize(screen)
                elif (event.type == pygame.VIDEORESIZE
                      and not is_fullscreen):
                    W, H = event.w, event.h
                    screen = pygame.display.set_mode((W, H),
                                                     pygame.RESIZABLE)
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
