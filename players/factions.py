import threading
import time
from typing import Dict, List, Set, Optional, Tuple
from enum import Enum
from queue import Queue
from graphics import Star, Planet
import networkx as nx

class FactionType(Enum):
    HUMAN = "Human"
    ALIEN = "Alien"
    ROBOT = "Robot"
    HYBRID = "Hybrid"

class DiplomacyStatus(Enum):
    WAR = "War"
    CONFLICT = "Conflict"
    NEUTRAL = "Neutral"
    PEACE = "Peace"
    ALLY = "Ally"

class Faction:
    def __init__(self, name: str, faction_type: FactionType, home_planet:'Planet', home_star: 'Star', 
                 starting_resources: Optional[Dict] = None):
        # Identificação da facção
        self.name = name
        self.faction_type = faction_type
        self.home_star = home_star
        self.home_planet = home_planet
        self.color = self._generate_faction_color()

        # Sistema de recursos
        self.resources = {
            'Minerals': 100,
            'Food': 100,
            'Energy': 100,
            'Electronics': 50,
            'Chemicals': 50,
            'Alloys': 25,
            'Research': 0
        }

        self.home_planet.planet_resources = self.resources        
        if starting_resources:
            self.resources.update(starting_resources)
        self.faction_task_queue = Queue()
        
        # Unidades e estruturas
        self.ships = {}
        self.stations = {}
        self.colonies = {self.home_planet.name: home_planet}
        self.scout_manager = None
        
        # Sistema de pesquisa e tecnologia
        self.tech_tree = {
            'exploration': 1,
            'propulsion': 1,
            'weapons': 1,
            'shields': 1,
            'sensors': 1,
            'construction': 1
        }
        self.research_queue = Queue()
        self.current_research = None
        self.research_progress = 0
        
        # Diplomacia
        self.diplomacy = {}  # {faction_name: DiplomacyStatus}
        self.war_declarations = set()
        self.allies = set()
        
        # Território e exploração
        self.controlled_stars = {home_star.name: home_star}
        self.explored_stars = set([home_star.name])
        self.claimed_systems = set([home_star.name])
        
        # Economia e produção
        self.production_queue = Queue()
        self.construction_projects = {}
        self.economy = {
            'mineral_income': 10,
            'energy_income': 15,
            'research_income': 5,
            'maintenance_cost': 0
        }
        
        # Threading e controle
        self.running = False
        self.lock = threading.Lock()
        self.threads = []
        
        # Estatísticas
        self.stats = {
            'ships_built': 0,
            'stations_built': 0,
            'colonies_established': 0,
            'stars_explored': 0,
            'battles_won': 0,
            'battles_lost': 0,
            'research_completed': 0
        }
    
    def _generate_faction_color(self) -> str:
        """Gera uma cor única baseada no tipo de facção"""
        colors = {
            FactionType.HUMAN: "#3498db",    # Azul
            FactionType.ALIEN: "#e74c3c",    # Vermelho
            FactionType.ROBOT: "#95a5a6",    # Cinza
            FactionType.HYBRID: "#9b59b6"    # Roxo
        }
        return colors.get(self.faction_type, "#ffffff")
    
    def initialize_scout_manager(self, map_G: nx.Graph, total_stars: List['Star']):
        """Inicializa o gerenciador de scouts"""
        from scout_manager import ScoutManager  # Importação local para evitar circular imports
        
        self.scout_manager = ScoutManager(self)
        
        # Configuração base dos scouts
        self.scout_config = {
            'ly_per_second': 2.0 + (self.tech_tree['propulsion'] * 0.5),
            'scan_time': 3.0 - (self.tech_tree['sensors'] * 0.2),
            'map_G': map_G,
            'current_position': self.home_star,
            'total_stars': total_stars
        }
        
        self.scout_manager.start_manager()
    
    def get_resource(self, resource_type: str) -> int:
        """Retorna a quantidade de um recurso"""
        return self.resources.get(resource_type, 0)   
    
    def queue_scout_construction(self):
        """Adiciona um scout à fila de construção"""
        if self.scout_manager:
            self.scout_manager.build_scout(**self.scout_config)
    
    def queue_research(self, tech_field: str):
        """Adiciona uma tecnologia à fila de pesquisa"""
        if tech_field in self.tech_tree:
            self.research_queue.put(tech_field)
    
    def process_research(self):
        """Processa a pesquisa tecnológica"""
        if self.current_research is None and not self.research_queue.empty():
            self.current_research = self.research_queue.get()
            self.research_progress = 0
        
        if self.current_research:
            research_cost = self.get_research_cost(self.current_research)
            
            if self.research_progress >= research_cost:
                # Pesquisa concluída
                self.tech_tree[self.current_research] += 1
                self.stats['research_completed'] += 1
                print(f"{self.name} completou pesquisa em {self.current_research}!")
                self.current_research = None
                self.research_progress = 0
            else:
                # Continuar pesquisa
                research_income = self.economy['research_income']
                self.research_progress += research_income
    
    def get_research_cost(self, tech_field: str) -> int:
        """Retorna o custo de pesquisa para um campo tecnológico"""
        current_level = self.tech_tree[tech_field]
        base_costs = {
            'exploration': 100,
            'propulsion': 120,
            'weapons': 150,
            'shields': 140,
            'sensors': 110,
            'construction': 130
        }
        return base_costs.get(tech_field, 100) * current_level
    
    
    
    def handle_power_shortage(self):
        """Lida com falta de energia"""
        print(f"ALERTA: {self.name} está com falta de energia!")
        # Desativar scouts primeiro
        if self.scout_manager:
            for scout_id in list(self.scout_manager.active_scouts):
                self.scout_manager.deactivate_scout(scout_id)
    
    def establish_colony(self, star: 'Star', planet:'Planet') -> bool:
        """Tenta estabelecer uma colônia"""
        colony_cost = {
            'Minerals': 200,
            'Electronics': 100,
            'Chemicals': 80,
            'Energy': 150
        }
        
        if not self.can_afford(colony_cost):
            return False
        
        if self.pay_cost(colony_cost):
            colony_id = f"colony_{len(self.colonies) + 1}"
            
            score = 0
            best_planet = None

            for planet in self.current_position.planets:
                if not planet.is_colonized:
                    local_score = planet.life_suitability[self.faction] * planet.planet_resources[0].quantity * planet.planet_resources[1].quantity
                    
                    if local_score > score:
                        score = local_score
                        best_planet = planet

            if best_planet is None:
                return False

            best_planet.planet_resources = {
                'Minerals': 10,
                'Food': 10,
                'Energy': 10,
                'Electronics': 1,
                'Chemicals': 1,
                'Alloys': 0.5,
            }

            best_planet.population = 1000
            self.colonies[colony_id] = {
                'star': star,
                'planet': best_planet,
                'developement': best_planet.developement
            }
            
            self.controlled_stars[star.name] = star
            self.stats['colonies_established'] += 1

            return True
        return False
    
    def update_diplomacy(self, other_faction: 'Faction', new_status: DiplomacyStatus):
        """Atualiza status diplomático com outra facção"""
        self.diplomacy[other_faction.name] = new_status
        
        if new_status == DiplomacyStatus.WAR:
            self.war_declarations.add(other_faction.name)
            self.allies.discard(other_faction.name)
        elif new_status == DiplomacyStatus.ALLY:
            self.allies.add(other_faction.name)
            self.war_declarations.discard(other_faction.name)
        elif new_status == DiplomacyStatus.NEUTRAL:
            self.war_declarations.discard(other_faction.name)
            self.allies.discard(other_faction.name)
    
    def run_faction(self):
        """Loop principal da facção"""
        self.running = True
        print(f"Facção {self.name} inicializada!")
        
        while self.running:
            try:                
                # Processar pesquisa
                self.process_research()
                
                # Construir scouts se possível
                if (self.scout_manager and 
                    len(self.scout_manager.active_scouts) < 3 + self.tech_tree['exploration']):
                    self.queue_scout_construction()
                
                # Atualizar estatísticas
                if self.scout_manager:
                    scout_stats = self.scout_manager.get_stats()
                    self.stats['stars_explored'] = scout_stats['stars_explored']
                
                time.sleep(5)  # Ciclo de 5 segundos
                
            except Exception as e:
                print(f"Erro na facção {self.name}: {e}")
                time.sleep(10)
    
    def start_faction(self):
        """Inicia todas as threads da facção"""
        # Thread principal da facção
        main_thread = threading.Thread(
            target=self.run_faction,
            name=f"Faction-{self.name}",
            daemon=True
        )
        main_thread.start()
        self.threads.append(main_thread)
        
        print(f"Facção {self.name} iniciada com sucesso!")
    
    def stop_faction(self):
        """Para todas as operações da facção"""
        self.running = False
        
        if self.scout_manager:
            self.scout_manager.stop_manager()
        
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=1)
    
    def get_status_report(self) -> Dict:
        """Retorna um relatório completo do status da facção"""
        return {
            'name': self.name,
            'faction_type': self.faction_type.value,
            'resources': self.resources.copy(),
            'tech_levels': self.tech_tree.copy(),
            'controlled_stars': len(self.controlled_stars),
            'colonies': len(self.colonies),
            'active_scouts': self.scout_manager.stats['active_scouts'] if self.scout_manager else 0,
            'stars_explored': self.stats['stars_explored'],
            'current_research': self.current_research,
            'research_progress': self.research_progress,
            'economy': self.economy.copy()
        }
    
    def __del__(self):
        """Destrutor - garante que tudo seja parado corretamente"""
        self.stop_faction()