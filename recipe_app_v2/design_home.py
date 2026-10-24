"""Sample content for the isolated homepage design study. No database access."""

LIBRARY_PALETTES = {
    'forest': dict(name='Forest', accent='#27634b', hover='#1c4c38',
                   quiet='#f2f6f3', rule='#dce4de', description='Deep green with a quiet botanical tint.'),
    'oxblood': dict(name='Oxblood', accent='#8c3544', hover='#702737',
                    quiet='#faf3f4', rule='#e9dcdf', description='Rich wine red with a soft rose tint.'),
    'aubergine': dict(name='Aubergine', accent='#704676', hover='#58345e',
                      quiet='#f7f3f8', rule='#e5dce7', description='Muted purple with a pale lavender tint.'),
    'burnt-orange': dict(name='Burnt orange', accent='#a84b26', hover='#863a1c',
                         quiet='#fbf5f0', rule='#eaded4', description='Warm burnt orange with a light apricot tint.'),
    'graphite': dict(name='Graphite', accent='#42484d', hover='#292f34',
                     quiet='#f4f5f5', rule='#dfe2e3', description='Charcoal gray for a restrained, almost monochrome finish.'),
}

HOME_LAYOUTS = [
    ("gallery", "Gallery", "Generous photographs. An open, three-column grid."),
    ("library", "Library", "Your collections within reach. A denser grid with a browsing sidebar."),
    ("spotlight", "Spotlight", "One recipe takes the lead. A split feature above the collection."),
    ("index", "Index", "More recipes at a glance. Compact rows with useful details."),
    ("weekboard", "Weekboard", "Recipes and dinner plans together. A grid with a weekly planning rail."),
]

HOME_RECIPES = [
    dict(id=1, title="Sticky gochujang chicken", image="100.jpg", cuisine="Korean", collection="Weeknight dinners", minutes=35, ingredients=6, servings=4, cooked=3, viewed=12, favorite=True, planned=True, source="Kitchen notes", ingredient_images=["chicken_thigh.jpg", "gochujang.jpg", "garlic.jpg"]),
    dict(id=2, title="Sunday night lasagna", image="1.jpg", cuisine="Italian", collection="Comfort food", minutes=85, ingredients=12, servings=8, cooked=8, viewed=26, favorite=True, planned=False, source="Family cookbook", ingredient_images=["lasagne_noodle.jpg", "ricotta_cheese.jpg", "tomato.jpg"]),
    dict(id=3, title="Smashed cucumber salad", image="111.jpg", cuisine="Chinese", collection="Vegetables & sides", minutes=15, ingredients=6, servings=4, cooked=0, viewed=2, favorite=False, planned=True, source="Kitchen notes", ingredient_images=["cucumber.jpg", "garlic.jpg", "red_chili.jpg"]),
    dict(id=4, title="Carrots with green goddess dressing", image="103.jpg", cuisine="American", collection="Vegetables & sides", minutes=25, ingredients=8, servings=4, cooked=2, viewed=7, favorite=False, planned=False, source="Saved recipes", ingredient_images=["baby_carrots.jpg", "greek_yogurt.jpg", "garlic.jpg"]),
    dict(id=5, title="Chocolate cookie icebox cake", image="107.jpg", cuisine="American", collection="Something sweet", minutes=20, ingredients=5, servings=8, cooked=1, viewed=5, favorite=True, planned=False, source="Family cookbook", ingredient_images=["cream.jpg", "sugar.jpg"]),
    dict(id=6, title="Tomato-baked fish with spinach", image="101.jpg", cuisine="Mediterranean", collection="Weeknight dinners", minutes=30, ingredients=9, servings=2, cooked=0, viewed=3, favorite=False, planned=False, source="Saved recipes", ingredient_images=["tomato.jpg", "baby_spinach.jpg", "garlic.jpg"]),
]

DESCRIPTIONS = [
    "Sticky edges, a little heat, and plenty of sauce for the rice. A dependable dinner in 35 minutes.",
    "Layers of slow-cooked tomato sauce, pasta, and ricotta. Make enough for tomorrow, too.",
    "Cool cucumber, fresh chile, and a sharp garlic dressing. The side that wakes up dinner.",
    "Sweet roasted carrots meet a bright, herby yogurt dressing.",
    "Chocolate cookies and softly whipped cream. A make-ahead dessert for a full table.",
    "Tender white fish under juicy tomatoes, with spinach to catch the pan juices.",
]

# Sample recency ranks are separate from cooking/view event counts.
for recipe, description, last_cooked, last_viewed in zip(
    HOME_RECIPES, DESCRIPTIONS, [6, 3, 0, 4, 2, 0], [5, 2, 6, 3, 1, 4]
):
    recipe.update(description=description, added=7-recipe['id'],
                  last_cooked=last_cooked, last_viewed=last_viewed)

COLLECTIONS = ["All recipes", "Favorites", "Never cooked", "Meal plan",
               "Weeknight dinners", "Comfort food", "Vegetables & sides", "Something sweet"]
CUISINES = sorted({recipe['cuisine'] for recipe in HOME_RECIPES})
