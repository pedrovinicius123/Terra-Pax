import pygame


class GalaxySelectionScreen:
    OPTIONS = (
        ("standard", "GALÁXIA PADRÃO", "60 sistemas · 10 facções"),
        ("compact", "GALÁXIA COMPACTA", "30 sistemas · 6 facções"),
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

        stacked = width < 560
        card_width = (
            max(180, width - 40) if stacked
            else min(360, (width - 72) // 2)
        )
        card_height = 112 if stacked else 150
        gap = 12 if stacked else 20
        start_x = (
            (width - card_width) // 2 if stacked
            else (width - (card_width * 2 + gap)) // 2
        )
        card_y = (
            (height - (card_height * 2 + gap)) // 2
            if stacked else (height - card_height) // 2 + 55
        )
        self.option_rects = []
        for index, (_, label, details) in enumerate(self.OPTIONS):
            rect = pygame.Rect(
                start_x if stacked else start_x + index * (card_width + gap),
                card_y + index * (card_height + gap) if stacked else card_y,
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
            title = self.body_font.render(label, True, (224, 237, 247))
            detail = self.small_font.render(details, True, (136, 180, 203))
            screen.blit(title, title.get_rect(
                center=(rect.centerx, rect.centery - 12)))
            screen.blit(detail, detail.get_rect(
                center=(rect.centerx, rect.centery + 22)))
