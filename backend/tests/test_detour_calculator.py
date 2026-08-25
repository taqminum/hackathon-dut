from app.services.detour_calculator import calculate_detour


def test_calculate_detour():
    assert calculate_detour(600, 900) == 300
