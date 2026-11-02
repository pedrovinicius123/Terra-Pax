import math
import random
import time

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
from graphics.star import (
    COLONY_FOCUSES,
    FOCUS_LABELS,
    HABITAT_MAX_PER_PLANET,
    format_population,
    planet_label_for,
)
from logistics.game_3d import PLANET_TYPE_LABELS, PlanetViewer3D, planet_type_of


ORDER_LABELS = {
    'move': 'em rota',
    'hold': 'paradas',
    'clear': 'retomando operações automáticas',
}


def outcome_label(kind):
    return ORDER_LABELS.get(kind, kind)


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
    PLANET_ASTEROID  = (160, 150, 138)
    PLANET_GIANT     = (216, 182, 132)
    BELT_SPECK       = (118, 110, 98)
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
        lines = str(self.text).split("\n")
        line_height = self.font.get_height() + 1
        for offset, line in enumerate(lines):
            screen.blit(self.font.render(line, True, self.color),
                        (self.rect.x, self.rect.y + offset * line_height))


class _FakeBar:
    """Barra de progresso rolável junto dos rótulos do painel."""

    def __init__(self, rect, fraction, color, font=None, text='',
                 track=(30, 40, 60)):
        self.rect = pygame.Rect(rect)
        self.fraction = fraction
        self.color = color
        self.font = font
        self.text = text
        self.track = track

    def draw(self, screen):
        pygame.draw.rect(screen, self.track, self.rect, border_radius=3)
        ratio = min(1.0, max(0.0, self.fraction))
        if ratio > 0.0:
            fill = pygame.Rect(self.rect.x, self.rect.y,
                               max(2, int(self.rect.width * ratio)),
                               self.rect.height)
            pygame.draw.rect(screen, self.color, fill, border_radius=3)
        if self.text and self.font is not None:
            surf = self.font.render(self.text, True, C.TEXT)
            screen.blit(surf, surf.get_rect(center=self.rect.center))


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
    SHIP_HEADING_STEPS = 24
    GRID_BASE_STEP = 100
    GRID_MIN_PX = 24

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
        self.selected_ships = []
        self._marquee = None
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
        self._planet_placeholders = {}
        self._planet_pending = {}
        self._camera_key = None
        self._camera_still = 0
        self._belt_speck_cache = {}
        self._ship_sprite_cache = {}
        self._ship_base_cache = {}
        self.planet_viewer = None
        self._last_event_idx = 0
        self._top_buttons = []
        self._filter_buttons = []
        self._tab_buttons = []
        self._panel_buttons = []
        self._texture_slider = None
        self._action_buttons = []
        self._planner_actions = []

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

    def _topbar_status_clip_rect(self):
        status_right = min(
            self.W - self.PANEL_W - 20,
            self._filter_buttons[0].rect.left - 10,
        )
        return pygame.Rect(490, 0, max(0, status_right - 490), self.TOP_H)

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
        self._planet_pending.clear()
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

    def _select_ship(self, ship, center=True):
        self._set_ship_selection([ship])
        if center:
            self.off_x, self.off_y = ship.abs_position
        self.log_msg(f"Selecionada {ship.ship_id}")

    # ---------- seleção de naves ----------
    def _own_ships(self):
        return [ship for ship in list(self.faction.ships.values())
                if ship.alive]

    def _set_ship_selection(self, ships):
        self.selected_ships = [ship for ship in ships if ship.alive]
        self.player.selected_ship = (self.selected_ships[-1]
                                     if self.selected_ships else None)
        self._rebuild_action_buttons()

    def _toggle_ship_selection(self, ship):
        if ship in self.selected_ships:
            self._set_ship_selection(
                [item for item in self.selected_ships if item is not ship])
        else:
            self._set_ship_selection(self.selected_ships + [ship])

    def _ship_at(self, pos, radius=18):
        wx, wy = self.screen_to_world(*pos)
        limit = radius / max(1e-6, self.zoom)
        best, best_dist = None, limit
        for ship in self._own_ships():
            distance = math.dist((wx, wy), ship.abs_position)
            if distance < best_dist:
                best, best_dist = ship, distance
        return best

    def _ships_in_rect(self, rect):
        return [ship for ship in self._own_ships()
                if rect.collidepoint(self.world_to_screen(*ship.abs_position))]

    # ---------- ordens ----------
    def _order_ships(self, kind, star=None):
        if not self.selected_ships:
            self.log_msg("Selecione naves primeiro")
            return 0
        issued = sum(1 for ship in self.selected_ships
                     if ship.issue_order(kind, star=star))
        detail = f" {star.name}" if kind == 'move' and star else ""
        self.log_msg(f"{issued} nave(s){detail} "
                     f"{outcome_label(kind)}")
        self._rebuild_action_buttons()
        return issued

    def _fleet_order(self, fleet_id, kind):
        issued = self.faction.fleet_manager.order(
            fleet_id, kind, star=self.selected_star)
        if issued:
            self.log_msg(f"{issued} nave(s) da frota {outcome_label(kind)}")
        self._rebuild_panel_buttons()

    def _auto_group_fleets(self):
        created = self.faction.fleet_manager.auto_group()
        self.log_msg(f"{created} frota(s) agrupadas por estrela")
        self._rebuild_panel_buttons()

    def _fleet_from_selection(self):
        manager = self.faction.fleet_manager
        fleet = manager.create(self.selected_ships)
        if fleet is None:
            self.log_msg("Selecione naves para formar uma frota")
        else:
            self.log_msg(f"{fleet.name}: {len(fleet.ships)} naves")
        self._rebuild_panel_buttons()

    def _select_fleet(self, fleet_id):
        fleet = self.faction.fleet_manager.fleets.get(fleet_id)
        if fleet is None:
            return
        self._set_ship_selection(fleet.ships)
        star = fleet.location()
        if star is not None:
            self.off_x, self.off_y = star.position
        self.log_msg(f"{fleet.name} selecionada")
        self._rebuild_panel_buttons()

    def _disband_fleet(self, fleet_id):
        fleet = self.faction.fleet_manager.fleets.get(fleet_id)
        if self.faction.fleet_manager.disband(fleet_id) and fleet:
            self.log_msg(f"{fleet.name} dissolvida")
        self._rebuild_panel_buttons()

    def _draw_fleet_manager(self, f, x0, w, y):
        """Seção de frotas: resumo, seleção e ordens conjuntas."""
        manager = f.fleet_manager
        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 18),
            f"FROTAS  ·  {len(manager.fleets)}",
            self.f_small, color=C.ACCENT))
        y += 20
        half = (w - 16) // 2
        self._panel_buttons.append(Button(
            (x0 + 4, y, half, 24), "Agrupar por estrela",
            self._auto_group_fleets))
        self._panel_buttons.append(Button(
            (x0 + 10 + half, y, half, 24),
            f"Frota da seleção ({len(self.selected_ships)})",
            self._fleet_from_selection,
            enabled=lambda: bool(self.selected_ships)))
        y += 30

        fleets = list(manager.fleets.values())
        if not fleets:
            self._panel_buttons.append(_FakeLabel(
                (x0 + 8, y, w - 8, 18),
                "Nenhuma frota — agrupe ou crie a partir da seleção.",
                self.f_small))
            y += 22
            return y

        for fleet in fleets:
            info = fleet.summary()
            members = fleet.ships
            highlighted = bool(self.selected_ships) and all(
                ship in self.selected_ships for ship in members)
            button = Button(
                (x0 + 4, y, w - 12, 24),
                f"{info['name']}  ·  {info['ships']} naves  ·  "
                f"{info['status']}",
                lambda fleet_id=fleet.fleet_id: self._select_fleet(fleet_id),
            )
            button._active = highlighted
            self._panel_buttons.append(button)
            y += 25
            self._panel_buttons.append(_FakeLabel(
                (x0 + 10, y, w - 18, 16),
                f"casco {info['hull']:.0f}  ·  fogo "
                f"{info['firepower']:.0f}  ·  vel {info['speed']:.1f}",
                self.f_small))
            y += 18
            gap = 4
            small = (w - 12 - 3 * gap) // 4
            actions = (("Mover *", 'move'), ("Parar", 'hold'),
                       ("Auto", 'clear'))
            for index, (label, kind) in enumerate(actions):
                rect = (x0 + 4 + index * (small + gap), y, small, 22)
                usable = kind != 'move' or self.selected_star is not None
                self._panel_buttons.append(Button(
                    rect, label,
                    lambda fleet_id=fleet.fleet_id, order=kind:
                    self._fleet_order(fleet_id, order),
                    enabled=lambda available=usable: available,
                ))
            self._panel_buttons.append(Button(
                (x0 + 4 + 3 * (small + gap), y, small, 22), "Dissolver",
                lambda fleet_id=fleet.fleet_id: self._disband_fleet(fleet_id)))
            y += 28
        return y

    @staticmethod
    def _compact(value):
        value = float(value)
        for limit, suffix in ((1e9, 'G'), (1e6, 'M'), (1e3, 'k')):
            if abs(value) >= limit:
                return f"{value / limit:.1f}{suffix}"
        return f"{value:.0f}"

    @staticmethod
    def _years_label(years):
        if years is None or not math.isfinite(years):
            return "sem progresso"
        if years >= 1000.0:
            return f"{years:,.0f} anos".replace(',', '.')
        return f"{years:.1f} anos"

    @staticmethod
    def _focus_label(planet):
        return FOCUS_LABELS.get(getattr(planet, 'focus', 'balanced'), '—')

    @staticmethod
    def _years_short(years):
        if years is None or not math.isfinite(years):
            return '—'
        if years >= 1000.0:
            return f"{years / 1000.0:.1f} mil a"
        return f"{years:.0f} a"

    @staticmethod
    def _stage_label(stage):
        if stage >= 0.95:
            return 'Gaia'
        if stage >= 0.80:
            return 'mundo vivo'
        if stage >= 0.60:
            return 'biosfera jovem'
        if stage >= 0.40:
            return 'em transformação'
        if stage >= 0.28:
            return 'quase estéril'
        return 'rocha estéril'

    def _set_colony_focus(self, planet, focus):
        if not planet.set_focus(focus):
            return
        self.log_msg(f"{planet.name}: foco {FOCUS_LABELS[focus].lower()}")
        self._rebuild_panel_buttons()

    def _cancel_colony_task(self, planet, task):
        if planet.cancel_queued(task):
            self.log_msg(f"{planet.name}: obra cancelada "
                         f"({task.get('label', 'obra')})")
        self._rebuild_panel_buttons()

    def _draw_colony_manager(self, f, planet, x0, w, y):
        """Gestão detalhada: terraformação, capacidade, foco, obras e recursos."""
        info = planet.expansion_info()
        growth = planet.growth_projection()
        stage = planet.terraforming_stage()
        outputs = planet.resource_output()
        world = planet_label_for(getattr(planet, 'planet_type',
                                         'terrestrial'))

        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 18), f"GESTÃO  ·  {planet.name}", self.f_small,
            color=C.ACCENT))
        y += 20
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 16),
            f"{world} · {planet.parent_star.name} · {planet.name}",
            self.f_small))
        y += 14
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 16),
            f"{self._stage_label(stage)} · exp {info['level']}/{info['max']}"
            f" · hab {planet.habitats}/{HABITAT_MAX_PER_PLANET}",
            self.f_small))
        y += 18
        self._panel_buttons.append(_FakeBar(
            (x0 + 4, y, w - 8, 12), stage, C.PLANET_MINE, self.f_small,
            f"retrato do mundo {stage * 100:.0f}% (estéril → Gaia)"))
        y += 16
        remaining = ('concluído' if info['level'] >= info['max']
                     else self._years_short(info['eta_years']))
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 16),
            f"expansão {info['percent'] * 100:.0f}% · "
            f"{info['rate']:.2f} anos-terra/ano · próx. nível: {remaining}",
            self.f_small))
        y += 18

        half = (w - 12) // 2
        self._panel_buttons.append(_FakeBar(
            (x0 + 4, y, half, 12),
            planet.population / max(1e-6, growth['max_pop']), C.SELECTED,
            self.f_small,
            f"pop {format_population(planet.population)}/"
            f"{format_population(growth['max_pop'])}"))
        self._panel_buttons.append(_FakeBar(
            (x0 + 12 + half, y, half, 12),
            planet.developement / max(1e-6, growth['max_dev']), C.STAR,
            self.f_small,
            f"desenv {planet.developement:.1f}/{growth['max_dev']:.0f}"))
        y += 16

        food = growth['food_balance']
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 16),
            f"alimento {food:+.0f}/ano · fome "
            f"{getattr(planet, 'famine', 0.0) * 100:.0f}% · crescimento "
            f"{growth['pop_growth_rate'] * 100:.2f}%/ano",
            self.f_small,
            color=C.PLANET_FREE_GOOD if food >= 0 else C.PLANET_ENEMY))
        y += 18
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 16),
            f"defesa {planet.defense:.0f}/{planet.max_defense:.0f} · "
            f"estaleiro {'sim' if planet.can_build_ships else 'não'}",
            self.f_small))
        y += 20

        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 16),
            f"PRODUÇÃO  ·  {self._compact(planet.annual_output())} un/ano",
            self.f_small, color=C.ACCENT))
        y += 18
        shown = [name for name in C.RES if name != 'Research']
        column = (w - 8) // 2
        for index, name in enumerate(shown):
            row, side = divmod(index, 2)
            stock = planet.planet_resources.get(name, 0.0)
            cap = planet.storage_capacity.get(name, float('inf'))
            rate = outputs.get(name, 0.0)
            cap_text = (self._compact(cap) if math.isfinite(cap) else '∞')
            self._panel_buttons.append(_FakeLabel(
                (x0 + 4 + side * column, y + row * 14, column - 6, 14),
                f"{name[:8]:<8s}{self._compact(stock):>6s}/{cap_text:<5s}"
                f"+{self._compact(rate)}",
                self.f_small, color=C.RES[name]))
        y += 14 * ((len(shown) + 1) // 2) + 8

        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 16), f"FOCO  ·  {self._focus_label(planet)}",
            self.f_small, color=C.ACCENT))
        y += 18
        gap = 4
        small = (w - 8 - 4 * gap) // 5
        short = {'balanced': 'Equil', 'industry': 'Indús',
                 'growth': 'Cresc', 'defense': 'Defes', 'science': 'Ciênc'}
        for index, focus in enumerate(COLONY_FOCUSES):
            button = Button(
                (x0 + 4 + index * (small + gap), y, small, 22),
                short[focus],
                lambda selected=planet, chosen=focus: self._set_colony_focus(
                    selected, chosen),
                tooltip=FOCUS_LABELS[focus])
            button._active = planet.focus == focus
            self._panel_buttons.append(button)
        y += 26
        effects = planet.focus_effects()
        names = {'development': 'desenv', 'population': 'pop',
                 'output': 'prod', 'research': 'pesq', 'defense': 'defesa'}
        summary = ('  '.join(f"{names.get(k, k)} x{v:.2f}"
                             for k, v in sorted(effects.items()))
                   if effects else 'sem modificadores')
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 14), f"efeitos: {summary}", self.f_small))
        y += 20

        active = planet.building_progress()
        queue = planet.queued_tasks()
        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 16),
            f"OBRAS  ·  {len(queue)} na fila", self.f_small, color=C.ACCENT))
        y += 18
        if active:
            self._panel_buttons.append(_FakeBar(
                (x0 + 4, y, w - 8, 12), active['percent'], C.STAR,
                self.f_small,
                f"{active['label'][:30]} · "
                f"{self._years_label(active['years_left'])}"))
            y += 16
        for task in queue[:6]:
            row = (x0 + 4, y, w - 34, 14)
            self._panel_buttons.append(_FakeLabel(
                row, f"fila: {str(task.get('label', 'obra'))[:34]}",
                self.f_small))
            self._panel_buttons.append(Button(
                (x0 + w - 26, y - 4, 22, 20), "x",
                lambda selected=planet, item=task: self._cancel_colony_task(
                    selected, item)))
            y += 22
        habitat_button = Button(
            (x0 + 4, y, w - 8, 24),
            ("Habitat orbital — máximo atingido"
             if planet.habitats >= HABITAT_MAX_PER_PLANET else
             ("Habitat em construção…" if planet.habitat_building else
              "Construir habitat orbital")),
            lambda selected=planet: self._build_habitat(selected),
            enabled=lambda selected=planet: f.can_build_habitat(selected))
        self._panel_buttons.append(habitat_button)
        y += 30
        return y

    def _colony_recommendations(self, f):
        """Diagnóstico agrupado do império: (gravidade, texto, ação, rótulo)."""
        groups = {}

        def add(severity, kind, text, planet, action, label):
            entry = groups.setdefault((severity, kind), {
                'text': text, 'planets': [], 'action': action, 'label': label})
            entry['planets'].append(planet)

        for planet in f.colonies.values():
            growth = planet.growth_projection()
            info = planet.expansion_info()
            pressure = planet.population / max(1e-6, growth['max_pop'])
            food = growth['food_balance']

            if food < 0.0 and planet.focus != 'industry':
                add(0, 'food_focus',
                    f"falta alimento ({food:.1f}/ano) — foco Indústria "
                    f"eleva a produção", planet, 'focus_industry', 'foco')
            elif food < 0.0:
                add(0, 'food_ships',
                    f"fome ({food:.1f}/ano) — envie transportes de alimento",
                    planet, 'select', 'ver')
            if getattr(planet, 'famine', 0.0) > 0.05:
                add(0, 'famine',
                    f"fome de {planet.famine * 100:.0f}% — crescimento "
                    f"travado", planet, 'select', 'ver')
            if (pressure >= 0.9 and planet.habitats < HABITAT_MAX_PER_PLANET
                    and not planet.habitat_building):
                add(1, 'habitat',
                    f"população a {pressure * 100:.0f}% do teto — habitat "
                    f"orbital libera capacidade", planet, 'habitat', 'habitat')
            if (pressure >= 0.9 and planet.habitats >= HABITAT_MAX_PER_PLANET
                    and info['level'] < info['max']):
                add(2, 'waiting_level',
                    f"sem espaço e o nível {info['level']} ainda cresce "
                    f"({self._years_label(info['eta_years'])})",
                    planet, 'select', 'ver')
            if info['eta_years'] > 400.0 and planet.focus != 'industry':
                add(3, 'slow_terraform',
                    f"terraformação lenta "
                    f"({self._years_label(info['eta_years'])}) — foco "
                    f"Indústria acelera o desenvolvimento",
                    planet, 'focus_industry', 'foco')
            if (planet.capacity_info()['dev_capped']
                    and info['level'] < info['max']):
                add(4, 'dev_capped',
                    "desenvolvimento no teto — só a expansão de nível abre "
                    "espaço", planet, None, None)

        handlers = {
            'focus_industry': lambda planet: self._set_colony_focus(
                planet, 'industry'),
            'habitat': lambda planet: self._build_habitat(planet),
            'select': lambda planet: self._select_colony(planet),
        }
        recommendations = []
        for (severity, kind), entry in groups.items():
            worlds = entry['planets']
            text = entry['text']
            if len(worlds) == 1:
                title = f"{worlds[0].name}: {text}"
            else:
                names = ", ".join(planet.name for planet in worlds[:2])
                more = f" +{len(worlds) - 2}" if len(worlds) > 2 else ""
                title = f"{len(worlds)} colônias ({names}{more}): {text}"
            handler = handlers.get(entry['action'])
            recommendations.append((
                severity, title,
                (lambda selected=worlds, run=handler:
                 [run(planet) for planet in selected])
                if handler is not None else None,
                entry['label']))

        recommendations.sort(key=lambda item: (item[0], item[1]))
        return recommendations[:8]

    def _apply_all_recommendations(self):
        actions = [action for _, _, action, _ in self._planner_actions
                   if action is not None]
        if not actions:
            self.log_msg("Nada a aplicar no plano")
            return
        for action in actions:
            action()
        self.log_msg(f"Plano aplicado: {len(actions)} medidas")
        self._rebuild_panel_buttons()

    def _draw_colony_planner(self, f, x0, w, y):
        """Planejador do império: projeções agregadas e medidas sugeridas."""
        colonies = list(f.colonies.values())
        total_pop = sum(p.population for p in colonies)
        total_capacity = sum(p.growth_projection()['max_pop']
                             for p in colonies)
        average_stage = (sum(p.terraforming_stage() for p in colonies)
                         / len(colonies)) if colonies else 0.0
        food_surplus = sum(p.food_balance() for p in colonies)
        queued = sum(len(p.queued_tasks()) for p in colonies)
        building = sum(1 for p in colonies if p.building_progress())

        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 18), "PLANO IMPERIAL", self.f_small, color=C.ACCENT))
        y += 20
        self._panel_buttons.append(_FakeBar(
            (x0 + 4, y, w - 8, 12),
            total_pop / max(1e-6, total_capacity), C.SELECTED, self.f_small,
            f"população {format_population(total_pop)} / "
            f"{format_population(total_capacity)}"))
        y += 16
        self._panel_buttons.append(_FakeBar(
            (x0 + 4, y, w - 8, 12), average_stage, C.PLANET_MINE, self.f_small,
            f"terraformação média {average_stage * 100:.0f}% (estéril → Gaia)"))
        y += 18
        self._panel_buttons.append(_FakeLabel(
            (x0 + 4, y, w, 16),
            f"alimento líquido {food_surplus:+.0f}/ano · obras {building} · "
            f"fila {queued}",
            self.f_small,
            color=C.PLANET_FREE_GOOD if food_surplus >= 0 else C.PLANET_ENEMY))
        y += 20

        recommendations = self._colony_recommendations(f)
        self._planner_actions = recommendations
        self._panel_buttons.append(_FakeLabel(
            (x0, y, w, 16), f"RECOMENDAÇÕES  ·  {len(recommendations)}",
            self.f_small, color=C.ACCENT))
        y += 18
        if not recommendations:
            self._panel_buttons.append(_FakeLabel(
                (x0 + 6, y, w - 6, 16),
                "Império equilibrado — nenhuma medida pendente.", self.f_small))
            y += 20
        else:
            for _, text, action, label in recommendations:
                lines = self._wrap_label(text, 44)
                height = 13 * len(lines)
                self._panel_buttons.append(_FakeLabel(
                    (x0 + 6, y, w - 74, height),
                    "\n".join(lines), self.f_small))
                if action is not None:
                    self._panel_buttons.append(Button(
                        (x0 + w - 66, y, 62, 20), label, action))
                y += max(22, height + 6)
            self._panel_buttons.append(Button(
                (x0 + 4, y, w - 8, 24), "Aplicar todas as medidas",
                self._apply_all_recommendations,
                enabled=lambda: any(
                    action is not None
                    for _, _, action, _ in self._planner_actions)))
            y += 30
        return y

    @staticmethod
    def _wrap_label(text, width):
        words = str(text).split()
        lines, current = [], ''
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > width and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines or ['']

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

    def _build_habitat(self, planet):
        if self.player.build_habitat(planet):
            self.log_msg(f"Habitat orbital em construção: {planet.name}")
            self._rebuild_panel_buttons()
        else:
            self.log_msg("Habitat indisponível ou recursos insuficientes")

    def _toggle_auto_colonize(self):
        on = self.player.toggle_auto_colonize()
        self.log_msg(f"Auto-colonizar: {'ON' if on else 'OFF'}")
        self._rebuild_panel_buttons()

    def _toggle_auto_habitat(self):
        on = self.player.toggle_auto_habitat()
        self.log_msg(f"Auto-habitat: {'ON' if on else 'OFF'}")
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
            from graphics.star import HABITAT_MAX_PER_PLANET
            if p.habitat_building:
                return ("habitat…", lambda: None, lambda: False)
            if p.habitats < HABITAT_MAX_PER_PLANET:
                return ("Habitat",
                        lambda pp=p: self._build_habitat(pp),
                        lambda pp=p: f.can_build_habitat(pp))
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
            y = self._draw_fleet_manager(f, x0, w, y)
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
            x0 = viewport.left
            w = viewport.width - 2
            y = viewport.top + 8
            colonies = sorted(f.colonies.values(), key=lambda p: p.name)
            home = f.home_planet
            selected = self.selected_planet
            if (selected is not None and selected.is_colonized
                    and selected.faction is f):
                y = self._draw_colony_manager(f, selected, x0, w, y)
            y = self._draw_colony_planner(f, x0, w, y)
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
                    button = Button(
                        (x0 + 4, y, w - 12, 24), planet.name,
                        lambda selected=planet: self._select_colony(selected),
                    )
                    button._active = planet is self.selected_planet
                    self._panel_buttons.append(button)
                    y += 25
                    info = planet.expansion_info()
                    stage = planet.terraforming_stage()
                    self._panel_buttons.append(_FakeLabel(
                        (x0 + 10, y, w - 18, 16),
                        f"{planet.parent_star.name}  ·  pop "
                        f"{format_population(planet.population)}  ·  "
                        f"desenv. {planet.developement:.1f}",
                        self.f_small))
                    y += 14
                    self._panel_buttons.append(_FakeLabel(
                        (x0 + 10, y, w - 18, 16),
                        f"{self._stage_label(stage)} {stage * 100:.0f}%  ·  "
                        f"exp {info['level']}/{info['max']}  ·  "
                        f"hab {planet.habitats}  ·  "
                        f"foco {self._focus_label(planet)[:6]}",
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
                        text = f"{p.name[-1]} MINHA exp{p.terraform_level} hab{getattr(p, 'habitats', 0)}"
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
            ah_label = f"Auto-habitat: {'ON' if f.auto_habitat else 'OFF'}"
            self._panel_buttons.append(Button(
                (x0, y, bw, 24), ac_label, self._toggle_auto_colonize))
            self._panel_buttons.append(Button(
                (x0 + bw + 4, y, bw, 24), ah_label,
                self._toggle_auto_habitat))
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
        planet_type = planet_type_of(p)
        if planet_type == 'asteroid':
            return C.PLANET_ASTEROID
        if planet_type == 'gas_giant':
            return C.PLANET_GIANT
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
            if self._marquee is not None:
                self._marquee[1] = (mx, my)

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
                    self._handle_map_click(
                        event.pos,
                        additive=bool(
                            pygame.key.get_mods() & pygame.KMOD_SHIFT))
                    self.dragging = True
                    self.last_mouse = event.pos
            elif event.button == 3:
                if (event.pos[0] < self.W - self.PANEL_W
                        and event.pos[1] > self.TOP_H):
                    self._handle_map_right_click(event.pos)
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

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 3:
            self._finish_marquee(
                additive=bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                self._toggle_pause()
            elif event.key == pygame.K_r:
                self.zoom = self.DEFAULT_ZOOM
                self._center_map_on_galaxy()
                self._map_planet_surfaces.clear()
                self._planet_placeholders.clear()
            elif event.key == pygame.K_v:
                self._open_planet_viewer()

    def _zoom_at(self, pos, direction):
        if direction == 0:
            return
        wx, wy = self.screen_to_world(*pos)
        self.zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM,
                         self.zoom * (1.2 if direction > 0 else 1 / 1.2)))
        self._map_planet_surfaces.clear()
        self._planet_placeholders.clear()
        self.off_x = wx - (pos[0] - self.W / 2) / self.zoom
        self.off_y = wy - (pos[1] - self.H / 2) / self.zoom

    def _object_at(self, pos):
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
        return best_obj

    def _handle_map_click(self, pos, additive=False):
        ship = self._ship_at(pos)
        if ship is not None:
            if additive:
                self._toggle_ship_selection(ship)
            else:
                self._set_ship_selection([ship])
            self._rebuild_panel_buttons()
            return
        best_obj = self._object_at(pos)
        if best_obj:
            self.selected_star, self.selected_planet = best_obj
            self.player.select(*best_obj)
            self._rebuild_panel_buttons()
            self._rebuild_action_buttons()
        elif not additive:
            self._set_ship_selection([])
            self._rebuild_panel_buttons()

    def _handle_map_right_click(self, pos):
        """Botão direito: ordem de movimento sobre o alvo, ou cerco de seleção."""
        if self.selected_ships:
            target = self._object_at(pos)
            if target is not None:
                self._order_ships('move', star=target[0])
                return
        self._marquee = [pos, pos]

    def _finish_marquee(self, additive=False):
        if self._marquee is None:
            return
        first, second = self._marquee
        self._marquee = None
        rect = pygame.Rect(
            min(first[0], second[0]), min(first[1], second[1]),
            abs(second[0] - first[0]), abs(second[1] - first[1]))
        if rect.width < 6 and rect.height < 6:
            return
        found = self._ships_in_rect(rect)
        if not found:
            if not additive:
                self._set_ship_selection([])
            return
        if additive:
            self._set_ship_selection(
                list(dict.fromkeys(self.selected_ships + found)))
        else:
            self._set_ship_selection(found)
        self.log_msg(f"{len(self.selected_ships)} naves selecionadas")
        self._rebuild_panel_buttons()

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
            from graphics.star import HABITAT_MAX_PER_PLANET
            if p.habitats >= HABITAT_MAX_PER_PLANET:
                self._action_buttons.append(Button(
                    (x, y, 170, 24), "Habitats: máx.",
                    lambda: None, enabled=lambda: False))
                x += 180
            elif p.habitat_building:
                self._action_buttons.append(Button(
                    (x, y, 170, 24), "Habitat em construção",
                    lambda: None, enabled=lambda: False))
                x += 180
            else:
                self._action_buttons.append(Button(
                    (x, y, 170, 24), "Construir habitat",
                    lambda: self._build_habitat(p),
                    enabled=lambda: f.can_build_habitat(p)))
                x += 180
            ah_label = f"Auto-habitat: {'ON' if f.auto_habitat else 'OFF'}"
            self._action_buttons.append(Button(
                (x, y, 170, 24), ah_label, self._toggle_auto_habitat))
            x += 180
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
        self._drain_planet_textures()

    def _draw_victory(self):
        overlay = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        overlay.fill((3, 8, 18, 190))
        self.screen.blit(overlay, (0, 0))
        winner = self.state.winner
        outcome = "VOCÊ VENCEU" if winner is self.faction else "FIM DE JOGO"
        title = self.f_title.render(outcome, True, C.ACCENT)
        detail = self.f.render(
            f"{winner.name} conquistou a vitória "
            f"{self.state.winner_condition or self.state.VICTORY_MODES[self.state.victory_mode]}.",
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
        zoom = self.zoom
        step = self.GRID_BASE_STEP
        spacing = step * zoom
        # Coarsen the lattice when zoomed far out so on-screen dot spacing
        # stays readable and the number of draw calls stays bounded. At
        # normal zoom (spacing >= GRID_MIN_PX) the grid is unchanged.
        while spacing < self.GRID_MIN_PX:
            step *= 2
            spacing = step * zoom
        map_w = self.W - self.PANEL_W
        left = self.off_x - self.W / 2 / zoom
        top = self.off_y - self.H / 2 / zoom
        first_gx = math.floor(left / step) * step
        first_gy = math.floor(top / step) * step
        cx0 = self.W / 2 - self.off_x * zoom
        cy0 = self.H / 2 - self.off_y * zoom
        screen = self.screen
        draw_circle = pygame.draw.circle
        color = C.GRID
        gy = first_gy
        sy = gy * zoom + cy0
        while sy < self.H:
            if sy >= 0:
                sx = first_gx * zoom + cx0
                gx = first_gx
                while sx < map_w:
                    if sx >= 0:
                        draw_circle(screen, color, (int(sx), int(sy)), 1)
                    gx += step
                    sx = gx * zoom + cx0
            gy += step
            sy = gy * zoom + cy0


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
            self._draw_belt_specks(s)
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

    def _belt_specks(self, star):
        cached = self._belt_speck_cache.get(star.name)
        if cached is None:
            cached = []
            distances = sorted({
                p.distance_from_star for p in star.planets
                if planet_type_of(p) == 'asteroid'})
            base = distances[0] if distances else 1.0
            for dist in distances:
                generator = random.Random(f"{star.name}:belt:{dist:.4f}")
                omega = 0.25 * (base / max(dist, 1e-6)) ** 1.5
                specks = [(generator.uniform(0, math.tau),
                           generator.uniform(-0.035, 0.035))
                          for _ in range(26)]
                cached.append((dist, omega, specks))
            self._belt_speck_cache[star.name] = cached
        return cached

    def _draw_belt_specks(self, star):
        for dist, omega, specks in self._belt_specks(star):
            orbit_px = dist * self.zoom
            if orbit_px < 8 or orbit_px > self.W:
                continue
            phase = self.state.time * omega
            for angle0, jitter in specks:
                angle = angle0 + phase
                r = dist * (1.0 + jitter)
                px, py = self.world_to_screen(
                    star.position[0] + r * math.cos(angle),
                    star.position[1] + r * math.sin(angle))
                if -2 <= px <= self.W + 2 and -2 <= py <= self.H + 2:
                    pygame.draw.circle(self.screen, C.BELT_SPECK,
                                       (px, py), 1)

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
        clip = self._clip_to_viewport(start[0], start[1], end[0], end[1])
        if clip is None:
            return
        # Dash grid stays anchored to the true start; only the visible span is
        # drawn, so zooming in no longer iterates thousands of off-screen px.
        dash_length, gap_length = 9, 6
        period = dash_length + gap_length
        lo, hi = clip[0] * length, clip[1] * length
        offset = (lo // period) * period
        ux, uy = dx / length, dy / length
        while offset < hi:
            a = max(offset, lo)
            b = min(offset + dash_length, hi)
            if a < b:
                pygame.draw.line(
                    self.screen, color,
                    (round(start[0] + ux * a), round(start[1] + uy * a)),
                    (round(start[0] + ux * b), round(start[1] + uy * b)), 1)
            offset += period

    def _clip_to_viewport(self, x0, y0, x1, y1):
        """Liang-Barsky clip of a screen segment to the map rect.

        Returns the (t0, t1) parameter bounds that fall inside the viewport, or
        None when the whole segment is off-screen.
        """
        w, h = self.W, self.H
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x0), (dx, w - x0), (-dy, y0), (dy, h - y0)):
            if p == 0.0:
                if q < 0.0:
                    return None
            else:
                r = q / p
                if p < 0.0:
                    if r > t1:
                        return None
                    if r > t0:
                        t0 = r
                else:
                    if r < t0:
                        return None
                    if r < t1:
                        t1 = r
        return t0, t1

    def _draw_ships(self):
        for s in self.faction.ships.copy().values():
            if not s.alive:
                continue
            self._draw_ship_sprite(s, s in self.selected_ships)
        for f in self.state.factions:
            if f is self.faction or f.eliminated:
                continue
            for s in list(f.ships.values()):
                if not s.alive:
                    continue
                self._draw_ship_sprite(s, False)
        self._draw_order_markers()
        self._draw_marquee()

    def _draw_order_markers(self):
        """Rota tracejada até o alvo das ordens manuais pendentes."""
        for ship in self._own_ships():
            order = ship.order
            if order is None or order['kind'] != 'move':
                continue
            star = order['star']
            if star is None:
                continue
            start = self.world_to_screen(*ship.abs_position)
            end = self.world_to_screen(*star.position)
            self._draw_dashed_line(start, end, C.SELECTED)
            pygame.draw.circle(self.screen, C.SELECTED, end, 6, 1)

    def _draw_marquee(self):
        if self._marquee is None:
            return
        first, second = self._marquee
        rect = pygame.Rect(
            min(first[0], second[0]), min(first[1], second[1]),
            abs(second[0] - first[0]), abs(second[1] - first[1]))
        pygame.draw.rect(self.screen, C.SELECTED, rect, 1)
        shade = pygame.Surface(rect.size, pygame.SRCALPHA)
        shade.fill((124, 224, 255, 26))
        self.screen.blit(shade, rect.topleft)

    def _rotated_ship_sprite(self, filename, color, size, heading):
        """Sprite virado para o rumo do voo, em passos de 15 graus."""
        step = 360.0 / self.SHIP_HEADING_STEPS
        index = 0
        if heading is not None:
            rotation = -math.degrees(heading) - 90.0
            index = int(round(rotation / step)) % self.SHIP_HEADING_STEPS
        key = (filename, color, size, index)
        sprite = self._ship_sprite_cache.get(key)
        if sprite is None:
            base = self._ship_base_sprite(filename, color, size)
            sprite = (base if index == 0
                      else pygame.transform.rotate(base, index * step))
            if len(self._ship_sprite_cache) > 768:
                self._ship_sprite_cache.clear()
            self._ship_sprite_cache[key] = sprite
        return sprite

    def _ship_base_sprite(self, filename, color, size):
        """Base descascada (sem rotação), mantida para sempre.

        O cache de sprites rotacionados é limpo quando cresce demais porque o
        tamanho depende do zoom; sem este cache, cada limpeza voltaria a ler o
        PNG do disco e a tiñá-lo com numpy durante o quadro.
        """
        key = (filename, color, size)
        base = self._ship_base_cache.get(key)
        if base is None:
            base = get_ship_sprite(filename, color, (size, size))
            self._ship_base_cache[key] = base
        return base

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
        sprite = self._rotated_ship_sprite(
            design['sprite'], self._hex_to_rgb(ship.faction.color),
            size, getattr(ship, 'heading', None),
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
        status_clip = self._topbar_status_clip_rect()
        if status_clip.width > 0:
            self.screen.set_clip(status_clip)
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
                f"  ·  Ociosas: {len(f.idle_colony_ships())}"
                f"  ·  Selecionadas: {len(self.selected_ships)}",
                True, C.DIM), (x0 + 10, y + 20))
            self.screen.blit(self.f_small.render(
                "Botão direito move a seleção; arraste para cercar.",
                True, C.DIM), (x0 + 10, y + 34))

        elif self.active_tab == 'colonies':
            colonies = list(f.colonies.values())
            population = sum(planet.population for planet in colonies)
            food = sum(planet.food_balance() for planet in colonies)
            self.screen.blit(self.f_med.render(
                f"COLÔNIAS ({len(colonies)})", True, C.ACCENT),
                (x0 + 10, y))
            self.screen.blit(self.f_small.render(
                f"Pop {format_population(population)} · alim {food:+.0f}/ano "
                f"· clique p/ gerir",
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
            hint = ("Clique em estrela/planeta — aba Sistema/Guerra "
                    "controla tudo")
            if self.selected_ships:
                hint = (f"{len(self.selected_ships)} naves selecionadas — "
                        "botão direito numa estrela dá a ordem de movimento")
            self.screen.blit(self.f.render(hint, True, C.DIM), (12, y0 + 12))
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
        from graphics.star import format_population as _fmt_pop
        tf = ""
        if p.is_colonized:
            exp = p.expansion_info()
            tf = (f"  exp {exp['level']}/{exp['max']}"
                  f" ({exp['percent'] * 100:.0f}%"
                  f", {exp['years_left']:.0f} anos)"
                  f"  hab {getattr(p, 'habitats', 0)}")
        type_label = PLANET_TYPE_LABELS.get(
            planet_type_of(p), 'Planeta')
        if getattr(p, 'has_rings', False):
            type_label += " (aneis)"
        self.screen.blit(self.f.render(
            f"  -> {p.name}  {type_label}  raio {p.radius:.3f}"
            f"  suit={suit:.2f}{tf}",
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
                f"  Pop {_fmt_pop(p.population)}/{_fmt_pop(pop_max)}  "
                f"dev {p.developement:.2f}/{dev_max:.2f}  "
                f"prod {p.annual_output():.1f}/ano",
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
            planet_type = planet_type_of(p)
            if planet_type == 'asteroid':
                category = 'MINERADOR'
            elif planet_type == 'gas_giant':
                category = 'ENERGIA'
            category_label = self.f_small.render(
                category.upper(), True, C.ACCENT)
            self.screen.blit(
                category_label,
                category_label.get_rect(
                    centerx=preview_x + preview_size // 2,
                    top=preview_y + preview_size + 4,
                ),
            )

    def _planet_texture_request(self, planet, size):
        """Chave de cache e argumentos do gerador para um mundo e tamanho."""
        suitability = tuple(sorted(planet.life_suitability.items()))
        capacity = planet.capacity_info()
        lights = round(city_light_intensity(
            planet.developement, planet.population,
            capacity['max_dev'], capacity['max_pop'],), 2)
        planet_type = planet_type_of(planet)
        rings = bool(getattr(planet, 'has_rings', False))
        habitats = int(getattr(planet, 'habitats', 0))
        greening = round(getattr(
            planet, 'terraforming_stage', lambda: 1.0)(), 2)
        key = (id(planet), suitability, size, lights, self.texture_detail,
               planet_type, rings, habitats, greening)
        return key, dict(city_lights=lights, detail_level=self.texture_detail,
                         planet_type=planet_type, rings=rings,
                         habitats=habitats, greening=greening)

    def _generate_planet_surface(self, planet, size):
        _, options = self._planet_texture_request(planet, size)
        star_name = (planet.parent_star.name
                     if planet.parent_star is not None else '')
        seed = f"{star_name}:{planet.name}"
        return generate_planet_surface(planet.life_suitability, seed, size,
                                       **options)

    def _planet_surface(self, planet, size):
        key, _ = self._planet_texture_request(planet, size)
        surface = self._planet_surfaces.get(key)
        if surface is None:
            surface = self._generate_planet_surface(planet, size)
            self._planet_surfaces[key] = surface
        return surface

    def _provisional_planet_surface(self, planet, wanted):
        """Melhor textura já gerada para o mesmo estado do mundo, ou None.

        O disco em si é barato; o que pesa é o traçado procedural. Enquanto a
        resolução do bucket estiver na fila, um bucket vizinho segura o lugar
        na tela; sem nenhum, `_placeholder_planet_surface` segura.
        """
        best_size = None
        best_surface = None
        for key, surface in self._planet_surfaces.items():
            if key[:2] != wanted[:2] or key[3:] != wanted[3:]:
                continue
            if best_size is None or abs(
                    key[2] - wanted[2]) < abs(best_size - wanted[2]):
                best_size, best_surface = key[2], surface
        return best_surface

    def _placeholder_planet_surface(self, planet, size):
        color = self._planet_color(planet)
        key = (id(planet), size, color)
        cached = self._planet_placeholders.get(key)
        if cached is None:
            cached = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(cached, color, (size // 2, size // 2),
                               max(1, size // 2))
            self._planet_placeholders[key] = cached
        return cached

    def _queued_planet_surface(self, planet, size):
        """Textura do bucket do mapa, gerada em quadro parado se faltar."""
        key, _ = self._planet_texture_request(planet, size)
        surface = self._planet_surfaces.get(key)
        if surface is not None:
            return surface
        self._planet_pending[key] = (planet, size)
        return self._provisional_planet_surface(planet, key)

    def _drain_planet_textures(self):
        """Gera as texturas adiadas quando a câmera parou de se mover."""
        if not self._planet_pending:
            return
        signature = (round(self.zoom, 4), round(self.off_x, 1),
                     round(self.off_y, 1))
        if signature != self._camera_key:
            self._camera_key = signature
            self._camera_still = 0
            return
        self._camera_still += 1
        if self._camera_still < 2:
            return
        deadline = time.perf_counter() + 0.05
        for key, (planet, size) in list(self._planet_pending.items()):
            self._planet_pending.pop(key, None)
            if key in self._planet_surfaces:
                continue
            self._planet_surfaces[key] = self._generate_planet_surface(
                planet, size)
            # O disco provisório virou obsoleto junto com a fila.
            self._map_planet_surfaces = {
                map_key: surface
                for map_key, surface in self._map_planet_surfaces.items()
                if map_key[0] != id(planet)
            }
            if time.perf_counter() > deadline:
                break

    def _map_planet_surface(self, planet, size):
        key, _ = self._planet_texture_request(planet, size)
        cached = self._map_planet_surfaces.get(key)
        if cached is not None:
            return cached
        render_size = min(512, max(64, 1 << (size - 1).bit_length()))
        surface = self._queued_planet_surface(planet, render_size)
        if surface is None:
            placeholder = self._placeholder_planet_surface(planet, size)
            self._map_planet_surfaces[key] = placeholder
            return placeholder
        scaled = (surface if surface.get_size() == (size, size)
                  else pygame.transform.smoothscale(surface, (size, size)))
        self._map_planet_surfaces[key] = scaled
        return scaled

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