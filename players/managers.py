import threading


class ScoutManager:
    def __init__(self, faction):
        self.faction = faction
        self.active_scouts = set()
        self.lock = threading.Lock()
        self.stats = {'stars_explored': 0, 'active_scouts': 0}

    def register_scout(self, scout_id, scout):
        with self.lock:
            self.active_scouts.add(scout_id)
            self.stats['active_scouts'] = len(self.active_scouts)

    def update_stats(self):
        self.stats['stars_explored'] = len(self.faction.explored_stars)
        self.stats['active_scouts'] = len(self.active_scouts)

    def get_stats(self):
        self.update_stats()
        return dict(self.stats)

    def start_manager(self):
        pass

    def stop_manager(self):
        pass
    