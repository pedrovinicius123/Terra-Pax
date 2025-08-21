import pygame
from graphics.generate_map import init_map
from players.factions import Faction, FactionType
import random, threading

def find_best(faction):
    def func(planet):
        return planet.life_suitability[faction]
    return func

def main():
   # Configuração do Pygame
    pygame.init()
    WIDTH, HEIGHT = 700, 700
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Terra Pax")
    clock = pygame.time.Clock()
    
    # Cores
    BACKGROUND = (0, 0, 0)
    WHITE = (255, 255, 255)
    RED = (255, 0, 0)
    GREEN = (0, 255, 0)
    BLUE = (0, 0, 255)
    YELLOW = (255, 255, 0)

    game_map, stars = init_map(50, WIDTH, 100)
    star = random.choice(stars)
    planet = random.choice(star.planets)

    facs = [Faction('Human Federation', FactionType.HUMAN, home_planet=planet, home_star=star)]
    
    # Configurações de zoom e visualização
    zoom_level = 1.0
    min_zoom = 0.2
    max_zoom = 1000.0
    zoom_speed = 1
    offset_x, offset_y = 0, 0
    dragging = False
    last_mouse_x, last_mouse_y = 0, 0

    # Fonte para texto
    font = pygame.font.SysFont(None, 24)

    # Função para converter coordenadas do mundo para a tela
    def world_to_screen(x, y, zoom, offset_x, offset_y):
        screen_x = int((x - offset_x) * zoom + WIDTH / 2)
        screen_y = int((y - offset_y) * zoom + HEIGHT / 2)
        return screen_x, screen_y

    # Função para converter coordenadas da tela para o mundo
    def screen_to_world(x, y, zoom, offset_x, offset_y):
        world_x = offset_x + (x - WIDTH / 2) / zoom
        world_y = offset_y + (y - HEIGHT / 2) / zoom
        return world_x, world_y

    # Loop principal
    clock = pygame.time.Clock()
    running = True
    threads = []

    for fac in facs:
        t = threading.Thread(target=fac.run_faction, name=fac.name, daemon=True)
        t.start()
        threads.append(t)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            # Controle de zoom com roda do mouse
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:  # Rola para cima - Zoom in
                    # Zoom no ponto do mouse
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    world_x, world_y = screen_to_world(mouse_x, mouse_y, zoom_level, offset_x, offset_y)
                    zoom_level = min(max_zoom, zoom_level + zoom_speed)
                    # Ajustar offset para zoom no ponto do mouse
                    offset_x = world_x - (mouse_x - WIDTH / 2) / zoom_level
                    offset_y = world_y - (mouse_y - HEIGHT / 2) / zoom_level
                    
                elif event.button == 5:  # Rola para baixo - Zoom out
                    # Zoom no ponto do mouse
                    mouse_x, mouse_y = pygame.mouse.get_pos()
                    world_x, world_y = screen_to_world(mouse_x, mouse_y, zoom_level, offset_x, offset_y)
                    zoom_level = max(min_zoom, zoom_level - zoom_speed)
                    # Ajustar offset para zoom no ponto do mouse
                    offset_x = world_x - (mouse_x - WIDTH / 2) / zoom_level
                    offset_y = world_y - (mouse_y - HEIGHT / 2) / zoom_level
                    
                elif event.button == 1:  # Botão esquerdo do mouse - Iniciar arrasto
                    dragging = True
                    last_mouse_x, last_mouse_y = pygame.mouse.get_pos()
            
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:  # Botão esquerdo do mouse - Parar arrasto
                    dragging = False
            
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r:  # Resetar zoom e posição
                    zoom_level = 1.0
                    offset_x, offset_y = 0, 0
        
        # Arrastar o mapa
        if dragging:
            mouse_x, mouse_y = pygame.mouse.get_pos()
            dx = (mouse_x - last_mouse_x) / zoom_level
            dy = (mouse_y - last_mouse_y) / zoom_level
            offset_x -= dx
            offset_y -= dy
            last_mouse_x, last_mouse_y = mouse_x, mouse_y
        
        # Limpar a tela
        screen.fill(BACKGROUND)
        
        # Desenhar grade de fundo
        grid_size = 100
        for x in range(-2000, 2000, grid_size):
            for y in range(-2000, 2000, grid_size):
                screen_x, screen_y = world_to_screen(x, y, zoom_level, offset_x, offset_y)
                if 0 <= screen_x <= WIDTH and 0 <= screen_y <= HEIGHT:
                    pygame.draw.circle(screen, (80, 80, 100), (screen_x, screen_y), 1)
        
        # Desenhar círculos
        for star in stars:
            screen_x, screen_y = world_to_screen(star.position[0], star.position[1], zoom_level, offset_x, offset_y)
            radius = max(1, int(star.radius * zoom_level))  # Garantir que o raio seja pelo menos 1 pixel

            # Só desenhar se estiver dentro da tela
            if -radius <= screen_x <= WIDTH + radius and -radius <= screen_y <= HEIGHT + radius:
                pygame.draw.circle(screen, YELLOW, (screen_x, screen_y), radius)
                pygame.draw.circle(screen, (255, 255, 255), (screen_x, screen_y), radius, 1)

            for planet in star.planets:
                screen_x, screen_y = world_to_screen(planet.abs_position[0], planet.abs_position[1], zoom_level, offset_x, offset_y)
                radius = max(1, int(planet.radius * zoom_level))  # Garantir que o raio seja pelo menos 1 pixel
                
                # Só desenhar se estiver dentro da tela
                if -radius <= screen_x <= WIDTH + radius and -radius <= screen_y <= HEIGHT + radius:
                    pygame.draw.circle(screen, WHITE, (screen_x, screen_y), radius)
                    pygame.draw.circle(screen, (255, 255, 255), (screen_x, screen_y), radius, 1)

            for faction in facs:
                for ship in faction.ships:
                    ship
        
        # Desenhar informações na tela
        info_text = f"Zoom: {zoom_level:.1f}x | Posição: ({offset_x:.0f}, {offset_y:.0f})"
        text_surface = font.render(info_text, True, (200, 200, 200))
        screen.blit(text_surface, (10, 10))
        
        help_text = "Use a roda do mouse para zoom | Arraste com botão esquerdo | R para resetar"
        help_surface = font.render(help_text, True, (150, 150, 150))
        screen.blit(help_surface, (10, HEIGHT - 30))
        
        # Atualizar a tela
        pygame.display.flip()
        clock.tick(60)

if __name__ == '__main__':
    main()