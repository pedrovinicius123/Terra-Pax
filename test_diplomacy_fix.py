
import sys
import os
sys.path.append(os.getcwd())

from players.factions import Faction, DiplomacyStatus, FactionType
from graphics.star import Star, Planet

def test_diplomacy_flow():
    # Star(name, position, radius, green_zone, planets) 
    # I will try passing an extra empty list or checking if there's a default.
    # The error says missing 1 positional argument 'planets' but I passed [].
    # Maybe the signature is different. Let's try adding one more.
    
    # Looking at the error: Star("Star1", (0,0,0), 10.0, 5.0, [])
    # missing 1 required positional argument: 'planets'
    # This is strange. I'll try to inspect the Star.__init__ signature or just add one more.
    # Actually, let's just use a simpler approach to verify the logic since the logic is already fixed.
    
    # Mocking the necessary parts of Star and Planet to avoid signature issues
    class MockStar:
        def __init__(self, name, pos): self.name = name; self.pos = pos
    class MockPlanet:
        def __init__(self, name, star, pos): 
            self.name = name; self.star = star; self.abs_position = pos
            self.is_colonized = False; self.faction = None
            self.planet_resources = {}; self.population = 0
            self.production = 1.0; self.developement = 0.1
            self.can_build_ships = True; self.defense = 0; self.max_defense = 0

    star1 = MockStar("Star1", (0,0,0))
    planet1 = MockPlanet("Planet1", star1, (0,0,0))
    star2 = MockStar("Star2", (100,0,0))
    planet2 = MockPlanet("Planet2", star2, (100,0,0))
    
    f1 = Faction("Player", FactionType.HUMAN, planet1, star1)
    f2 = Faction("AI", FactionType.ALIEN, planet2, star2)
    
    print("Step 1: AI proposes peace, Player refuses")
    f2.propose_peace(f1)
    assert f2.name in f1.pending_peace_offers
    f1.respond_to_peace_offer(f2, accept=False)
    assert f2.name in f1.declined_peace_offers
    
    print("Step 2: Player proposes peace back to AI")
    success = f1.propose_peace(f2)
    assert success is True, "Proposing peace should succeed even if previously declined"
    assert f1.name in f2.pending_peace_offers
    assert f1.name not in f2.declined_peace_offers, "Proposing should clear declined status"
    
    print("Step 3: AI accepts proposal")
    f2.respond_to_peace_offer(f1, accept=True)
    
    status_f1 = f1.diplomacy.get(f2.name, set())
    status_f2 = f2.diplomacy.get(f1.name, set())
    
    print(f"Final Statuses: Player={status_f1}, AI={status_f2}")
    assert DiplomacyStatus.PEACE in status_f1
    assert DiplomacyStatus.PEACE in status_f2
    print("TEST SUCCESSFUL")

if __name__ == '__main__':
    try:
        test_diplomacy_flow()
    except Exception as e:
        print(f"TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
