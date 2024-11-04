import csv
import datetime
import os

import requests
from recipe_scrapers import scrape_html

from myrecipes import db
from myrecipes.models import Recipe, Recipe_Instruction

#SELECT r.recipe_id  , source_url
#FROM recipe r
#left join `recipe__instruction`  ri
#on  r.recipe_id = ri.recipe_id
#WHERE ri.recipe_id is null
#and length(source_url) > 1


def scrape(recipe_id=None, source_url=None):
#result = SomeModel.query.with_entities(SomeModel.col1, SomeModel.col2)

    if recipe_id is None:
        print('Scraping many...')
        recipe_with_no_instructions = (
            db.session.query(Recipe.recipe_id, Recipe.source_url)
            .select_from(Recipe)
            .join(Recipe_Instruction, Recipe.recipe_id == Recipe_Instruction.recipe_id, isouter=True)
            .filter(Recipe_Instruction.recipe_id.is_(None))
            .order_by(Recipe.recipe_id)
            .all()
        )
    for i, recipe in enumerate(recipe_with_no_instructions):
        if i > 30:
            break
        global total_recipe_count
        total_recipe_count = len(recipe_with_no_instructions)

        recipe_id, source_url = recipe
        scrape_recipe(i, recipe_id, source_url)    
    else:
        print('Scraping one...')
        scrape_recipe(1, recipe_id, source_url)
    return total_recipe_count, recipe_scrape_count

def scrape_recipe(i, recipe_id, source_url):
    global recipe_scrape_count
    recipe_scrape_count = 0
    name = 'bob'
    recipe_update_dt = datetime.datetime.now()
    
    instructions_list = None
    try:
        html = requests.get(source_url, headers={"User-Agent": f"Pie eater {name}"}).content

        print(f'{round(i/total_recipe_count*100,2)}% trying recipe_id: {recipe_id} ({source_url})...')
        scraper = scrape_html(html, org_url=source_url, wild_mode=False)
        instructions_list = scraper.instructions_list()

        if len(instructions_list)>1:
            sequence = 0
            is_group_header = 0

            for instruction in instructions_list:
                sequence += 1
                recipe = Recipe.query.get_or_404(recipe_id)
                instruction = Recipe_Instruction(text_contents=instruction.strip(), sequence=sequence, type=1, is_group_header=is_group_header, recipe_id=recipe_id)
                recipe.update_dt = recipe_update_dt
                db.session.add(instruction)
                db.session.commit()
            recipe_scrape_count += 1
            print(f'Recipe_id: {recipe_id}: {sequence} instructions scraped')
        else:
            print(f'Recipe_id: {recipe_id}: No instructions found')
    except Exception as e:
        print(f'Recipe_id: {recipe_id}: ERROR: {e}')


