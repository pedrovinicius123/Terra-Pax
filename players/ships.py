import threading
import numpy as np
import networkx as nx
import time

from typing import List
from graphics.star import Star, Planet
import networkx as nx
import math
from typing import List
from queue import Queue

class Ship(threading.Thread):
    lock = threading.Lock()   # Lock compartilhado para todos os scouts

    def __init__(self, ly_per_second: float, map_G: nx.Graph,
                 current_position: Star, ship_id: int, faction:object, total_stars:List[Star]):

        super().__init__()

        # Configurações base
        self.total_stars = total_stars
        self.faction=faction
        self.ship_id = ship_id
        self.ly_per_second = ly_per_second
        self.map_G = map_G
        self.abs_position = list(current_position.position)
        self.running = False
        self.current_position = current_position
        self.daemon = True
        
        # Mapeamento de nomes para objetos Star
        self.stars_dict = {star.name: star for star in self.total_stars}
        self.abs_position = current_position.position

    def run(self):
        pass

    def move_to_star(self, from_star, to_star):
        """Move o scout de uma estrela para outra"""
        distance = self.map_G[from_star.name][to_star.name]['weight']
        steps = max(10, int(distance / self.ly_per_second) * 10)  # Mínimo de 10 steps
        
        positions_x = np.linspace(from_star.position[0], to_star.position[0], steps)
        positions_y = np.linspace(from_star.position[1], to_star.position[1], steps)
        
        print(f"Nave {self.ship_id} viajando de {from_star.name} para {to_star.name}")
        
        for i, j in zip(positions_x, positions_y):
            if not self.running:
                break
                
            self.abs_position[0] = i
            self.abs_position[1] = j
            time.sleep(0.01)  # Movimento mais suave

        self.current_position = to_star

    def find_path_to_star(self, target_star):
        """Encontra o caminho para uma estrela usando Dijkstra"""
        try:
            # Encontrar estrela atual mais próxima
            current_pos = np.array(self.abs_position)
            distances = [np.linalg.norm(current_pos - np.array(star.position)) 
                        for star in self.total_stars]
            current_idx = np.argmin(distances)
            current_star = self.total_stars[current_idx]
            
            # Encontrar caminho
            path = nx.shortest_path(self.map_G, current_star.name, target_star.name, 
                                    weight='weight')
            return [self.stars_dict[star_name] for star_name in path[1:]]  # Pular a atual
            
        except (nx.NetworkXNoPath, KeyError):
            return None

    def stop(self):
        """Para a thread do scout"""
        self.running = False



class Scout(Ship):
    already_explored = set()  # Usar set() é mais eficiente que list()
    in_exploration = set()
    resources_needed = {'Minerals': 10, 'Food': 2, 'Electronics': 5, 'Chemicals': 10}

    def __init__(self, ly_per_second: float, scan_time: float, map_G: nx.Graph, 
                 current_position: Star, total_stars: List[Star], scout_id: int, faction:object, **kwargs):
        super().__init__(ly_per_second, map_G, current_position, scout_id, faction, total_stars=total_stars)
        # Configurações Base do Scout
        self.total_stars = total_stars
        self.scan_time = scan_time
        self.abs_position = list(current_position.position)
        self.running = False
        self.current_position = current_position
        
        # Sistema de fila para gerenciar exploração
        self.exploration_queue = Queue()
        self.exploration_queue.put((current_position, None))  # Primeira tarefa

    def run(self):
        self.running = True
        print(f"Scout {self.ship_id} construido em {self.current_position.name}")
        
        while self.running and not self.exploration_queue.empty():
            # Processar próxima tarefa da fila
            if self.exploration_queue.empty():
                if self.find_unexplored():
                    continue
                else:
                    print(f"Scout {self.ship_id}: Nada mais para explorar")
                    break                

            s, anterior_s = self.exploration_queue.get(timeout=0.1)
            self.process_exploration(s, anterior_s)
            self.exploration_queue.task_done()
                
            time.sleep(0.01)  # Pequena pausa para não sobrecarregar

    def calculate_dist(self, star):
        return math.dist(self.current_position.position, star.position)

    def process_exploration(self, s, anterior_s):
        """Processa a exploração de uma estrela"""
        # Marcar como explorado
        if s.name not in Scout.already_explored:
            Scout.in_exploration.add(s.name)
            print(f"Scout {self.ship_id} explorando {s.name}")
            
            # Gerar planetas se necessário
            if hasattr(s, 'generate'):
                s.generate
            
            # Escanear planetas
            for idx, planet in enumerate(s.planets):
                time.sleep(self.scan_time)
                print(f"Scout {self.ship_id} escaneou planeta {idx} da estrela {s.name}")

            Scout.already_explored.add(s.name)

        # Obter estrelas vizinhas
        next_stars = list(self.map_G.neighbors(s.name))
        
        # Adicionar vizinhos não explorados à fila
        stars_to_chose = list(filter(lambda x: x not in Scout.already_explored, next_stars)) 
        to_chose = sorted(map(lambda x: self.stars_dict[x], stars_to_chose), key=self.calculate_dist)

        with Scout.lock:
            for chosed in to_chose:
                if chosed.name not in Scout.in_exploration:
                    Scout.in_exploration.add(chosed.name)
                    self.exploration_queue.put((chosed, s))
                    self.move_to_star(s, chosed)
                    break

        # Voltar para estrela anterior se necessário
        if anterior_s is not None and self.exploration_queue.empty():
            self.move_to_star(s, anterior_s)

    def find_unexplored(self):
        """Tenta encontrar estrelas não exploradas"""
        with Scout.lock:
            unexplored = [star for star in self.total_stars 
                         if star.name not in Scout.already_explored]
        
        if unexplored:
            # Encontrar a estrela não explorada mais próxima
            current_pos = np.array(self.abs_position)
            distances = [np.linalg.norm(current_pos - np.array(star.position)) 
                        for star in unexplored]
            nearest_idx = np.argmin(distances)
            nearest_star = unexplored[nearest_idx]
            
            # Encontrar caminho para a estrela mais próxima
            path = self.find_path_to_star(nearest_star)
            if path:
                # Adicionar todo o caminho à fila
                for star in path:
                    self.exploration_queue.put((star, None))
                return True
        
        return False