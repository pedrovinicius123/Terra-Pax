import networkx as nx
import random
import math

from graphics.star import Planet, Star
from graphics.planet_generator import generate_suitability_profile


def generate_traditional_star_name():
    catalogue = ["HD", "HIP", "HR", "GJ", "BD", "CD", "CPD",
                 "TYC", "2MASS", "WISE", "GSC", "SAO"]
    greek = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta",
             "Eta", "Theta", "Iota", "Kappa", "Lambda", "Mu",
             "Nu", "Xi", "Omicron", "Pi", "Rho", "Sigma",
             "Tau", "Upsilon", "Phi", "Chi", "Psi", "Omega"]
    constelations = [
        "Andromedae", "Antliae", "Apodis", "Aquarii", "Aquilae", "Arae",
        "Arietis", "Aurigae", "Bootis", "Caeli", "Camelopardalis", "Cancri",
        "Canum Venaticorum", "Canis Majoris", "Canis Minoris", "Capricorni",
        "Carinae", "Cassiopeiae", "Centauri", "Cephei", "Ceti",
        "Chamaeleontis", "Circini", "Columbae", "Comae Berenices",
        "Coronae Australis", "Coronae Borealis", "Corvi", "Crateris",
        "Crucis", "Cygni", "Delphini", "Doradus", "Draconis", "Equulei",
        "Eridani", "Fornacis", "Geminorum", "Gruis", "Herculis",
        "Horologii", "Hydrae", "Hydri", "Indi", "Lacertae", "Leonis",
        "Leonis Minoris", "Leporis", "Librae", "Lupi", "Lyncis", "Lyrae",
        "Mensae", "Microscopii", "Monocerotis", "Muscae", "Normae",
        "Octantis", "Ophiuchi", "Orionis", "Pavonis", "Pegasi", "Persei",
        "Phoenicis", "Pictoris", "Piscium", "Piscis Austrini", "Puppis",
        "Pyxidis", "Reticuli", "Sagittarii", "Scorpii", "Sculptoris",
        "Scuti", "Serpentis", "Sextantis", "Tauri", "Telescopii",
        "Trianguli", "Trianguli Australis", "Tucanae", "Ursae Majoris",
        "Ursae Minoris", "Velorum", "Virginis", "Volantis", "Vulpeculae",
    ]
    method = random.choice(["catalogue", "greek", "number"])
    if method == "catalogue":
        return f"{random.choice(catalogue)} {random.randint(1, 999999)}"
    if method == "greek":
        return f"{random.choice(greek)} {random.choice(constelations)}"
    return f"{random.randint(1, 300)} {random.choice(constelations)}"


def init_map(n_stars: int, sector_size: int, min_dist: int):
    stars = []
    used_star_names = set()
    planet_letters = "bcdefghi"
    star_positions = []
    minimum_system_spacing = (
        0.4 * sector_size / math.sqrt(max(1, n_stars)))
    max_placement_attempts = max(100, n_stars * 20)

    for _ in range(n_stars):
        for attempt in range(max_placement_attempts):
            pos = [random.uniform(0, sector_size),
                   random.uniform(0, sector_size)]
            if all(math.dist(pos, other) >= minimum_system_spacing
                   for other in star_positions):
                star_positions.append(pos)
                break
        else:
            raise ValueError(
                f"Could not place {n_stars} stars with minimum spacing "
                f"{minimum_system_spacing:.1f} in a {sector_size} unit sector "
                f"after {attempt + 1} attempts"
            )

        # Astro sizes stay small compared with inter-system distances.
        star_r = random.uniform(0.003, 0.005) * sector_size
        planet_r = random.uniform(0.0007, 0.0012) * sector_size

        star_name = generate_traditional_star_name()
        base_name = star_name
        suffix = 2
        while star_name in used_star_names:
            star_name = f"{base_name}-{suffix}"
            suffix += 1
        used_star_names.add(star_name)

        star = Star(
            name=star_name,
            total_resources=random.uniform(1e4, 1e6),
            radius=star_r,
            green_zone=random.uniform(1, 2) * star_r,
            position=pos,
            planets=[],
        )
        stars.append(star)

        # Órbitas compactas, em camadas: base + k * passo
        n_planets = random.randint(1, 8)
        base_orbit = star_r * 1.5
        orbit_step = star_r * 0.35

        for k in range(n_planets):
            dist = base_orbit + k * orbit_step
            angle = random.uniform(0, 2 * math.pi)
            px = pos[0] + dist * math.cos(angle)
            py = pos[1] + dist * math.sin(angle)

            p = Planet(
                n_planet_resources=0,
                developement=0,
                name=f"{star.name}-{planet_letters[k]}",
                abs_position=(px, py),
                planet_resources={},
                life_suitability=generate_suitability_profile(),
                production=1.0,
                distance_from_star=dist,
                is_colonized=False,
                radius=planet_r,
                star_position=star.position
            )
            p.post_init()
            p.parent_star = star
            star.planets.append(p)

    G = nx.Graph()
    for s in stars:
        G.add_node(s.name)
    for i, s1 in enumerate(stars):
        for s2 in stars[i + 1:]:
            d = math.dist(s1.position, s2.position)
            if 0 < d < min_dist:
                G.add_edge(s1.name, s2.name, weight=d)
    return G, stars
