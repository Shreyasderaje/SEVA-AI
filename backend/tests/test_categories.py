"""Public taxonomy endpoint: fixed categories + display subcategories."""


def test_categories_lists_five_fixed_classes(client):
    response = client.get("/api/categories")
    assert response.status_code == 200
    categories = response.json()
    codes = [c["code"] for c in categories]
    assert codes == ["clothing", "grains_rice", "packaged_food", "utensils", "other"]
    assert all(c["display_name"] for c in categories)


def test_categories_include_example_display_subcategories(client):
    response = client.get("/api/categories")
    by_code = {c["code"]: c for c in response.json()}
    clothing_names = [s["display_name"] for s in by_code["clothing"]["subcategories"]]
    assert "Men's" in clothing_names and "Children's" in clothing_names
    grains_names = [s["display_name"] for s in by_code["grains_rice"]["subcategories"]]
    assert "Rice" in grains_names and "Pulses" in grains_names
    assert by_code["other"]["subcategories"]  # Miscellaneous seeded


def test_categories_is_public(client):
    response = client.get("/api/categories")
    assert response.status_code == 200  # no auth required
