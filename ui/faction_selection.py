import math

import pygame

from players.factions import FACTION_TRAITS


class FactionSelectionScreen:
    def __init__(self, screen, factions):
        self.screen = screen
        self.factions = factions
        self.selected_index = 0
        self.card_rects = []
        self.confirm_rect = pygame.Rect(0, 0, 0, 0)
        self.title_font = pygame.font.SysFont('Consolas', 30, bold=True)
        self.body_font = pygame.font.SysFont('Consolas', 16)
        self.small_font = pygame.font.SysFont('Consolas', 13)

    def on_resize(self, screen):
        self.screen = screen

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.factions[self.selected_index]
            if event.key in (pygame.K_RIGHT, pygame.K_DOWN):
                self.selected_index = (
                    self.selected_index + 1) % len(self.factions)
            elif event.key in (pygame.K_LEFT, pygame.K_UP):
                self.selected_index = (
                    self.selected_index - 1) % len(self.factions)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.card_rects):
                if rect.collidepoint(event.pos):
                    self.selected_index = index
                    return None
            if self.confirm_rect.collidepoint(event.pos):
                return self.factions[self.selected_index]
        return None

    def draw(self):
        screen = self.screen
        width, height = screen.get_size()
        screen.fill((7, 12, 25))
        title = self.title_font.render(
            "ESCOLHA SUA FACÇÃO", True, (224, 237, 247))
        screen.blit(title, title.get_rect(center=(width // 2, 45)))
        subtitle = self.small_font.render(
            "Selecione uma facção para comandar; as demais serão controladas "
            "pela IA.", True, (136, 160, 181))
        screen.blit(subtitle, subtitle.get_rect(center=(width // 2, 82)))

        margin = 28
        max_columns = max(1, min(4, (width - margin * 2) // 250))
        max_rows = max(1, (height - 210) // 130)
        columns = min(max_columns, math.ceil(len(self.factions) / max_rows))
        rows = math.ceil(len(self.factions) / columns)
        gap = 12
        card_width = (width - margin * 2 - gap * (columns - 1)) // columns
        grid_height = max(0, height - 220)
        card_height = min(154, (grid_height - gap * (rows - 1)) // rows)
        card_height = max(70, card_height)
        grid_top = max(112, (height - rows * card_height
                             - (rows - 1) * gap) // 2)

        self.card_rects = []
        for index, faction in enumerate(self.factions):
            row, column = divmod(index, columns)
            rect = pygame.Rect(
                margin + column * (card_width + gap),
                grid_top + row * (card_height + gap),
                card_width, card_height,
            )
            self.card_rects.append(rect)
            selected = index == self.selected_index
            faction_color = tuple(
                int(faction.color[offset:offset + 2], 16)
                for offset in (1, 3, 5))
            background = (24, 45, 66) if selected else (13, 23, 41)
            pygame.draw.rect(screen, background, rect, border_radius=8)
            pygame.draw.rect(
                screen, faction_color if selected else (40, 67, 93),
                rect, 2 if selected else 1, border_radius=8)
            name = self.body_font.render(
                faction.name, True, (224, 237, 247))
            screen.blit(name, (rect.x + 12, rect.y + 12))
            kind = self.small_font.render(
                faction.faction_type.value, True, faction_color)
            screen.blit(kind, (rect.x + 12, rect.y + 38))
            description = faction.description
            max_chars = max(12, (card_width - 24) // 8)
            if len(description) > max_chars:
                description = description[:max_chars - 3] + "..."
            detail = self.small_font.render(
                description, True, (136, 160, 181))
            screen.blit(detail, (rect.x + 12, rect.y + 62))
            state = "JOGADOR" if selected else "IA"
            label = self.small_font.render(
                state, True, faction_color if selected else (136, 160, 181))
            screen.blit(label, (rect.x + 12, rect.bottom - 24))

        self.confirm_rect = pygame.Rect(
            width // 2 - 110, height - 62, 220, 38)
        pygame.draw.rect(screen, (37, 104, 128), self.confirm_rect,
                         border_radius=6)
        pygame.draw.rect(screen, (89, 201, 219), self.confirm_rect, 1,
                         border_radius=6)
        label = self.body_font.render(
            "INICIAR PARTIDA", True, (224, 237, 247))
        screen.blit(label, label.get_rect(center=self.confirm_rect.center))


class FactionCustomizationScreen:
    def __init__(self, screen, faction, other_names=()):
        self.screen = screen
        self.faction = faction
        self.name = faction.name
        self.other_names = {
            name.casefold() for name in other_names if name != faction.name}
        self.error = ""
        self.advantage = faction.advantage
        self.disadvantage = faction.disadvantage
        self.name_rect = pygame.Rect(0, 0, 460, 42)
        self.advantage_rect = pygame.Rect(0, 0, 460, 64)
        self.disadvantage_rect = pygame.Rect(0, 0, 460, 64)
        self.start_rect = pygame.Rect(0, 0, 220, 42)
        self.title_font = pygame.font.SysFont("Consolas", 30, bold=True)
        self.body_font = pygame.font.SysFont("Consolas", 17)
        self.small_font = pygame.font.SysFont("Consolas", 14)

    def on_resize(self, screen):
        self.screen = screen

    def _cycle_trait(self, field, direction):
        options = tuple(FACTION_TRAITS)
        current = getattr(self, field)
        index = options.index(current)
        for offset in range(1, len(options) + 1):
            candidate = options[(index + direction * offset) % len(options)]
            other = self.disadvantage if field == "advantage" else self.advantage
            if candidate != other:
                setattr(self, field, candidate)
                return

    def _finish(self):
        name = self.name.strip()
        if not name:
            self.error = "O nome da facção não pode ficar vazio."
            return None
        if name.casefold() in self.other_names:
            self.error = "Esse nome já está sendo usado por outra facção."
            return None
        self.faction.name = name[:24]
        self.faction.advantage = self.advantage
        self.faction.disadvantage = self.disadvantage
        return self.faction

    def handle_event(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self._finish()
            if event.key == pygame.K_ESCAPE:
                return None
            if event.key == pygame.K_BACKSPACE:
                self.name = self.name[:-1]
                self.error = ""
            elif (event.key == pygame.K_a
                  and getattr(event, "mod", 0) & pygame.KMOD_CTRL):
                self.name = ""
                self.error = ""
            elif getattr(event, "unicode", "").isprintable():
                if len(self.name) < 24:
                    self.name += event.unicode
                    self.error = ""
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.advantage_rect.collidepoint(event.pos):
                self._cycle_trait("advantage", 1)
            elif self.disadvantage_rect.collidepoint(event.pos):
                self._cycle_trait("disadvantage", 1)
            elif self.start_rect.collidepoint(event.pos):
                return self._finish()
        return None

    def draw(self):
        screen = self.screen
        width, height = screen.get_size()
        screen.fill((7, 12, 25))
        title = self.title_font.render(
            "PERSONALIZE SUA FACÇÃO", True, (224, 237, 247))
        screen.blit(title, title.get_rect(center=(width // 2, height // 4)))
        subtitle = self.small_font.render(
            "Ctrl+A e digite um nome; clique nos traços para alternar.",
            True, (136, 160, 181))
        screen.blit(subtitle, subtitle.get_rect(
            center=(width // 2, height // 4 + 42)))

        center_x = width // 2
        self.name_rect.topleft = (center_x - 230, height // 2 - 100)
        self.advantage_rect.topleft = (center_x - 230, height // 2 - 28)
        self.disadvantage_rect.topleft = (center_x - 230, height // 2 + 54)
        self.start_rect.topleft = (center_x - 110, height // 2 + 150)
        pygame.draw.rect(screen, (13, 23, 41), self.name_rect,
                         border_radius=6)
        pygame.draw.rect(screen, (40, 67, 93), self.name_rect, 1,
                         border_radius=6)
        label = self.small_font.render(
            "NOME", True, (136, 160, 181))
        screen.blit(label, (self.name_rect.x, self.name_rect.y - 20))
        name_surface = self.body_font.render(
            self.name or "Digite um nome", True, (224, 237, 247))
        screen.blit(name_surface, (self.name_rect.x + 12,
                                   self.name_rect.y + 11))
        if self.error:
            error = self.small_font.render(
                self.error, True, (226, 112, 121))
            screen.blit(error, (self.name_rect.x, self.name_rect.bottom + 2))

        for rect, label, trait in (
                (self.advantage_rect, "VANTAGEM", self.advantage),
                (self.disadvantage_rect, "DESVANTAGEM", self.disadvantage)):
            pygame.draw.rect(screen, (13, 23, 41), rect, border_radius=6)
            pygame.draw.rect(screen, (40, 67, 93), rect, 1,
                             border_radius=6)
            name, description = FACTION_TRAITS[trait]
            screen.blit(self.small_font.render(
                label, True, (136, 160, 181)),
                (rect.x + 12, rect.y + 8))
            screen.blit(self.body_font.render(
                name, True, (89, 201, 219)),
                (rect.x + 12, rect.y + 27))
            screen.blit(self.small_font.render(
                description, True, (224, 237, 247)),
                (rect.x + 146, rect.y + 30))

        pygame.draw.rect(screen, (37, 104, 128), self.start_rect,
                         border_radius=6)
        pygame.draw.rect(screen, (89, 201, 219), self.start_rect, 1,
                         border_radius=6)
        label = self.body_font.render(
            "INICIAR PARTIDA", True, (224, 237, 247))
        screen.blit(label, label.get_rect(center=self.start_rect.center))
