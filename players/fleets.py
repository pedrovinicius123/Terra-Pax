"""Frotas: agrupamentos de naves que se movem e recebem ordens juntas."""

import math


FLEET_SIZE_LIMIT = 12
MAX_FLEETS = 16


class Fleet:
    def __init__(self, fleet_id, name, faction):
        self.fleet_id = fleet_id
        self.name = name
        self.faction = faction
        self.member_ids = []

    # ---------- membros ----------
    @property
    def ships(self):
        registry = self.faction.ships
        members = [registry[ship_id] for ship_id in self.member_ids
                   if ship_id in registry and registry[ship_id].alive]
        self.member_ids = [ship.ship_id for ship in members]
        return members

    def add(self, ship):
        if (ship is None or not ship.alive
                or ship.ship_id in self.member_ids
                or len(self.member_ids) >= FLEET_SIZE_LIMIT):
            return False
        self.member_ids.append(ship.ship_id)
        return True

    def remove(self, ship_id):
        if ship_id in self.member_ids:
            self.member_ids.remove(ship_id)
            return True
        return False

    def __len__(self):
        return len(self.member_ids)

    # ---------- valores agregados ----------
    def total_hull(self):
        return sum(ship.hull for ship in self.ships)

    def total_firepower(self):
        return sum(ship.weapons + ship.shields for ship in self.ships)

    def min_speed(self):
        speeds = [ship.speed for ship in self.ships]
        return min(speeds) if speeds else 0.0

    def location(self):
        """Estrela com mais naves da frota; None quando dispersa."""
        counts = {}
        stars = {}
        for ship in self.ships:
            star = ship.current_position
            if star is None:
                continue
            counts[star.name] = counts.get(star.name, 0) + 1
            stars.setdefault(star.name, star)
        if not counts:
            return None
        busiest = max(counts, key=lambda name: (counts[name], name))
        return stars[busiest]

    def is_grouped(self):
        ships = self.ships
        if not ships:
            return False
        names = set()
        for ship in ships:
            if ship.current_position is None:
                return False
            names.add(ship.current_position.name)
        return len(names) == 1

    def is_moving(self):
        return any(ship.is_moving for ship in self.ships)

    def status(self):
        if not self.ships:
            return "vazia"
        if self.is_moving():
            return "em trânsito"
        star = self.location()
        return f"orbitada em {star.name}" if star else "dispersa"

    # ---------- ordens conjuntas ----------
    def _broadcast(self, kind, star=None):
        # A frota inteira viaja na velocidade da nave mais lenta, de modo
        # que o grupo permaneça junto ao longo do salto.
        cap = self.min_speed() or None
        issued = 0
        for ship in self.ships:
            if ship.issue_order(kind, star=star, speed_cap=cap):
                issued += 1
        return issued

    def order_move(self, star):
        if star is None:
            return 0
        return self._broadcast('move', star=star)

    def order_hold(self):
        return self._broadcast('hold')

    def order_resume(self):
        return self._broadcast('clear')

    def summary(self):
        star = self.location()
        return {
            'fleet_id': self.fleet_id,
            'name': self.name,
            'ships': len(self.ships),
            'hull': self.total_hull(),
            'firepower': self.total_firepower(),
            'speed': self.min_speed(),
            'status': self.status(),
            'location': star.name if star is not None else None,
        }


class FleetManager:
    def __init__(self, faction, max_fleets=MAX_FLEETS):
        self.faction = faction
        self.fleets = {}
        self._counter = 0
        self.max_fleets = max_fleets

    # ---------- criação e dissolução ----------
    def create(self, ships=(), name=None):
        if len(self.fleets) >= self.max_fleets:
            return None
        self._counter += 1
        fleet_id = f"{self.faction.name[:3].upper()}-F{self._counter:02d}"
        fleet = Fleet(fleet_id,
                      name or f"Frota {self._counter}",
                      self.faction)
        self.fleets[fleet_id] = fleet
        for ship in ships:
            fleet.add(ship)
        if not fleet.ships:
            del self.fleets[fleet_id]
            return None
        return fleet

    def disband(self, fleet_id):
        return self.fleets.pop(fleet_id, None) is not None

    def rename(self, fleet_id, name):
        fleet = self.fleets.get(fleet_id)
        if fleet is None or not name:
            return False
        fleet.name = str(name)[:24]
        return True

    def fleet_of(self, ship_id):
        for fleet in self.fleets.values():
            if ship_id in fleet.member_ids:
                return fleet
        return None

    def assign(self, ship, fleet_id):
        fleet = self.fleets.get(fleet_id)
        if fleet is None or ship is None:
            return False
        current = self.fleet_of(ship.ship_id)
        if current is fleet:
            return True
        if current is not None:
            current.remove(ship.ship_id)
        if not fleet.add(ship):
            return False
        self.prune()
        return True

    def unassigned(self):
        assigned = {ship_id for fleet in self.fleets.values()
                    for ship_id in fleet.member_ids}
        return [ship for ship in self.faction.ships.values()
                if ship.alive and ship.ship_id not in assigned]

    def auto_group(self):
        """Agrupa naves ociosas por estrela, respeitando o limite por frota."""
        self.prune()
        groups = {}
        for ship in self.unassigned():
            star = ship.current_position
            if star is None:
                continue
            groups.setdefault(star.name, []).append(ship)
        created = 0
        for name in sorted(groups):
            pending = groups[name]
            while pending:
                batch = pending[:FLEET_SIZE_LIMIT]
                pending = pending[FLEET_SIZE_LIMIT:]
                if self.create(batch, name=f"Frota {name}") is None:
                    break
                created += 1
        return created

    def prune(self):
        """Descarta frotas que perderam todas as naves."""
        empty = [fleet_id for fleet_id, fleet in self.fleets.items()
                 if not fleet.ships]
        for fleet_id in empty:
            del self.fleets[fleet_id]
        return len(empty)

    def summaries(self):
        self.prune()
        return [fleet.summary() for fleet in self.fleets.values()]

    def order(self, fleet_id, kind, star=None):
        fleet = self.fleets.get(fleet_id)
        if fleet is None:
            return 0
        if kind == 'move':
            return fleet.order_move(star)
        if kind == 'hold':
            return fleet.order_hold()
        if kind == 'clear':
            return fleet.order_resume()
        return 0

    def fleet_strength(self):
        return sum(fleet.total_firepower()
                   for fleet in self.fleets.values())
