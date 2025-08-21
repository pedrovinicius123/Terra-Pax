from dataclasses import dataclass
from typing import Tuple, Dict, List, Any
from queue import Queue, Empty
import threading

@dataclass
class Planet:
    n_planet_resources: int
    planet_resources:Dict[str, float]
    abs_position: Tuple[int, int]
    life_suitability: Dict[str, float]
    production:float
    developement:float
    distance_from_star: float
    radius:float
    is_colonized:bool
    name:str

    def post_init(self):
        self.const_queue = Queue()
        self.developement = 0.1
        self.can_build_ships = False
        self.lock = threading.Lock()
        self.population = 0
        self.storage_capacity = {
            'Minerals': 1000,
            'Food': 500,
            'Energy': 2000,
            'Electronics': 300,
            'Chemicals': 300,
            'Alloys': 200,
            'Research': float('inf')
        }
        self.faction = None
        self.ships = []

    def develop(self):
        self.developement *= 1.1
        self.population *= 1.1

        if self.developement > 3:
            self.developement *= 1.4
            self.population *= 1.4

        if self.developement > 10:
            self.developement *= 1.6
            self.population *= 1.6
            self.can_build_ships = True
        
        self.const()
        self.produce()

    def can_afford(self, cost: Dict[str, int]) -> bool:
        """Verifica se a facção pode pagar por algo"""
        with self.lock:
            for resource, amount in cost.items():
                if self.planet_resources[resource] < amount:
                    return False
            return True

    def const(self):
        current_task = self.const_queue.get()
        if self.can_afford(current_task.get('Resources_needed')):
            print('CREATING SHIP')
            self.pay_cost(current_task.get('Resources_needed'))
            time.sleep(20)

            # Criar ship
            ship_id = self.name + f"{current_task.get('ShipType')}" + current_task.get('id')
            ship = current_task['ShipType'](
                **current_task.get('config')
            )
            
            # Iniciar thread da ship
            ship.start()
            self.ships.append(ship)


    def pay_cost(self, cost: Dict[str, int]) -> bool:
        """Tenta pagar um custo"""
        if not self.can_afford(cost):
            return False

        for resource, amount in cost.items():
            self.remove_resource(resource, amount)
        return True

    def produce(self):
        for resource in self.planet_resources.keys():
            if self.planet_resources[resource] > self.storage_capacity[resource]:
                continue
            
            if resource == 'Food':
                self.planet_resources[resource] -= self.population*1e-4

            if resource == 'Research':
                self.faction.research_progress += self.production*self.developement
                continue

            self.planet_resources[resource] += self.production*self.developement            


    def remove_resource(self, resource_type: str, amount: int) -> bool:
        """Remove recursos do armazenamento"""
        if resource_type not in self.planet_resources.keys():
            return False
        
        if self.planet_resources[resource_type] >= amount:
            self.resources[resource_type] -= amount
            return True
            
        return False


# Dataclass for start sistems, with random generation.
@dataclass
class Star:
    name: str
    total_resources: int
    radius:float
    green_zone: float
    position: Tuple[int, int]
    planets:List[Planet]

