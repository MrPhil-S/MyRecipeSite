"""Exercise recipe activity using owned dev fixtures; preserve existing table data."""
import json
import os
import re
import secrets
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .activity import CHILDREN
from .database import get_engine, get_write_engine
from .models import Collection, Recipe, Recipe_Ingredient, Recipe_Instruction, Recipe_Plan_Date, recipe_collection, recipe_cooked_date, recipe_view_date
from .verify_editor import FormParser, inventory


def browser_check(recipe_id, collection_id):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.common.exceptions import StaleElementReferenceException
    root = Path(__file__).resolve().parent
    driver_path = next((root / '.browser-tools').glob('*/chromedriver-win64/chromedriver.exe'))
    for javascript in (True, False):
        with TemporaryDirectory(dir=root / '.browser-tools') as profile:
            options = webdriver.ChromeOptions()
            options.binary_location = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
            options.add_argument('--headless=new')
            options.add_argument('--window-size=1200,900')
            options.add_argument('--user-data-dir=' + profile)
            if not javascript:
                options.add_experimental_option('prefs', {'profile.managed_default_content_settings.javascript': 2})
            browser = webdriver.Chrome(service=Service(str(driver_path)), options=options)
            try:
                wait = WebDriverWait(browser, 20, ignored_exceptions=(StaleElementReferenceException,))
                browser.get(f'http://127.0.0.1:8001/?collection_id={collection_id}&sort=visited')
                if javascript:
                    browser.execute_script('window.activityMarker = 42')
                card = f'[data-recipe-id="{recipe_id}"]'
                wait.until(lambda b: b.find_element(By.CSS_SELECTOR, card + ' button').text == 'Add to plan')
                browser.find_element(By.CSS_SELECTOR, card + ' button').click()
                wait.until(lambda b: b.find_element(By.CSS_SELECTOR, card + ' button').text == 'Remove from plan')
                assert f'collection_id={collection_id}' in browser.current_url
                if javascript:
                    assert browser.execute_script('return window.activityMarker') == 42
                browser.get('http://127.0.0.1:8001/plan')
                plan_card = f'[data-plan-recipe-id="{recipe_id}"]'
                if javascript:
                    browser.execute_script('window.activityMarker = 42')
                old = browser.find_element(By.CSS_SELECTOR, plan_card)
                browser.find_element(By.CSS_SELECTOR, plan_card + ' form[action$="/cooked"] button').click()
                wait.until(lambda b: stale(old))
                wait.until(lambda b: b.find_element(By.CSS_SELECTOR, plan_card))
                browser.find_element(By.CSS_SELECTOR, plan_card + ' form[action$="/plan-remove"] button').click()
                wait.until(lambda b: not b.find_elements(By.CSS_SELECTOR, plan_card))
                if javascript:
                    assert browser.execute_script('return window.activityMarker') == 42
            finally:
                browser.quit()


def stale(element):
    from selenium.common.exceptions import StaleElementReferenceException
    try:
        element.is_enabled()
        return False
    except StaleElementReferenceException:
        return True


def verify(browser=False):
    os.environ['RECIPE_DEV_WRITES'] = '1'
    before = inventory()
    prefix = 'V2 activity ' + secrets.token_hex(6)
    owned_id = collection_id = None
    try:
        with Session(get_write_engine()) as session:
            collection = Collection(collection_name=prefix)
            recipe = Recipe(name=prefix, collections=[collection])
            session.add(recipe)
            session.flush()
            owned_id, collection_id = recipe.recipe_id, collection.collection_id
            session.add_all([Recipe_Ingredient(recipe_id=owned_id, name_written=prefix),
                Recipe_Instruction(recipe_id=owned_id, text_contents='Mix', type=1)])
            session.commit()
        with httpx.Client(base_url='http://127.0.0.1:8001', timeout=30) as client:
            assert client.get('/health').json()['database'] == 'MyRecipes_DEV'
            context = f'/?sort=visited&q={prefix.replace(" ", "+")}&collection_id={collection_id}'
            listing = client.get(context)
            assert listing.status_code == 200 and f'data-recipe-id="{owned_id}"' in listing.text
            token = dict(FormParser(listing.text).fields)['csrf_token']
            def action(name, target='/plan'):
                response = client.post(f'/recipes/{owned_id}/actions/{name}',
                    data={'csrf_token': token, 'return_to': target})
                assert response.status_code == 303 and response.headers['location'] == target
            detail = client.get(f'/recipes/{owned_id}')
            assert detail.status_code == 200 and '1 recorded views' in detail.text
            action('cooked', context)
            action('plan-add')
            action('plan-add')
            plan = client.get('/plan')
            assert f'data-plan-recipe-id="{owned_id}"' in plan.text and 'Added ' in plan.text
            legacy = httpx.get('http://127.0.0.1:8080/plan', timeout=30)
            assert legacy.status_code == 200 and prefix in legacy.text
            with Session(get_engine()) as session:
                active = set(session.scalars(select(Recipe_Plan_Date.recipe_id).where(Recipe_Plan_Date.removed_dt.is_(None))))
                rendered = set(map(int, re.findall(r'data-plan-recipe-id="(\d+)"', plan.text)))
                assert active == rendered
                for model in (recipe_view_date, recipe_cooked_date, Recipe_Plan_Date):
                    assert session.scalar(select(func.count()).select_from(model).where(model.recipe_id == owned_id)) == 1
            for sort in ('recent', 'name', 'cooked', 'visited'):
                body = client.get('/', params={'sort': sort, 'q': prefix, 'collection_id': collection_id}).text
                assert f'data-recipe-id="{owned_id}"' in body and 'collection_id=' in body
            action('plan-remove')
            assert f'data-plan-recipe-id="{owned_id}"' not in client.get('/plan').text
            if browser:
                browser_check(owned_id, collection_id)
            action('plan-add')
            confirm = client.get(f'/recipes/{owned_id}/delete?from_plan=true')
            fields = dict(FormParser(confirm.text).fields)
            response = client.post(f'/recipes/{owned_id}/delete', data=fields)
            assert response.status_code == 303 and response.headers['location'] == '/plan'
            assert client.get(f'/recipes/{owned_id}?log_visit=false').status_code == 404
            with Session(get_engine()) as session:
                for model in CHILDREN:
                    assert session.scalar(select(func.count()).select_from(model).where(model.recipe_id == owned_id)) == 0
    finally:
        with Session(get_write_engine()) as session:
            if owned_id is not None:
                recipe = session.get(Recipe, owned_id)
                if recipe is not None:
                    assert recipe.name == prefix, 'Fixture ownership changed; refusing cleanup.'
                    for model in CHILDREN:
                        session.execute(delete(model).where(model.recipe_id == owned_id))
                    session.execute(delete(recipe_collection).where(recipe_collection.c.recipe_id == owned_id))
                    session.expire(recipe, ['collections'])
                    session.delete(recipe)
            if collection_id is not None:
                collection = session.get(Collection, collection_id)
                assert collection.collection_name == prefix
                session.delete(collection)
            session.commit()
    assert inventory() == before, 'Dev table data changed after fixture cleanup.'
    return {'activity_plan_delete_collection_sorts': 'passed', 'browser_htmx_and_no_javascript': 'passed' if browser else 'not run', 'plan_matches_existing_active_recipes': True,
            'dev_tables_unchanged_after_cleanup': len(before)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--browser', action='store_true')
    print(json.dumps(verify(parser.parse_args().browser), indent=2))
