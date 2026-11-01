import pygame


class GalaxySelectionScreen:
    OPTIONS = (
        ("tiny", "GALÁXIA MINÚSCULA", "20 sistemas · 4 facções"),
        ("compact", "GALÁXIA PEQUENA", "30 sistemas · 6 facções"),
        ("medium", "GALÁXIA MÉDIA", "60 sistemas · 10 facções"),
        ("large", "GALÁXIA GRANDE", "100 sistemas · 10 facções"),
        ("giant", "GALÁXIA GIGANTE", "160 sistemas · 10 facções"),
    )

    def __init__(self, screen):
        self.screen = screen
        self.selected_index = 0
        self.option_rects = []
        self.title_font = pygame.font.SysFont("Consolas", 30, bold=True)
        self.body_font = pygame.font.SysFont("Consolas", 19, bold=True)
        self.small_font = pygame.font.SysFont("Consolas", 15)

    def on_resize(self, screen):
        self.screen = screen

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.OPTIONS[self.selected_index][0]
            if event.key in (pygame.K_LEFT, pygame.K_UP):
                self.selected_index = (
                    self.selected_index - 1) % len(self.OPTIONS)
            elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                self.selected_index = (
                    self.selected_index + 1) % len(self.OPTIONS)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.option_rects):
                if rect.collidepoint(event.pos):
                    self.selected_index = index
                    return self.OPTIONS[index][0]
        return None

    def draw(self):
        screen = self.screen
        width, height = screen.get_size()
        screen.fill((7, 12, 25))
        title = self.title_font.render(
            "ESCOLHA O TAMANHO DA GALÁXIA", True, (224, 237, 247))
        screen.blit(title, title.get_rect(center=(width // 2, height // 3)))
        subtitle = self.small_font.render(
            "Use as setas e Enter, ou clique em uma opção.",
            True, (136, 160, 181))
        screen.blit(
            subtitle, subtitle.get_rect(center=(width // 2, height // 3 + 46)))

        columns = max(1, min(3, (width - 48) // 220))
        rows = (len(self.OPTIONS) + columns - 1) // columns
        gap = 12
        card_width = (width - 40 - gap * (columns - 1)) // columns
        card_height = min(
            112, max(64, (height - 240 - gap * (rows - 1)) // rows))
        grid_width = columns * card_width + (columns - 1) * gap
        start_x = (width - grid_width) // 2
        grid_height = rows * card_height + (rows - 1) * gap
        card_y = max(height // 3 + 25, (height - grid_height) // 2 + 45)
        self.option_rects = []
        for index, (_, label, details) in enumerate(self.OPTIONS):
            row, column = divmod(index, columns)
            rect = pygame.Rect(
                start_x + column * (card_width + gap),
                card_y + row * (card_height + gap),
                card_width, card_height,
            )
            self.option_rects.append(rect)
            selected = index == self.selected_index
            border = (89, 201, 219) if selected else (40, 67, 93)
            background = (24, 45, 66) if selected else (13, 23, 41)
            pygame.draw.rect(screen, background, rect, border_radius=8)
            pygame.draw.rect(
                screen, border, rect, 2 if selected else 1,
                border_radius=8)
            title = self.small_font.render(label, True, (224, 237, 247))
            detail = self.small_font.render(details, True, (136, 180, 203))
            screen.blit(title, title.get_rect(
                center=(rect.centerx, rect.centery - 12)))
            screen.blit(detail, detail.get_rect(
                center=(rect.centerx, rect.centery + 22)))


class VictorySelectionScreen:
    OPTIONS = (
        ("diplomatic", "DIPLOMÁTICA",
         "Alie-se a todas as facções; relações mais difíceis."),
        ("domination", "DOMINAÇÃO",
         "Conquiste os impérios rivais e elimine seus comandantes."),
        ("economic", "ECONÔMICA",
         "Expanda produção, reservas e acordos comerciais."),
        ("expansion", "EXPANSÃO",
         "Lidere em população no ano 3000; Biotech acelera o crescimento."),
        ("scientific", "CIENTÍFICA",
         "Pesquise todos os campos até o nível máximo."),
        ("standard", "PADRÃO",
         "Quem tiver mais força total em 3000 vence."),
    )

    def __init__(self, screen):
        self.screen = screen
        self.selected_index = 5
        self.option_rects = []
        self.title_font = pygame.font.SysFont("Consolas", 30, bold=True)
        self.body_font = pygame.font.SysFont("Consolas", 15, bold=True)
        self.small_font = pygame.font.SysFont("Consolas", 12)

    def on_resize(self, screen):
        self.screen = screen

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.OPTIONS[self.selected_index][0]
            if event.key in (pygame.K_LEFT, pygame.K_UP):
                self.selected_index = (
                    self.selected_index - 1) % len(self.OPTIONS)
            elif event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                self.selected_index = (
                    self.selected_index + 1) % len(self.OPTIONS)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.option_rects):
                if rect.collidepoint(event.pos):
                    self.selected_index = index
                    return self.OPTIONS[index][0]
        return None

    def draw(self):
        screen = self.screen
        width, height = screen.get_size()
        screen.fill((7, 12, 25))
        title = self.title_font.render(
            "ESCOLHA A CONDIÇÃO DE VITÓRIA", True, (224, 237, 247))
        screen.blit(title, title.get_rect(center=(width // 2, height // 4)))
        subtitle = self.small_font.render(
            "Use as setas e Enter, ou clique em uma opção.",
            True, (136, 160, 181))
        screen.blit(subtitle, subtitle.get_rect(
            center=(width // 2, height // 4 + 42)))

        columns = max(1, min(3, (width - 48) // 230))
        rows = (len(self.OPTIONS) + columns - 1) // columns
        gap = 10
        card_width = (width - 40 - gap * (columns - 1)) // columns
        card_height = min(
            116, max(44, (height - 220 - gap * (rows - 1)) // rows))
        grid_width = columns * card_width + (columns - 1) * gap
        start_x = (width - grid_width) // 2
        grid_height = rows * card_height + (rows - 1) * gap
        start_y = max(height // 3 + 25, (height - grid_height) // 2 + 35)
        self.option_rects = []
        for index, (_, label, details) in enumerate(self.OPTIONS):
            row, column = divmod(index, columns)
            rect = pygame.Rect(
                start_x + column * (card_width + gap),
                start_y + row * (card_height + gap),
                card_width, card_height)
            self.option_rects.append(rect)
            selected = index == self.selected_index
            border = (89, 201, 219) if selected else (40, 67, 93)
            pygame.draw.rect(
                screen, (24, 45, 66) if selected else (13, 23, 41),
                rect, border_radius=8)
            pygame.draw.rect(
                screen, border, rect, 2 if selected else 1,
                border_radius=8)
            label_surface = self.body_font.render(
                label, True, (224, 237, 247))
            detail_surface = self.small_font.render(
                details, True, (136, 180, 203))
            screen.blit(label_surface, label_surface.get_rect(
                center=(rect.centerx, rect.centery - 13)))
            screen.blit(detail_surface, detail_surface.get_rect(
                center=(rect.centerx, rect.centery + 14)))
