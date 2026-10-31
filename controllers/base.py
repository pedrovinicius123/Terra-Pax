# controllers/base.py
class BaseController:
    def __init__(self, faction):
        self.faction = faction

    def update(self, state, dt):
        pass