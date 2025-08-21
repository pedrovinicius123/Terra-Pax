import networkx as nx
import string
import random
import math
import pygame

from graphics.star import Planet, Star


def generate_traditional_star_name():
    """Generate names in the astronomical traditional catalogue"""
    
    # Common Catalogue
    catalogue = [
        "HD", "HIP", "HR", "GJ", "BD", "CD", "CPD", 
        "TYC", "2MASS", "WISE", "GSC", "SAO"
    ]
    
    # Greek letters for bright stars
    greek = [
        "Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", 
        "Eta", "Theta", "Iota", "Kappa", "Lambda", "Mu", 
        "Nu", "Xi", "Omicron", "Pi", "Rho", "Sigma", 
        "Tau", "Upsilon", "Phi", "Chi", "Psi", "Omega"
    ]

    # constelations
    constelations = [
        "Andromedae", "Antliae", "Apodis", "Aquarii", "Aquilae", 
        "Arae", "Arietis", "Aurigae", "Bootis", "Caeli", 
        "Camelopardalis", "Cancri", "Canum Venaticorum", "Canis Majoris", 
        "Canis Minoris", "Capricorni", "Carinae", "Cassiopeiae", 
        "Centauri", "Cephei", "Ceti", "Chamaeleontis", "Circini", 
        "Columbae", "Comae Berenices", "Coronae Australis", "Coronae Borealis", 
        "Corvi", "Crateris", "Crucis", "Cygni", "Delphini", 
        "Doradus", "Draconis", "Equulei", "Eridani", "Fornacis", 
        "Geminorum", "Gruis", "Herculis", "Horologii", "Hydrae", 
        "Hydri", "Indi", "Lacertae", "Leonis", "Leonis Minoris", 
        "Leporis", "Librae", "Lupi", "Lyncis", "Lyrae", 
        "Mensae", "Microscopii", "Monocerotis", "Muscae", "Normae", 
        "Octantis", "Ophiuchi", "Orionis", "Pavonis", "Pegasi", 
        "Persei", "Phoenicis", "Pictoris", "Piscium", "Piscis Austrini", 
        "Puppis", "Pyxidis", "Reticuli", "Sagittarii", "Scorpii", 
        "Sculptoris", "Scuti", "Serpentis", "Sextantis", "Tauri", 
        "Telescopii", "Trianguli", "Trianguli Australis", "Tucanae", 
        "Ursae Majoris", "Ursae Minoris", "Velorum", "Virginis", 
        "Volantis", "Vulpeculae"
    ]
    
    # Chose an random method
    method = random.choice(["catalogue", "greek", "number"])
    
    if method == "catalogue":
        catalogue = random.choice(catalogue)
        number = random.randint(1, 999999)
        return f"{catalogue} {number}"
    
    elif method == "greek":
        letter = random.choice(greek)
        constelation = random.choice(constelations)
        return f"{letter} {constelation}"
    
    else:  # number
        constelation = random.choice(constelations)
        number = random.randint(1, 300)
        return f"{number} {constelation}"



def init_map(n_stars:int, sector_size:int, min_dist:int):
    stars = []
    for i in range(n_stars):
        random_position = [random.uniform(0, sector_size), random.uniform(0, sector_size)]
        random_planet_position_x = random.uniform(0,1)
        random_planet_position_y = random.uniform(0,1)
        star_radius = random.uniform(0.03, 0.05)

        stars.append(
            Star(
            name=generate_traditional_star_name(),
            total_resources = random.uniform(1e4, 1e6),
            radius=star_radius,
            green_zone = random.uniform(1, 2)*star_radius,
            position = random_position,
            #faction='',
            planets=[])
        )

        for i in range(random.randint(1, 10)):
            p = Planet(
                n_planet_resources=0,
                abs_position=(random_position[0] + random_planet_position_x, random_position[1] + random_planet_position_y),
                planet_resources={},
                life_suitability={},
                production=0,
                distance_from_star=math.sqrt(random_planet_position_x**2 + random_planet_position_y**2),
                is_colonized=False,
                radius=random.uniform(0.01, 0.03)
                
            )

            p.post_init()
            stars[-1].planets.append(p)

    map_G = nx.Graph()

    for star in stars:
        for other in stars:
            dist = math.dist(star.position, other.position)

            if other.position != star.position and dist < min_dist:
                print(dist)
                map_G.add_edge(star.name, other.name, weight=dist)

    return map_G, stars