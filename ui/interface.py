import math
import numpy as np
import pygame

from players.factions import (
    DESIGNS,
    DiplomacyStatus,
    FACTION_TRAITS,
    GALACTIC_WONDERS,
    TECH_CAPS,
)
from players.ships import ColonyShip, Scout, Transport, Warship
from graphics.planet_generator import (
    city_light_intensity,
    dominant_suitability,
    generate_planet_surface,
)
from graphics.ship_sprites import get_ship_sprite
from logistics.game_3d import PlanetViewer3D


class C:
    BG          = (7, 12, 25)
    GRID        = (22, 36, 57)
    STAR        = (255, 207, 117)
    STAR_BORDER = (255, 239, 190)
    PLANET_FREE_GOOD = (82, 220, 177)
    PLANET_FREE_MID  = (236, 190, 103)
    PLANET_FREE_LOW  = (226, 112, 121)
    PLANET_MINE      = (82, 220, 177)
    PLANET_ENEMY     = (226, 112, 121)
    SELECTED    = (124, 224, 255)
    PANEL_BG    = (13, 23, 41)
    PANEL_BR    = (40, 67, 93)
    TEXT        = (224, 237, 247)
    DIM         = (136, 160, 181)
    ACCENT      = (89, 201, 219)
    BUTTON      = (26, 48, 72)
    BUTTON_HOV  = (41, 79, 107)
    BUTTON_DIS  = (25, 33, 45)
    TAB_ACTIVE  = (37, 104, 128)
    INFLUENCE   = (35, 55, 90)
    SIEGE       = (255, 91, 104)

    RES = {
        'Minerals':    (150, 150, 100),
        'Food':        (110, 200, 120),
        'Energy':      (255, 230, 90),
        'Electronics': (110, 160, 255),
        'Chemicals':   (200, 110, 200),
        'Alloys':      (200, 150, 100),
        'Credits':     (255, 205, 85),
        'Research':    (110, 255, 210),
    }


class Button:
    def __init__(self, rect, text, callback, enabled=None, tooltip=None):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.cb = callback
        self.enabled_check = enabled
        self.tooltip = tooltip
        self.hover = False

    def enabled(self):
        return self.enabled_check() if self.enabled_check else True

    def draw(self, screen, font, active=False):
        if active:
            col = C.TAB_ACTIVE
        elif not self.enabled():
            col = C.BUTTON_DIS
        else:
            col = C.BUTTON_HOV if self.hover else C.BUTTON
        pygame.draw.rect(screen, col, self.rect, border_radius=4)
        pygame.draw.rect(screen, C.PANEL_BR, self.rect, 1, border_radius=4)
        surf = font.render(self.text, True,
                           C.TEXT if self.enabled() else C.DIM)
        screen.blit(surf, surf.get_rect(center=self.rect.center))

    def hit(self, pos):
        return self.rect.collidepoint(pos) and self.enabled()


class _FakeLabel:
    def __init__(self, rect, text, font, color=C.DIM):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.font = font
        self.color = color

    def draw(self, screen):
        screen.blit(self.font.render(self.text, True, self.color),
                    self.rect.topleft)


class _NumericSlider:
    def __init__(self, rect, label, minimum, maximum, value, on_change):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.minimum = minimum
        self.maximum = maximum
        self.value = value
        self.on_change = on_change
        self.dragging = False

    def _set_from_x(self, x):
        ratio = (x - self.rect.left) / max(1, self.rect.width)
        value = round(self.minimum + ratio * (self.maximum - self.minimum))
        value = max(self.minimum, min(self.maximum, value))
        if value != self.value:
            self.value = value
            self.on_change(value)

    def handle_event(self, event):
        if (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
                and self.rect.collidepoint(event.pos)):
            self.dragging = True
            self._set_from_x(event.pos[0])
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self._set_from_x(event.pos[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was_dragging = self.dragging
            self.dragging = False
            return was_dragging
        return False

    def draw(self, screen, font):
        label = font.render(
            f"{self.label}: {self.value}", True, C.TEXT)
        screen.blit(label, (self.rect.x, self.rect.y - 20))
        center_y = self.rect.centery
        start_x = self.rect.left + 10
        end_x = self.rect.right - 10
        pygame.draw.line(screen, C.PANEL_BR, (start_x, center_y),
                         (end_x, center_y), 4)
        for value in range(self.minimum, self.maximum + 1):
            ratio = ((value - self.minimum)
                     / (self.maximum - self.minimum))
            x = round(start_x + ratio * (end_x - start_x))
            color = C.ACCENT if value <= self.value else C.DIM
            pygame.draw.circle(screen, color, (x, center_y), 7)
            pygame.draw.circle(screen, C.PANEL_BG, (x, center_y), 3)
            numeral = font.render(str(value), True, C.DIM)
            screen.blit(numeral, numeral.get_rect(
                center=(x, self.rect.bottom + 10)))


class GameUI:
    PANEL_W = 420
    TOP_H   = 36
    BOT_H   = 144
    DEFAULT_ZOOM = 0.45
    MIN_ZOOM = 0.05
    MAX_ZOOM = 120.0
    PANEL_LIST_TOP = TOP_H + 86

    def __init__(self, screen, state, player_ctrl):
        self.screen = screen
        self.W, self.H = screen.get_size()
        self.state = state
        self.player = player_ctrl
        self.faction = player_ctrl.faction
        self.restart_requested = False

        self.zoom = self.DEFAULT_ZOOM
        self.off_x = 0
        self.off_y = 0
        self.dragging = False
        self.last_mouse = (0, 0)
        self.selected_star = None
        self.selected_planet = None
        self.hovered_star = None
        self.filter_mode = 'all'

        self.tabs = ['resources', 'system', 'research', 'fleet',
                     'colonies', 'build', 'war', 'visual']
        self.tab_labels = {
            'resources': 'Recursos', 'system': 'Sistema',
            'research': 'Pesquisa', 'fleet': 'Frota',
            'colonies': 'Colônias',
            'build': 'Construir', 'war': 'Diplom.',
            'visual': 'Visual',
        }
        self.active_tab = 'resources'
        self.texture_detail = 3
        self._scrollable_tabs = {'build', 'fleet', 'colonies', 'war'}
        self._panel_scroll = {tab: 0 for tab in self._scrollable_tabs}
        self._panel_content_height = 0

        self.f_small = pygame.font.SysFont('Consolas', 11)
        self.f_tab   = pygame.font.SysFont('Consolas', 10)
        self.f       = pygame.font.SysFont('Consolas', 13)
        self.f_med   = pygame.font.SysFont('Consolas', 14, bold=True)
        self.f_title = pygame.font.SysFont('Consolas', 18, bold=True)

        self.log = []
        self._planet_surfaces = {}
        self._map_planet_surfaces = {}
        self.planet_viewer = None
        self._last_event_idx = 0
        self._top_buttons = []
        self._filter_buttons = []
        self._tab_buttons = []
        self._panel_buttons = []
        self._texture_slider = None
        self._action_buttons = []

        self._build_top_buttons()
        self._build_filter_buttons()
        self._build_tab_buttons()
        self._rebuild_panel_buttons()
        self._center_map_on_galaxy()

    def on_resize(self, screen):
        self.screen = screen
        self.W, self.H = screen.get_size()
        self._build_top_buttons()
        self._build_filter_buttons()
        self._build_tab_buttons()
        self._rebuild_panel_buttons()
        self._action_buttons = []

    def log_msg(self, m):
        self.log.append(m)
        self.log = self.log[-7:]

    def _sync_events(self):
        events = getattr(self.state, 'event_log', None)
        if events is None:
            return
        while self._last_event_idx < len(events):
            entry = events[self._last_event_idx]
            if isinstance(entry, tuple) and len(entry) == 2:
                _, msg = entry
            else:
                msg = str(entry)
            self.log_msg(msg)
            self._last_event_idx += 1

    # ---------- Botões ----------
    def _build_top_buttons(self):
        self._top_buttons = [
            Button((self.W - 382, 6, 72, 24), "Pausa", self._toggle_pause),
            Button((self.W - 302, 6, 42, 24), "1x",
                   lambda: self._set_speed(1.0)),
            Button((self.W - 252, 6, 42, 24), "2x",
                   lambda: self._set_speed(2.0)),
            Button((self.W - 202, 6, 42, 24), "5x",
                   lambda: self._set_speed(5.0)),
            Button((self.W - 148, 6, 138, 24), "NOVO JOGO",
                   self._request_restart),
        ]

    def _build_filter_buttons(self):
        # Posicionado à esquerda do painel, relativo à largura
        base_x = self.W - self.PANEL_W - 235
        y = 6
        self._filter_buttons = []
        for mode, label in [('all', 'Todos'), ('mine', 'Minhas'),
                            ('free', 'Livres')]:
            self._filter_buttons.append(
                Button((base_x, y, 70, 24), label,
                       lambda m=mode: self._set_filter(m)))
            base_x += 74

    def _build_tab_buttons(self):
        x0 = self.W - self.PANEL_W + 2
        y = self.TOP_H + 8
        n = len(self.tabs)
        w = (self.PANEL_W - 8) // n
        self._tab_buttons = []
        for i, t in enumerate(self.tabs):
            bx = x0 + i * (w + 1)
            self._tab_buttons.append(
                Button((bx, y, w, 24), self.tab_labels[t],
                       lambda tab=t: self._switch_tab(tab)))

    def _center_map_on_galaxy(self):
        if not self.state.stars:
            return
        self.off_x = sum(star.position[0] for star in self.state.stars) / len(
            self.state.stars)
        self.off_y = sum(star.position[1] for star in self.state.stars) / len(
            self.state.stars)

    def _panel_viewport(self):
        panel_x = self.W - self.PANEL_W
        return pygame.Rect(
            panel_x + 6, self.PANEL_LIST_TOP, self.PANEL_W - 24,
            max(0, self.H - self.PANEL_LIST_TOP - 10),
        )

    def _visible_panel_rect(self, button):
        if self.active_tab in self._scrollable_tabs:
            return button.rect.move(0, -self._panel_scroll[self.active_tab])
        return button.rect

    def _scroll_active_panel(self, amount):
        if self.active_tab not in self._scrollable_tabs:
            return
        viewport = self._panel_viewport()
        max_scroll = max(0, self._panel_content_height - viewport.height)
        self._panel_scroll[self.active_tab] = max(
            0, min(max_scroll,
                   self._panel_scroll[self.active_tab] + amount))

    def _toggle_pause(self):
        self.state.paused = not self.state.paused
        self.log_msg("Pausado" if self.state.paused else "Retomado")

    def _request_restart(self):
        self.restart_requested = True

    def _set_speed(self, s):
        self.state.speed = s

    def _set_filter(self, mode):
        self.filter_mode = mode

    def _switch_tab(self, tab):
        self.active_tab = tab
        self._rebuild_panel_buttons()

    def _set_texture_detail(self, value):
        if value == self.texture_detail:
            return
        self.texture_detail = value
        self._planet_surfaces.clear()
        self._map_planet_surfaces.clear()
        if self.planet_viewer is not None:
            self.planet_viewer.set_detail_level(value)

    def _set_research(self, tech):
        if self.player.set_research(tech):
            self.log_msg(f"Foco de pesquisa: {tech}")
            self._rebuild_panel_buttons()

    def _build(self, design_key):
        if self.player.build_ship(design_key):
            self.log_msg(f"Fila: {DESIGNS[design_key]['display']}")
        else:
            self.log_msg("Recursos insuficientes")

    def _select_ship(self, ship):
        self.player.selected_ship = ship
        self.off_x, self.off_y = ship.abs_position
        self.log_msg(f"Selecionada {ship.ship_id}")

    def _select_colony(self, planet):
        self.selected_star = planet.parent_star
        self.selected_planet = planet
        self.player.select(planet.parent_star, planet)
        self.off_x, self.off_y = planet.parent_star.position
        self._rebuild_panel_buttons()
        self._rebuild_action_buttons()

    def _send_colonizer_to(self, planet):
        star = planet.parent_star
        if self.player.send_colony_ship(star, planet):
            self.log_msg(f"Colonizador -> {planet.name}")
            self._rebuild_panel_buttons()
        else:
            self.log_msg("Nenhum colonizador ocioso")

    def _terraform(self, planet):
        if self.player.terraform(planet):
            self.log_msg(f"Terraformando {planet.name}")
            self._rebuild_panel_buttons()
        else:
            self.log_msg("Recursos insuficientes")

    def _toggle_auto_colonize(self):
        on = self.player.toggle_auto_colonize()
        self.log_msg(f"Auto-colonizar: {'ON' if on else 'OFF'}")
        self._rebuild_panel_buttons()

    def _toggle_auto_terraform(self):
        on = self.player.toggle_auto_terraform()
        self.log_msg(f"Auto-terraform: {'ON' if on else 'OFF'}")
        self._rebuild_panel_buttons()

    def _declare_war(self, other):
        self.player.declare_war(other)
        self.log_msg(f"Guerra: {other.name}")
        self._rebuild_panel_buttons()

    def _make_peace(self, other):
        self.player.make_peace(other)
        self.log_msg(f"Paz: {other.name}")
        self._rebuild_panel_buttons()

    def _respond_to_peace_offer(self, other, accept):
        if self.player.respond_to_peace_offer(other, accept):
            decision = "aceita" if accept else "recusada"
            self.log_msg(f"Proposta de paz {decision}: {other.name}")
        self._rebuild_panel_buttons()

    def _propose_alliance(self, other):
        if self.player.propose_alliance(other):
            self.log_msg(f"Aliança: {other.name}")
            self._rebuild_panel_buttons()
        else:
            threshold = 85 if self.state.victory_mode == 'diplomatic' else 70
            self.log_msg(
                f"Aliança exige comércio ativo e relação ≥ {threshold}")

    def _build_wonder(self, wonder_type):
        wonder = GALACTIC_WONDERS[wonder_type]
        if self.faction.build_wonder(wonder_type):
            self.log_msg(f"Maravilha construída: {wonder['name']}")
        else:
            self.log_msg("Maravilha indisponível ou recursos insuficientes")
        self._rebuild_panel_buttons()

    def _break_alliance(self, other):
        if self.player.break_alliance(other):
            self.log_msg(f"Aliança rompida: {other.name}")
            self._rebuild_panel_buttons()

    def _improve_relations(self, other):
        if self.player.improve_relations(other):
            self.log_msg(f"Relações com {other.name} melhoraram (+10)")
        else:
            self.log_msg("Ação indisponível: confira energia, relação ou guerra")
        self._rebuild_panel_buttons()

    def _offer_treaty(self, other, treaty, label):
        if self.player.offer_treaty(other, treaty):
            self.log_msg(f"{label} firmado com {other.name}")
        else:
            threshold = 45 if treaty == 'non_aggression' else 55
            self.log_msg(
                f"{label} recusado: relação mínima {threshold}")
        self._rebuild_panel_buttons()

    # ---------- Painel ----------
    def _planet_action(self, p):
        f = self.faction
        if not p.is_colonized:
            if self.player.has_idle_colony_ship():
                return ("Enviar",
                        lambda pp=p: self._send_colonizer_to(pp), None)
            if f.can_afford(DESIGNS['colony']['cost']):
                return ("Construir",
                        lambda: self._build('colony'),
                        lambda: f.can_afford(DESIGNS['colony']['cost']))
            return ("—", lambda: None, lambda: False)
        if p.faction is f:
            if p.terraform_level < p.max_terraform_level:
                return ("Terraform",
                        lambda pp=p: self._terraform(pp),
                        lambda pp=p: f.can_terraform(pp))
            return ("max", lambda: None, lambda: False)
        return None

    def _rebuild_panel_buttons(self):
        self._panel_buttons = []
        self._texture_slider = None
        x0 = self.W - self.PANEL_W + 10
        content_y = self.TOP_H + 42
        w = self.PANEL_W - 20
        f = self.faction
        self._panel_content_height = 0
        alliance_threshold = (
            85 if self.state.victory_mode == 'diplomatic' else 70)

        if self.active_tab == 'research':
            y = content_y + 24   # pula linha do cabeçalho
            for field in f.tech_tree:
                self._panel_buttons.append(Button(
                    (x0 + w - 52, y - 2, 22, 18), "-",
                    lambda fl=field: self._adjust_weight(fl, -0.5),
                    enabled=lambda fl=field: not f.is_tech_capped(fl)))
                self._panel_buttons.append(Button(
                    (x0 + w - 28, y - 2, 22, 18), "+",
                    lambda fl=field: self._adjust_weight(fl, +0.5),
                    enabled=lambda fl=field: not f.is_tech_capped(fl)))
                y += 40
            self._panel_buttons.append(Button(
                (x0, y + 2, w, 22), "Reset pesos (1x cada)",
                self._reset_research_weights))

        elif self.active_tab == 'build':
            viewport = self._panel_viewport()
            y = viewport.top + 8
            for key, d in DESIGNS.items():
                btn = Button((x0, y, w, 22),
                             f"{d['display']}  [{d['build_time']} meses]",
                             lambda k=key: self._build(k),
                             enabled=lambda dd=d: f.can_afford(dd['cost']))
                self._panel_buttons.append(btn)
                y += 24
                cost_txt = "  ".join(
                    f"{k}:{int(v)}" for k, v in d['cost'].items())
                self._panel_buttons.append(_FakeLabel(
                    (x0 + 4, y, w, 12), cost_txt, self.f_small))
                y += 14
            y += 6
            self._panel_buttons.append(_FakeLabel(
                (x0, y, w, 18), "MARAVILHAS GALÁCTICAS",
                self.f_small, color=C.ACCENT))
            y += 20
            for wonder_type, wonder in GALACTIC_WONDERS.items():
                owner = self.state.wonders_built.get(wonder_type)
                label = (
                    f"{wonder['name']}  ·  concluída por {owner}"
                    if owner else wonder['name'])
                self._panel_buttons.append(Button(
                    (x0, y, w, 22), label,
                    lambda kind=wonder_type: self._build_wonder(kind),
                    enabled=lambda kind=wonder_type, data=wonder: (
                        kind not in self.state.wonders_built
                        and f.can_afford(data['cost']))))
                y += 24
                cost_txt = "  ".join(
                    f"{resource}:{int(amount)}"
                    for resource, amount in wonder['cost'].items())
                self._panel_buttons.append(_FakeLabel(
                    (x0 + 4, y, w, 12), wonder['description'],
                    self.f_small))
                y += 13
                self._panel_buttons.append(_FakeLabel(
                    (x0 + 4, y, w, 12), cost_txt, self.f_small))
                y += 14
            self._panel_content_height = y - viewport.top

        elif self.active_tab == 'fleet':
            viewport = self._panel_viewport()
            y = viewport.top + 8
            groups = (
                ("EXPLORAÇÃO", Scout),
                ("COLONIZAÇÃO", ColonyShip),
                ("COMBATE", Warship),
                ("LOGÍSTICA", Transport),
            )
            ships = [ship for ship in list(f.ships.values()) if ship.alive]
            grouped = set()
            for title, ship_type in groups:
                members = [ship for ship in ships
                           if isinstance(ship, ship_type)]
                grouped.update(id(ship) for ship in members)
                self._panel_buttons.append(_FakeLabel(
                    (x0, y, w, 18), f"{title}  ·  {len(members)}",
                    self.f_small, color=C.ACCENT))
                y += 22
                if not members:
                    self._panel_buttons.append(_FakeLabel(
                        (x0 + 8, y, w - 8, 18),
                        "Nenhuma nave nesta seção", self.f_small))
                    y += 20
                    continue
                for ship in sorted(members, key=lambda item: item.ship_id):
                    design = DESIGNS.get(ship.design_key, {})
                    self._panel_buttons.append(Button(
                        (x0 + 4, y, w - 12, 24),
                        f"{ship.ship_id}  {design.get('display', '?')}",
                        lambda selected=ship: self._select_ship(selected),
                    ))
                    y += 25
                    self._panel_buttons.append(_FakeLabel(
                        (x0 + 10, y, w - 18, 16),
                        f"{ship.activity}  ·  casco {ship.hull:.0f}/"
                        f"{ship.max_hull:.0f}",
                        self.f_small))
                    y += 20
            others = [ship for ship in ships if id(ship) not in grouped]
            if others:
                self._panel_buttons.append(_FakeLabel(
                    (x0, y, w, 18), f"OUTRAS  ·  {len(others)}",
                    self.f_small, color=C.ACCENT))
                y += 22
                for ship in sorted(others, key=lambda item: item.ship_id):
                    design = DESIGNS.get(ship.design_key, {})
                    self._panel_buttons.append(Button(
                        (x0 + 4, y, w - 12, 24),
                        f"{ship.ship_id}  {design.get('display', '?')}",
                        lambda selected=ship: self._select_ship(selected),
                    ))
                    y += 28
            self._panel_content_height = y - viewport.top

        elif self.active_tab == 'colonies':
            viewport = self._panel_viewport()
            y = viewport.top + 8
            colonies = sorted(f.colonies.values(), key=lambda p: p.name)
            home = f.home_planet
            sections = (
                ("CAPITAL", [p for p in colonies if p is home]),
                ("COLÔNIAS", [p for p in colonies if p is not home]),
            )
            for title, members in sections:
                self._panel_buttons.append(_FakeLabel(
                    (x0, y, w, 18), f"{title}  ·  {len(members)}",
                    self.f_small, color=C.ACCENT))
                y += 22
                if not members:
                    self._panel_buttons.append(_FakeLabel(
                        (x0 + 8, y, w - 8, 18),
                        "Nenhuma colônia nesta seção", self.f_small))
                    y += 20
                    continue
                for planet in members:
                    self._panel_buttons.append(Button(
                        (x0 + 4, y, w - 12, 24), planet.name,
                        lambda selected=planet: self._select_colony(selected),
                    ))
                    y += 25
                    self._panel_buttons.append(_FakeLabel(
                        (x0 + 10, y, w - 18, 16),
                        f"{planet.parent_star.name}  ·  pop "
                        f"{planet.population:.0f}  ·  "
                        f"desenv. {planet.developement:.1f}  ·  "
                        f"defesa {planet.defense:.0f}",
                        self.f_small))
                    y += 20
            self._panel_content_height = y - viewport.top

        elif self.active_tab == 'system':
            if self.selected_star is None:
                self._panel_buttons.append(_FakeLabel(
                    (x0, content_y + 22, w, 20),
                    "Selecione uma estrela no mapa", self.f))
                return
            y = content_y + 22
            for p in self.selected_star.planets:
                suit = p.get_suitability(f)
                if p.is_colonized:
                    if p.faction is f:
                        text = f"{p.name[-1]} MINHA tf{p.terraform_level}"
                        col = C.PLANET_MINE
                    elif p.faction:
                        text = f"{p.name[-1]} {p.faction.name[:10]}"
                        col = C.PLANET_ENEMY
                    else:
                        text = f"{p.name[-1]} —"
                        col = C.DIM
                else:
                    hs = p.life_suitability
                    text = (f"{p.name[-1]} livre  "
                            f"H{hs.get('Human',0):.2f} "
                            f"A{hs.get('Alien',0):.2f} "
                            f"R{hs.get('Robot',0):.2f} "
                            f"Y{hs.get('Hybrid',0):.2f}")
                    col = (C.PLANET_FREE_GOOD if suit >= 0.7 else
                        C.PLANET_FREE_MID if suit >= 0.4 else
                        C.PLANET_FREE_LOW)
                    
                self._panel_buttons.append(_FakeLabel(
                    (x0, y, w - 100, 20), text, self.f_small, color=col))
                act = self._planet_action(p)
                if act:
                    lbl, cb, en = act
                    self._panel_buttons.append(
                        Button((x0 + w - 95, y, 95, 20), lbl, cb, enabled=en))
                y += 22

        elif self.active_tab == 'war':
            viewport = self._panel_viewport()
            y = viewport.top + 8
            bw = (w - 4) // 2
            ac_label = f"Auto-colonizar: {'ON' if f.auto_colonize else 'OFF'}"
            at_label = f"Auto-terraform: {'ON' if f.auto_terraform else 'OFF'}"
            self._panel_buttons.append(Button(
                (x0, y, bw, 24), ac_label, self._toggle_auto_colonize))
            self._panel_buttons.append(Button(
                (x0 + bw + 4, y, bw, 24), at_label,
                self._toggle_auto_terraform))
            y += 30

            my_total = f.compute_strength()['total']
            self._panel_buttons.append(_FakeLabel(
                (x0, y, w, 16),
                f"MINHA FORÇA: {my_total:.0f}",
                self.f_med, color=C.ACCENT))
            y += 22
            self._panel_buttons.append(_FakeLabel(
                (x0, y, w, 16), "DIPLOMACIA E FORÇA",
                self.f_med, color=C.ACCENT))
            y += 20

            for other in self.state.factions:
                if other is f:
                    continue
                if other.eliminated:
                    self._panel_buttons.append(_FakeLabel(
                        (x0, y, w, 16),
                        f"{other.name[:18]} — eliminada",
                        self.f_small, color=C.DIM))
                    y += 18
                    continue
                status = f.diplomacy.get(other.name, DiplomacyStatus.NEUTRAL)
                relation = f.get_relation(other)
                their_total = other.compute_strength()['total']
                ratio = (my_total + 1) / (their_total + 1)
                if ratio >= 1.5:
                    ratio_col = (110, 230, 130)   # verde — dominamos
                elif ratio >= 0.8:
                    ratio_col = (230, 200, 80)    # amarelo — equilibrado
                else:
                    ratio_col = (200, 90, 90)     # vermelho — perdendo

                # linha 1: nome + status
                self._panel_buttons.append(_FakeLabel(
                    (x0, y, w, 16),
                    f"{other.name[:18]}  [{status.value}]",
                    self.f_small))
                y += 16
                treaties = []
                if f.has_treaty(other, 'non_aggression'):
                    treaties.append("Não agressão")
                if f.has_treaty(other, 'trade'):
                    treaties.append("Comércio")
                treaty_text = ", ".join(treaties) or "sem tratados"
                self._panel_buttons.append(_FakeLabel(
                    (x0 + 4, y, w - 4, 14),
                    f"Relação {relation:3f}/100 · {treaty_text}",
                    self.f_small, color=ratio_col))
                y += 16
                self._panel_buttons.append(_FakeLabel(
                    (x0 + 4, y, w - 4, 14),
                    f"Força {their_total:.0f} ({ratio:.2f}x nossa)",
                    self.f_small, color=ratio_col))
                y += 16
                if status == DiplomacyStatus.WAR:
                    if other.name in f.pending_peace_offers:
                        self._panel_buttons.append(_FakeLabel(
                            (x0, y, w, 16),
                            f"{other.name[:18]} propõe encerrar a guerra",
                            self.f_small, color=C.ACCENT))
                        y += 18
                        self._panel_buttons.append(Button(
                            (x0, y, 82, 20), "Aceitar paz",
                            lambda o=other: self._respond_to_peace_offer(
                                o, True)))
                        self._panel_buttons.append(Button(
                            (x0 + 88, y, 82, 20), "Recusar",
                            lambda o=other: self._respond_to_peace_offer(
                                o, False)))
                    else:
                        self._panel_buttons.append(Button(
                            (x0, y, 90, 20), "Paz",
                            lambda o=other: self._make_peace(o)))
                elif status == DiplomacyStatus.ALLY:
                    self._panel_buttons.append(Button(
                        (x0, y, 140, 20), "Romper aliança",
                        lambda o=other: self._break_alliance(o)))
                else:
                    action_x = x0
                    actions = (
                        (120, "Relação +10/25E",
                         lambda o=other: self._improve_relations(o),
                         lambda o=other: (
                             f.get_relation(o) < 100
                             and f.resources.get('Energy', 0) >= 25)),
                        (100, ("Pacto ativo" if
                               f.has_treaty(other, 'non_aggression')
                               else "Não agressão"),
                         lambda o=other: self._offer_treaty(
                             o, 'non_aggression', 'Pacto'),
                         lambda o=other: (
                             not f.has_treaty(o, 'non_aggression')
                             and f.get_relation(o) >= 45)),
                        (92, ("Comércio OK" if
                              f.has_treaty(other, 'trade') else "Comércio"),
                         lambda o=other: self._offer_treaty(
                             o, 'trade', 'Acordo comercial'),
                         lambda o=other: (
                             not f.has_treaty(o, 'trade')
                             and f.get_relation(o) >= 55)),
                        (62, "Guerra",
                         lambda o=other: self._declare_war(o), None),
                    )
                    for width, label, callback, enabled in actions:
                        self._panel_buttons.append(Button(
                            (action_x, y, width, 20), label, callback,
                            enabled=(
                                (lambda check=enabled: check())
                                if enabled else None)))
                        action_x += width + 4
                    y += 22
                    self._panel_buttons.append(Button(
                        (x0, y, 140, 20), "Propor aliança",
                        lambda o=other: self._propose_alliance(o),
                        enabled=lambda o=other: (
                            f.get_relation(o) >= alliance_threshold
                            and f.has_treaty(o, 'trade'))))
                y += 24
            self._panel_content_height = y - viewport.top

        elif self.active_tab == 'visual':
            slider_rect = pygame.Rect(
                x0 + 18, content_y + 58, w - 36, 34)
            self._texture_slider = _NumericSlider(
                slider_rect, "Detalhe da textura", 1, 8,
                self.texture_detail, self._set_texture_detail)
        if self.active_tab in self._scrollable_tabs:
            viewport = self._panel_viewport()
            max_scroll = max(
                0, self._panel_content_height - viewport.height)
            self._panel_scroll[self.active_tab] = min(
                self._panel_scroll[self.active_tab], max_scroll)

    # ---------- Coordenadas ----------
    def world_to_screen(self, x, y):
        return (int((x - self.off_x) * self.zoom + self.W / 2),
                int((y - self.off_y) * self.zoom + self.H / 2))

    def screen_to_world(self, x, y):
        return (self.off_x + (x - self.W / 2) / self.zoom,
                self.off_y + (y - self.H / 2) / self.zoom)

    def _should_draw_planet(self, p):
        if self.filter_mode == 'mine':
            return p.is_colonized and p.faction is self.faction
        if self.filter_mode == 'free':
            return not p.is_colonized
        return True

    def _planet_color(self, p):
        if p.is_colonized:
            return (C.PLANET_MINE if p.faction is self.faction
                    else C.PLANET_ENEMY)
        suit = p.get_suitability(self.faction)
        if suit >= 0.7:
            return C.PLANET_FREE_GOOD
        if suit >= 0.4:
            return C.PLANET_FREE_MID
        return C.PLANET_FREE_LOW

    # ---------- Eventos ----------
    def handle_event(self, event):
        if self.planet_viewer is not None:
            if self.planet_viewer.handle_event(event):
                self.planet_viewer = None
            return

        if (self.active_tab == 'visual' and self._texture_slider is not None
                and self._texture_slider.handle_event(event)):
            return

        if event.type == pygame.MOUSEMOTION:
            all_btns = (self._top_buttons + self._filter_buttons
                        + self._tab_buttons + self._action_buttons)
            for b in all_btns:
                b.hover = b.rect.collidepoint(event.pos)
            viewport = self._panel_viewport()
            for b in self._panel_buttons:
                if hasattr(b, 'hover'):
                    b.hover = (
                        viewport.collidepoint(event.pos)
                        and self._visible_panel_rect(b).collidepoint(event.pos)
                    )
            mx, my = event.pos
            if mx < self.W - self.PANEL_W and my > self.TOP_H:
                wx, wy = self.screen_to_world(mx, my)
                nearest, nd = None, 1e9
                for s in self.state.stars:
                    d = math.dist((wx, wy), s.position)
                    if d < nd:
                        nd, nearest = d, s
                self.hovered_star = nearest if nd * self.zoom < 18 else None
            if self.dragging:
                dx = (mx - self.last_mouse[0]) / self.zoom
                dy = (my - self.last_mouse[1]) / self.zoom
                self.off_x -= dx
                self.off_y -= dy
                self.last_mouse = (mx, my)

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:
                for b in (self._top_buttons + self._filter_buttons
                          + self._tab_buttons + self._action_buttons):
                    if hasattr(b, 'hit') and b.hit(event.pos):
                        b.cb()
                        return
                viewport = self._panel_viewport()
                if (self.active_tab in self._scrollable_tabs
                        and viewport.collidepoint(event.pos)):
                    for button in self._panel_buttons:
                        if (isinstance(button, Button)
                                and self._visible_panel_rect(button).collidepoint(
                                    event.pos)
                                and button.enabled()):
                            button.cb()
                            return
                elif self.active_tab not in self._scrollable_tabs:
                    for button in self._panel_buttons:
                        if (hasattr(button, 'hit')
                                and button.hit(event.pos)):
                            button.cb()
                            return
                if (event.pos[0] < self.W - self.PANEL_W
                        and event.pos[1] > self.TOP_H):
                    self._handle_map_click(event.pos)
                    self.dragging = True
                    self.last_mouse = event.pos
            elif event.button == 4:
                if event.pos[0] >= self.W - self.PANEL_W:
                    self._scroll_active_panel(-48)
                else:
                    self._zoom_at(event.pos, +1)
            elif event.button == 5:
                if event.pos[0] >= self.W - self.PANEL_W:
                    self._scroll_active_panel(48)
                else:
                    self._zoom_at(event.pos, -1)

        elif event.type == pygame.MOUSEWHEEL:
            pos = pygame.mouse.get_pos()
            if pos[0] >= self.W - self.PANEL_W:
                self._scroll_active_panel(-event.y * 48)
            else:
                self._zoom_at(pos, event.y)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self._toggle_pause()
            elif event.key == pygame.K_r:
                self.zoom = self.DEFAULT_ZOOM
                self._center_map_on_galaxy()
                self._map_planet_surfaces.clear()
            elif event.key == pygame.K_v:
                self._open_planet_viewer()

    def _zoom_at(self, pos, direction):
        if direction == 0:
            return
        wx, wy = self.screen_to_world(*pos)
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM,
                         self.zoom * (1.2 if direction > 0 else 1 / 1.2)))
        self._map_planet_surfaces.clear()
        self.off_x = wx - (pos[0] - self.W / 2) / self.zoom
        self.off_y = wy - (pos[1] - self.H / 2) / self.zoom

    def _handle_map_click(self, pos):
        wx, wy = self.screen_to_world(*pos)
        best_obj, best_dist = None, float('inf')
        for s in self.state.stars:
            d = math.dist((wx, wy), s.position) * self.zoom
            if d < 14 and d < best_dist:
                best_obj, best_dist = (s, None), d
            for p in s.planets:
                if not self._should_draw_planet(p):
                    continue
                d = math.dist((wx, wy), p.abs_position) * self.zoom
                if d < 8 and d < best_dist:
                    best_obj, best_dist = (s, p), d
        if best_obj:
            self.selected_star, self.selected_planet = best_obj
            self.player.select(*best_obj)
            self._rebuild_panel_buttons()
            self._rebuild_action_buttons()

    def _rebuild_action_buttons(self):
        self._action_buttons = []
        if not self.selected_star:
            return
        x = 10
        y = self.H - self.BOT_H + 104      # era +82 — agora abaixo da barra de defesa
        p = self.selected_planet
        f = self.faction
        if p is None:
            return

        if not p.is_colonized:
            if self.player.has_idle_colony_ship():
                self._action_buttons.append(Button(
                    (x, y, 190, 24), "Enviar colonizador",
                    lambda: self._send_colonizer_to(p)))
                x += 200
            else:
                self._action_buttons.append(Button(
                    (x, y, 210, 24), "Construir colonizadora",
                    lambda: self._build('colony'),
                    enabled=lambda: f.can_afford(DESIGNS['colony']['cost'])))
                x += 220
        elif p.faction is f:
            if p.terraform_level < p.max_terraform_level:
                self._action_buttons.append(Button(
                    (x, y, 150, 24), "Terraformar",
                    lambda: self._terraform(p),
                    enabled=lambda: f.can_terraform(p)))
                x += 160
            else:
                self._action_buttons.append(Button(
                    (x, y, 150, 24), "Max. terraform",
                    lambda: None, enabled=lambda: False))
                x += 160
        self._action_buttons.append(Button(
            (x, y, 150, 24), "Vista 3D  [V]",
            self._open_planet_viewer,
        ))

    def _open_planet_viewer(self):
        if self.selected_planet is not None:
            self.planet_viewer = PlanetViewer3D(self.texture_detail)

    # ---------- Render ----------
    def render(self):
        self._sync_events()
        if self.active_tab in self._scrollable_tabs:
            self._rebuild_panel_buttons()
        self._rebuild_action_buttons()

        self.screen.fill(C.BG)
        self._draw_grid()
        self._draw_influence_spheres()
        self._draw_colony_routes()
        self._draw_stars_and_planets()
        self._draw_ships()
        self._draw_topbar()
        self._draw_panel()
        self._draw_bottombar()
        self._draw_log()

        for b in self._top_buttons + self._action_buttons:
            b.draw(self.screen, self.f)
        for i, mode in enumerate(['all', 'mine', 'free']):
            self._filter_buttons[i].draw(
                self.screen, self.f, active=(mode == self.filter_mode))
        for i, t in enumerate(self.tabs):
            self._tab_buttons[i].draw(self.screen, self.f_tab,
                                      active=(t == self.active_tab))
        self._draw_panel_buttons()
        if self.planet_viewer is not None and self.selected_planet is not None:
            self.planet_viewer.draw(
                self.screen, self.selected_planet, self.f_title, self.f_small)
        if self.state.game_over:
            self._draw_victory()

    def _draw_victory(self):
        overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        overlay.fill((3, 8, 18, 190))
        self.screen.blit(overlay, (0, 0))
        winner = self.state.winner
        outcome = "VOCÊ VENCEU" if winner is self.faction else "FIM DE JOGO"
        title = self.f_title.render(outcome, True, C.ACCENT)
        detail = self.f.render(
            f"{winner.name} conquistou a vitória "
            f"{self.state.VICTORY_MODES[self.state.victory_mode]}.",
            True, C.TEXT)
        self.screen.blit(title, title.get_rect(
            center=(self.W // 2, self.H // 2 - 24)))
        self.screen.blit(detail, detail.get_rect(
            center=(self.W // 2, self.H // 2 + 8)))

    def _draw_panel_buttons(self):
        if self.active_tab not in self._scrollable_tabs:
            for button in self._panel_buttons:
                if isinstance(button, _FakeLabel):
                    button.draw(self.screen)
                else:
                    button.draw(self.screen, self.f,
                                active=getattr(button, '_active', False))
            if self._texture_slider is not None:
                self._texture_slider.draw(self.screen, self.f_small)
            return

        viewport = self._panel_viewport()
        old_clip = self.screen.get_clip()
        mouse_pos = pygame.mouse.get_pos()
        self.screen.set_clip(viewport)
        try:
            for button in self._panel_buttons:
                original_rect = button.rect
                button.rect = self._visible_panel_rect(button)
                try:
                    if hasattr(button, 'hover'):
                        button.hover = (
                            viewport.collidepoint(mouse_pos)
                            and button.rect.collidepoint(mouse_pos)
                        )
                        button.draw(
                            self.screen, self.f,
                            active=getattr(button, '_active', False),
                        )
                    else:
                        button.draw(self.screen)
                finally:
                    button.rect = original_rect
        finally:
            self.screen.set_clip(old_clip)

        if self._panel_content_height <= viewport.height:
            return
        track = pygame.Rect(self.W - 12, viewport.top, 4, viewport.height)
        pygame.draw.rect(self.screen, C.BUTTON, track, border_radius=2)
        thumb_height = min(
            viewport.height,
            max(28, int(viewport.height ** 2 / self._panel_content_height)),
        )
        max_scroll = self._panel_content_height - viewport.height
        thumb_offset = int(max(
            0, viewport.height - thumb_height)
            * self._panel_scroll[self.active_tab] / max_scroll)
        thumb = pygame.Rect(
            track.x, track.y + thumb_offset, track.width, thumb_height)
        pygame.draw.rect(self.screen, C.ACCENT, thumb, border_radius=2)

    def _hex_to_rgb(self, hex_str):
        h = hex_str.lstrip('#')
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))

    def _draw_influence_spheres(self):
        star_owner = {}
        for f in self.state.factions:
            for name in f.controlled_stars:
                star_owner[name] = f
        if not star_owner:
            return
        cache_key = (
            tuple(sorted((n, f.name) for n, f in star_owner.items())),
            round(self.zoom, 3), round(self.off_x, 1), round(self.off_y, 1),
            self.W, self.H)
        if getattr(self, '_influence_cache_key', None) == cache_key:
            self.screen.blit(self._influence_surface, (0, 0))
            return
        radius_world = 160
        radius_px = radius_world * self.zoom
        if radius_px < 3:
            empty = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            self._influence_cache_key = cache_key
            self._influence_surface = empty
            return
        points = []
        for star in self.state.stars:
            f = star_owner.get(star.name)
            if f is None:
                continue
            sx, sy = self.world_to_screen(*star.position)
            if (sx < -radius_px or sx > self.W + radius_px or
                    sy < -radius_px or sy > self.H + radius_px):
                continue
            points.append((sx, sy, self._hex_to_rgb(f.color)))
        if not points:
            empty = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
            self._influence_cache_key = cache_key
            self._influence_surface = empty
            return
        SCALE = 3
        gw = self.W // SCALE + 1
        gh = self.H // SCALE + 1
        gx, gy = np.meshgrid(np.arange(gw) * SCALE,
                             np.arange(gh) * SCALE, indexing='ij')
        owner_idx = np.full((gw, gh), -1, dtype=np.int16)
        dist_arr = np.full((gw, gh), np.inf, dtype=np.float32)
        for i, (sx, sy, _) in enumerate(points):
            d = np.sqrt((gx - sx) ** 2 + (gy - sy) ** 2).astype(np.float32)
            mask = (d < radius_px) & (d < dist_arr)
            owner_idx[mask] = i
            dist_arr[mask] = d[mask]
        rgba = np.zeros((gw, gh, 4), dtype=np.uint8)
        for i, (_, _, rgb) in enumerate(points):
            mask = owner_idx == i
            if not mask.any():
                continue
            rgba[mask, 0] = rgb[0]
            rgba[mask, 1] = rgb[1]
            rgba[mask, 2] = rgb[2]
            rgba[mask, 3] = 75
        raw = np.ascontiguousarray(rgba.transpose(1, 0, 2)).tobytes()
        surf_small = pygame.image.frombuffer(
            raw, (gw, gh), 'RGBA').convert_alpha()
        surf = pygame.transform.smoothscale(surf_small, (self.W, self.H))
        self._influence_surface = surf
        self._influence_cache_key = cache_key
        self.screen.blit(surf, (0, 0))

    def _draw_grid(self):
        step = 100
        x0 = int(self.off_x - self.W / 2 / self.zoom)
        y0 = int(self.off_y - self.H / 2 / self.zoom)
        for gx in range(x0 - x0 % step,
                        x0 + int(self.W / self.zoom) + step, step):
            for gy in range(y0 - y0 % step,
                            y0 + int(self.H / self.zoom) + step, step):
                sx, sy = self.world_to_screen(gx, gy)
                if 0 <= sx < self.W - self.PANEL_W and 0 <= sy < self.H:
                    pygame.draw.circle(self.screen, C.GRID, (sx, sy), 1)

    def _draw_stars_and_planets(self):
        for s in self.state.stars:
            sx, sy = self.world_to_screen(*s.position)
            r = max(2, int(s.radius * self.zoom))
            if sx < -r or sx > self.W + r or sy < -r or sy > self.H + r:
                continue
            if s is self.selected_star:
                for planet in s.planets:
                    orbit_radius = int(planet.distance_from_star * self.zoom)
                    if orbit_radius > r + 2:
                        pygame.draw.circle(
                            self.screen, C.GRID, (sx, sy), orbit_radius, 1)
            pygame.draw.circle(self.screen, C.STAR, (sx, sy), r)
            pygame.draw.circle(self.screen, C.STAR_BORDER, (sx, sy), r, 1)
            if s is self.selected_star:
                pygame.draw.circle(self.screen, C.SELECTED,
                                   (sx, sy), r + 4, 2)
            for p in s.planets:
                if not self._should_draw_planet(p):
                    continue
                px, py = self.world_to_screen(*p.abs_position)
                pr = max(1, int(p.radius * self.zoom))
                if -pr <= px <= self.W + pr and -pr <= py <= self.H + pr:
                    if pr >= 6 or (p.is_colonized and pr >= 4):
                        image = self._map_planet_surface(p, pr * 2)
                        self.screen.blit(image, (px - pr, py - pr))
                    else:
                        pygame.draw.circle(
                            self.screen, self._planet_color(p), (px, py), pr)
                    if not p.is_colonized and pr >= 3:
                        pygame.draw.circle(
                            self.screen, self._planet_color(p), (px, py),
                            pr, 1)
                    # Anel de cerco
                    if (p.is_colonized and p.max_defense > 0
                            and p.defense < p.max_defense - 0.5):
                        pulse = (math.sin(self.state.time * 5) + 1) / 2
                        ring_r = pr + 3 + int(pulse * 2)
                        pygame.draw.circle(self.screen, C.SIEGE,
                                           (px, py), ring_r, 1)
                    if p is self.selected_planet:
                        pygame.draw.circle(self.screen, C.SELECTED,
                                           (px, py), pr + 3, 1)

    def _draw_colony_routes(self):
        for faction in self.state.factions:
            if faction.eliminated:
                continue
            colonized_systems = {
                planet.parent_star.name for planet in faction.colonies.values()
                if planet.parent_star is not None
            }
            if len(colonized_systems) < 2:
                continue
            color = self._hex_to_rgb(faction.color)
            for first, second in self.state.map_G.edges:
                if (first not in colonized_systems
                        or second not in colonized_systems):
                    continue
                start = self.world_to_screen(
                    *self.state.stars_by_name[first].position)
                end = self.world_to_screen(
                    *self.state.stars_by_name[second].position)
                self._draw_dashed_line(start, end, color)

    def _draw_dashed_line(self, start, end, color):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length < 1:
            return
        dash_length, gap_length = 9, 6
        offset = 0.0
        while offset < length:
            dash_end = min(length, offset + dash_length)
            point_start = (
                round(start[0] + dx * offset / length),
                round(start[1] + dy * offset / length),
            )
            point_end = (
                round(start[0] + dx * dash_end / length),
                round(start[1] + dy * dash_end / length),
            )
            pygame.draw.line(self.screen, color, point_start, point_end, 1)
            offset += dash_length + gap_length

    def _draw_ships(self):
        for s in self.faction.ships.copy().values():
            if not s.alive:
                continue
            self._draw_ship_sprite(s, s is self.player.selected_ship)
        for f in self.state.factions:
            if f is self.faction or f.eliminated:
                continue
            for s in list(f.ships.values()):
                if not s.alive:
                    continue
                self._draw_ship_sprite(s, False)

    def _draw_ship_sprite(self, ship, selected):
        sx, sy = self.world_to_screen(*ship.abs_position)
        if not (0 <= sx < self.W and 0 <= sy < self.H):
            return
        design = DESIGNS.get(ship.design_key)
        if design is None or 'sprite' not in design:
            raise ValueError(
                f"Ship design '{ship.design_key}' has no sprite mapping")
        base_size = 18 if ship.design_key in ('scout', 'transport') else 22
        size = min(36, max(
            14, round(base_size * min(
                1.6, max(0.8, math.pow(self.zoom, 0.25))))))
        sprite = get_ship_sprite(
            design['sprite'], self._hex_to_rgb(ship.faction.color),
            (size, size),
        )
        self.screen.blit(sprite, sprite.get_rect(center=(sx, sy)))
        if selected:
            pygame.draw.circle(
                self.screen, C.SELECTED, (sx, sy), size // 2 + 3, 1)

    def _draw_topbar(self):
        pygame.draw.rect(self.screen, C.PANEL_BG, (0, 0, self.W, self.TOP_H))
        pygame.draw.line(self.screen, C.PANEL_BR,
                         (0, self.TOP_H), (self.W, self.TOP_H))

        title = self.f_title.render("TERRA PAX", True, C.TEXT)
        self.screen.blit(title, (10, 8))
        year_rect = pygame.Rect(128, 5, 132, 26)
        pygame.draw.rect(self.screen, (22, 47, 67), year_rect,
                         border_radius=5)
        pygame.draw.rect(self.screen, C.ACCENT, year_rect, 1,
                         border_radius=5)
        year_text = self.f_med.render(
            f"{self.state.month[:3].upper()} {self.state.year}",
            True, C.ACCENT)
        self.screen.blit(year_text, year_text.get_rect(center=year_rect.center))
        mode_rect = pygame.Rect(270, 5, 210, 26)
        mode_label = self.state.VICTORY_MODES[self.state.victory_mode]
        mode_text = self.f_small.render(
            f"VITÓRIA: {mode_label.upper()}", True, C.TEXT)
        self.screen.blit(mode_text, mode_text.get_rect(
            center=mode_rect.center))

        war_n = len(self.faction.war_declarations)
        ally_n = len(self.faction.allies)
        status = self.f_small.render(
            f"{self.faction.name}  |  frota {len(self.faction.ships)}  "
            f"guerras {war_n}  aliados {ally_n}  |  {self.state.speed:g}x",
            True, C.DIM,
        )
        status_right = self.W - self.PANEL_W - 20
        if status_right > 490:
            self.screen.set_clip(pygame.Rect(490, 0, status_right - 490,
                                             self.TOP_H))
            self.screen.blit(status, (490, 12))
            self.screen.set_clip(None)

    def _draw_panel(self):
        x0 = self.W - self.PANEL_W
        pygame.draw.rect(self.screen, C.PANEL_BG,
                         (x0, self.TOP_H, self.PANEL_W,
                          self.H - self.TOP_H))
        pygame.draw.line(self.screen, C.PANEL_BR,
                         (x0, self.TOP_H), (x0, self.H))
        pygame.draw.line(self.screen, C.PANEL_BR,
                         (x0 + 6, self.TOP_H + 36),
                         (self.W - 6, self.TOP_H + 36))
        y = self.TOP_H + 46
        f = self.faction

        if self.active_tab == 'resources':
            self.screen.blit(self.f_med.render("RECURSOS",
                                               True, C.ACCENT), (x0 + 10, y))
            y += 20
            for name, col in C.RES.items():
                val = f.resources.get(name, 0)
                pygame.draw.rect(self.screen, col, (x0 + 10, y, 10, 10))
                self.screen.blit(self.f.render(
                    f"{name:12s} {val:9.1f}", True, C.TEXT),
                    (x0 + 26, y - 1))
                y += 15
            y += 8
            self.screen.blit(self.f_med.render(
                f"COLÔNIAS ({len(f.colonies)})", True, C.ACCENT),
                (x0 + 10, y))
            y += 18
            for name in list(f.colonies)[:8]:
                self.screen.blit(self.f_small.render(
                    f"- {name}", True, C.TEXT), (x0 + 14, y))
                y += 12

        elif self.active_tab == 'system':
            if self.selected_star is None:
                self.screen.blit(self.f_med.render("SISTEMA",
                                                   True, C.ACCENT),
                                 (x0 + 10, y))
            else:
                s = self.selected_star
                free = sum(1 for p in s.planets if not p.is_colonized)
                mine = sum(1 for p in s.planets
                           if p.is_colonized and p.faction is f)
                other = len(s.planets) - free - mine
                self.screen.blit(self.f_med.render(
                    f"SISTEMA: {s.name}", True, C.STAR), (x0 + 10, y))
                y += 18
                self.screen.blit(self.f_small.render(
                    f"Livres {free}  Minhas {mine}  Outras {other}",
                    True, C.DIM), (x0 + 10, y))

        elif self.active_tab == 'research':
            rate = f.compute_research_rate()
            total_w = sum(f.research_weights.values()) or 1.0
            self.screen.blit(self.f_med.render(
                f"PESQUISA  {rate:5.1f}/ano", True, C.ACCENT),
                (x0 + 10, y))
            y += 20

            bar_w = total_w - 12
            for field in f.tech_tree:
                lvl = f.tech_tree[field]
                cost = f.get_research_cost(field)
                prog = f.research_progress[field]
                pct = min(1.0, prog / cost) if cost > 0 else 0.0
                share = f.research_weights[field] / total_w * 100.0

                # Linha 1: nome / nível / peso
                self.screen.blit(self.f_small.render(
                    f"{field:12s} Lv{lvl}/{TECH_CAPS[field]}  "
                    f"{share:5.1f}%",
                    True, C.TEXT), (x0 + 10, y))
                y += 16

                # Linha 2: barra
                pygame.draw.rect(self.screen, (30, 40, 60),
                                 (x0 + 10, y, bar_w, 6))
                fill_col = ((255, 230, 100) if pct > 0.9
                            else (110, 220, 180))
                if pct > 0:
                    pygame.draw.rect(self.screen, fill_col,
                                     (x0 + 10, y, int(bar_w * pct), 6))
                y += 8

                # Linha 3: números
                self.screen.blit(self.f_small.render(
                    f"  {prog:7.1f}/{cost:6.0f}  ({pct*100:5.1f}%)",
                    True, C.DIM), (x0 + 10, y))
                y += 16

        elif self.active_tab == 'fleet':
            self.screen.blit(self.f_med.render(
                f"FROTA ({len(f.ships)})", True, C.ACCENT), (x0 + 10, y))
            self.screen.blit(self.f_small.render(
                f"Ativas: {sum(1 for ship in f.ships.copy().values() if ship.alive)}"
                f"  ·  Colonizadores ociosos: "
                f"{len(f.idle_colony_ships())}",
                True, C.DIM), (x0 + 10, y + 20))

        elif self.active_tab == 'colonies':
            population = sum(
                planet.population for planet in f.colonies.values())
            self.screen.blit(self.f_med.render(
                f"COLÔNIAS ({len(f.colonies)})", True, C.ACCENT),
                (x0 + 10, y))
            self.screen.blit(self.f_small.render(
                f"População total: {population:.0f}",
                True, C.DIM), (x0 + 10, y + 20))

        elif self.active_tab == 'build':
            self.screen.blit(self.f_med.render("CONSTRUIR",
                                               True, C.ACCENT), (x0 + 10, y))

        
        elif self.active_tab == 'war':
            self.screen.blit(self.f_med.render("DIPLOMACIA",
                                               True, C.ACCENT),
                             (x0 + 10, y))
            y += 18
            desc = getattr(f, 'description', '')
            if desc:
                self.screen.blit(self.f_small.render(desc, True, C.DIM),
                                 (x0 + 10, y))
                y += 14
            advantage = FACTION_TRAITS[f.advantage][0]
            disadvantage = FACTION_TRAITS[f.disadvantage][0]
            self.screen.blit(self.f_small.render(
                f"Vantagem: {advantage}  ·  Desvantagem: {disadvantage}",
                True, C.DIM), (x0 + 10, y))
            y += 14
            self.screen.blit(self.f_small.render(
                f"Guerras: {len(f.war_declarations)}   "
                f"Aliados: {len(f.allies)}   "
                f"Comércio: {sum('trade' in p for p in f.treaties.values())}",
                True, C.DIM), (x0 + 10, y))

        elif self.active_tab == 'visual':
            self.screen.blit(self.f_med.render(
                "DETALHE DAS TEXTURAS", True, C.ACCENT),
                (x0 + 10, y))
            y += 22
            self.screen.blit(self.f_small.render(
                "Escolha de 1 (leve) a 8 (mais detalhado).",
                True, C.DIM), (x0 + 10, y))

    def _draw_bottombar(self):
        y0 = self.H - self.BOT_H
        pygame.draw.rect(self.screen, C.PANEL_BG,
                        (0, y0, self.W - self.PANEL_W, self.BOT_H))
        pygame.draw.line(self.screen, C.PANEL_BR,
                        (0, y0), (self.W - self.PANEL_W, y0))

        if not self.selected_star:
            self.screen.blit(self.f.render(
                "Clique em estrela/planeta — aba Sistema/Guerra controla tudo",
                True, C.DIM), (12, y0 + 12))
            return

        s = self.selected_star
        self.screen.blit(self.f_med.render(f"* {s.name}", True, C.STAR),
                        (10, y0 + 4))
        colonized = sum(1 for p in s.planets if p.is_colonized)
        self.screen.blit(self.f.render(
            f"Planetas: {len(s.planets)}  |  Colonizados: {colonized}",
            True, C.TEXT), (10, y0 + 24))

        if not self.selected_planet:
            return

        p = self.selected_planet
        suit = p.get_suitability(self.faction)
        tf = (f"  tf {p.terraform_level}/{p.max_terraform_level}"
            if p.is_colonized else "")
        self.screen.blit(self.f.render(
            f"  -> {p.name}  raio {p.radius:.3f}  suit={suit:.2f}{tf}",
            True, C.TEXT), (10, y0 + 40))

        hs = p.life_suitability
        detail = (f"  Human={hs.get('Human', 0):.2f}  "
                  f"Alien={hs.get('Alien', 0):.2f}  "
                  f"Hybrid={hs.get('Hybrid', 0):.2f}  "
                  f"Robot={hs.get('Robot', 0):.2f}")
        self.screen.blit(self.f_small.render(detail, True, C.DIM),
                        (10, y0 + 56))

        if p.is_colonized and p.faction:
            try:
                caps = p.capacity_info()
                pop_max = caps['max_pop']
                dev_max = caps['max_dev']
            except Exception:
                pop_max, dev_max = 2000, 2.0
            self.screen.blit(self.f_small.render(
                f"  Pop {p.population:.0f}/{pop_max:.0f}  "
                f"dev {p.developement:.2f}/{dev_max:.2f}  "
                f"prod {p.production:.2f}",
                True, C.DIM), (10, y0 + 70))

            if p.max_defense > 0:
                pct = max(0.0, p.defense / p.max_defense)
                bar_x, bar_y = 10, y0 + 86
                bar_w, bar_h = 260, 6
                pygame.draw.rect(self.screen, (40, 40, 60),
                                (bar_x, bar_y, bar_w, bar_h))
                col = ((110, 220, 160) if pct > 0.6
                    else (230, 200, 80) if pct > 0.3
                    else C.SIEGE)
                pygame.draw.rect(self.screen, col,
                                (bar_x, bar_y, int(bar_w * pct), bar_h))
                txt = f"DEF {p.defense:.0f}/{p.max_defense:.0f}"
                self.screen.blit(self.f_small.render(
                    txt, True, C.DIM), (bar_x + bar_w + 8, bar_y - 3))

        preview_size = 82
        map_width = self.W - self.PANEL_W
        preview_x = map_width - preview_size - 14
        if preview_x > 320:
            preview_y = y0 + (self.BOT_H - preview_size) // 2
            card = pygame.Rect(
                preview_x - 7, preview_y - 7,
                preview_size + 14, preview_size + 27)
            pygame.draw.rect(self.screen, (19, 34, 53), card,
                             border_radius=8)
            pygame.draw.rect(self.screen, C.PANEL_BR, card, 1,
                             border_radius=8)
            self.screen.blit(
                self._planet_surface(p, preview_size),
                (preview_x, preview_y),
            )
            category = dominant_suitability(p.life_suitability)
            category_label = self.f_small.render(
                category.upper(), True, C.ACCENT)
            self.screen.blit(
                category_label,
                category_label.get_rect(
                    centerx=preview_x + preview_size // 2,
                    top=preview_y + preview_size + 4,
                ),
            )

    def _planet_surface(self, planet, size):
        suitability = tuple(sorted(planet.life_suitability.items()))
        capacity = planet.capacity_info()
        lights = round(city_light_intensity(
            planet.developement, planet.population,
            capacity['max_dev'], capacity['max_pop'],), 2)
        key = (id(planet), suitability, size, lights, self.texture_detail)
        if key not in self._planet_surfaces:
            star_name = (planet.parent_star.name
                         if planet.parent_star is not None else '')
            seed = f"{star_name}:{planet.name}"
            self._planet_surfaces[key] = generate_planet_surface(
                planet.life_suitability, seed, size, city_lights=lights,
                detail_level=self.texture_detail)
        return self._planet_surfaces[key]

    def _map_planet_surface(self, planet, size):
        suitability = tuple(sorted(planet.life_suitability.items()))
        capacity = planet.capacity_info()
        lights = round(city_light_intensity(
            planet.developement, planet.population,
            capacity['max_dev'], capacity['max_pop'],), 2)
        key = (id(planet), suitability, size, lights, self.texture_detail)
        if key not in self._map_planet_surfaces:
            render_size = min(512, max(64, 1 << (size - 1).bit_length()))
            surface = self._planet_surface(planet, render_size)
            self._map_planet_surfaces[key] = (
                surface if surface.get_size() == (size, size)
                else pygame.transform.smoothscale(surface, (size, size)))
        return self._map_planet_surfaces[key]

    def _draw_log(self):
        if not self.log:
            return
        x = 10
        line_h = 14
        y = self.H - self.BOT_H - len(self.log) * line_h - 6
        for msg in self.log:
            surf = self.f_small.render(msg, True, C.DIM)
            bg = pygame.Surface((surf.get_width() + 8, line_h - 1),
                                pygame.SRCALPHA)
            bg.fill((0, 0, 0, 150))
            self.screen.blit(bg, (x - 4, y))
            self.screen.blit(surf, (x, y + 1))
            y += line_h

    def _adjust_weight(self, field, delta):
        f = self.faction
        new_w = f.research_weights.get(field, 1.0) + delta
        f.set_research_weight(field, new_w)

    def _reset_research_weights(self):
        self.player.reset_research_weights()
        self.log_msg("Pesos de pesquisa resetados (1x cada)")