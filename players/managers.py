import threading
import time

from players.ships import Scout
from queue import Queue, Empty
from typing import List, Dict, Set
from graphics.star import Planet, Star
import networkx as nx

def find_best(planet):
    if self.planet.can_build_ships:
        return self.planet.production * len(planet.const_queue)

    else:
        return 0

class ScoutManager:
    def __init__(self, faction):
        self.faction = faction
        self.scouts: Dict[int, Scout] = {}
        self.active_scouts = set()
        self.inactive_scouts = set()
        self.scout_construction_queue = Queue()
        self.manager_running = False
        self.lock = threading.Lock()
        self.scout_config = {
            'ly_per_second': ly_per_second,
            'scan_time': scan_time,
            'map_G': map_G,
            'current_position': current_position,
            'total_stars': total_stars,
            'faction': faction,
            **kwargs
        }
        
        # Estatísticas de monitoramento
        self.tasks_queue = Queue()
        self.stats = {
            'total_scouts_built': 0,
            'active_scouts': 0,
            'stars_explored': 0,
            'resources_spent': {res: 0 for res, _ in Scout.resources_needed}
        }
    
    def build_scout(self, ly_per_second: float, scan_time: float, map_G: nx.Graph, 
                   current_position: Star, total_stars: List[Star], planets:List[Planet] **kwargs) -> bool:
        """Tenta construir um novo scout"""
        
        task = {
            'ShipType':Scout,
            'Resouces_needed':Scout.resources_needed,
            'config': self.scout_config,
            'id': len(self.scouts)
        }

        planet = max(self.faction.colonies.values(), key=find_best)
        planet.const_queue.put(task)       
    
    def process_construction_queue(self):
        """Processa a fila de construção de scouts"""
        while self.manager_running:
            try:
                # Tentar pegar configuração da fila
                scout_config = self.scout_construction_queue.get(timeout=1)
                
                # Tentar construir scout
                if self.build_scout(**scout_config):
                    print(f"Scout construído da fila (ID: {self.stats['total_scouts_built']})")
                else:
                    # Se não há recursos, recoloca na fila
                    self.scout_construction_queue.put(scout_config)
                    time.sleep(5)  # Espera antes de tentar novamente
                
                self.scout_construction_queue.task_done()
                
            except Empty:
                continue
            except Exception as e:
                print(f"Erro ao processar fila de construção: {e}")
    
    def deactivate_scout(self, scout_id: int):
        """Desativa um scout"""
        with self.lock:
            if scout_id in self.active_scouts:
                self.active_scouts.remove(scout_id)
                self.inactive_scouts.add(scout_id)
                self.stats['active_scouts'] -= 1
                
                if scout_id in self.scouts:
                    self.scouts[scout_id].running = False
    
    def activate_scout(self, scout_id: int):
        """Reativa um scout"""
        with self.lock:
            if scout_id in self.inactive_scouts:
                self.inactive_scouts.remove(scout_id)
                self.active_scouts.add(scout_id)
                self.stats['active_scouts'] += 1
                
                if scout_id in self.scouts:
                    self.scouts[scout_id].running = True
                    # Reiniciar thread se necessário
                    scout_thread = threading.Thread(
                        target=self.scouts[scout_id].run,
                        name=f"Scout-{scout_id}",
                        daemon=True
                    )
                    scout_thread.start()
    
    def get_scout_status(self, scout_id: int) -> Dict:
        """Retorna o status de um scout específico"""
        if scout_id not in self.scouts:
            return {"status": "not_found"}
        
        scout = self.scouts[scout_id]
        return {
            "status": "active" if scout_id in self.active_scouts else "inactive",
            "current_position": scout.current_position.name if scout.current_position else "Unknown",
            "exploration_queue_size": scout.exploration_queue.qsize(),
            "running": scout.running
        }
    
    def get_all_scouts_status(self) -> List[Dict]:
        """Retorna status de todos os scouts"""
        status_list = []
        with self.lock:
            for scout_id in self.scouts:
                status = self.get_scout_status(scout_id)
                status['scout_id'] = scout_id
                status_list.append(status)
        return status
    
    def update_stats(self):
        """Atualiza estatísticas de monitoramento"""
        with self.lock:
            self.stats['stars_explored'] = len(Scout.already_explored)
            self.stats['active_scouts'] = len(self.active_scouts)
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas atuais"""
        self.update_stats()
        return self.stats.copy()
    
    def assign_scout_to_sector(self, scout_id: int, target_sector: List['Star']):
        """Atribui um scout para explorar um setor específico"""
        if scout_id not in self.scouts:
            return False
        
        scout = self.scouts[scout_id]
        
        # Limpar fila atual e adicionar estrelas do setor
        while not scout.exploration_queue.empty():
            try:
                scout.exploration_queue.get_nowait()
                scout.exploration_queue.task_done()
            except Empty:
                break
        
        # Adicionar estrelas do setor à fila
        for star in target_sector:
            scout.exploration_queue.put((star, None))
        
        return True
    
    def emergency_recall(self):
        """Recupera todos os scouts para a posição inicial"""
        with self.lock:
            for scout_id in self.active_scouts:
                if scout_id in self.scouts:
                    scout = self.scouts[scout_id]
                    scout.running = False
                    
                    # Limpar fila de exploração
                    while not scout.exploration_queue.empty():
                        try:
                            scout.exploration_queue.get_nowait()
                            scout.exploration_queue.task_done()
                        except Empty:
                            break
                    
                    # Adicionar tarefa de retorno
                    if hasattr(scout, 'faction') and hasattr(scout.faction, 'home_star'):
                        scout.exploration_queue.put((scout.faction.home_star, None))
    
    def start_manager(self):
        """Inicia o gerenciador de scouts"""
        self.manager_running = True
        
        # Thread para processar fila de construção
        construction_thread = threading.Thread(
            target=self.process_construction_queue,
            name="ScoutConstruction",
            daemon=True
        )
        construction_thread.start()
        
        # Thread para monitoramento
        monitoring_thread = threading.Thread(
            target=self.monitor_scouts,
            name="ScoutMonitoring",
            daemon=True
        )
        monitoring_thread.start()
    
    def stop_manager(self):
        """Para o gerenciador de scouts"""
        self.manager_running = False
        self.emergency_recall()
    
    def monitor_scouts(self):
        """Monitora o status dos scouts periodicamente"""
        while self.manager_running:
            try:
                self.update_stats()
                
                # Verificar scouts inativos por muito tempo
                current_time = time.time()
                for scout_id in list(self.inactive_scouts):
                    # Lógica para reativar scouts após certo tempo se necessário
                    pass
                
                time.sleep(10)  # Verificar a cada 10 segundos
                
            except Exception as e:
                print(f"Erro no monitoramento: {e}")
                time.sleep(5)

