"""Optional headless Chrome check. Run with the legacy Selenium environment."""
import json
import os
import secrets
import subprocess
import time
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait
from sqlalchemy import delete
from recipe_app_v2.database import get_write_engine
from recipe_app_v2.models import Query_History

ROOT = Path(__file__).resolve().parent.parent
CHROME = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')


def verify():
    test_query = 'ground turkey NOT "v2-history-test-' + secrets.token_hex(6) + '"'
    version = subprocess.check_output(['powershell', '-NoProfile', '-Command',
        f"(Get-Item '{CHROME}').VersionInfo.ProductVersion"], text=True).strip()
    target = ROOT / 'recipe_app_v2/.browser-tools'
    target.mkdir(exist_ok=True)
    target = target / version
    target.mkdir(exist_ok=True)
    driver_path = target / 'chromedriver-win64/chromedriver.exe'
    if not driver_path.is_file():
        with urlopen('https://googlechromelabs.github.io/chrome-for-testing/latest-patch-versions-per-build-with-downloads.json', timeout=30) as response:
            builds = json.load(response)['builds']
        build = builds['.'.join(version.split('.')[:3])]
        url = next(d['url'] for d in build['downloads']['chromedriver'] if d['platform'] == 'win64')
        archive = target / 'driver.zip'
        with urlopen(url, timeout=60) as response:
            archive.write_bytes(response.read())
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                resolved = (target / member.filename).resolve()
                if target.resolve() not in resolved.parents:
                    raise RuntimeError('Driver archive has an unsafe path')
            bundle.extractall(target)
    with TemporaryDirectory(dir=target) as profile:
        options = webdriver.ChromeOptions()
        options.binary_location = str(CHROME)
        options.add_argument('--headless=new')
        options.add_argument('--window-size=1200,900')
        options.add_argument('--user-data-dir=' + profile)
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        browser = webdriver.Chrome(service=Service(str(driver_path)), options=options)
        try:
            wait = WebDriverWait(browser, 20)
            browser.get('http://127.0.0.1:8001/')
            browser.execute_script('window.searchVerificationMarker = 42')
            browser.find_element(By.ID, 'search-query').send_keys('chicken')
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('q') == ['chicken'])
            assert browser.execute_script('return window.searchVerificationMarker') == 42
            assert browser.find_element(By.ID, 'search-query').get_attribute('value') == 'chicken'
            assert browser.execute_script('return document.activeElement.id') == 'search-query'
            browser.find_element(By.ID, 'search-query').send_keys(' ')
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('q') == ['chicken '])
            assert browser.find_element(By.ID, 'search-query').get_attribute('value') == 'chicken '
            browser.find_element(By.ID, 'search-query').send_keys('NOT cream')
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('q') == ['chicken NOT cream'])
            Select(browser.find_element(By.ID, 'sort')).select_by_value('name')
            browser.find_element(By.ID, 'sort').find_element(By.XPATH, '..').find_element(By.TAG_NAME, 'button').click()
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('sort') == ['name'])
            assert parse_qs(urlsplit(browser.current_url).query)['q'] == ['chicken NOT cream']
            browser.find_element(By.CSS_SELECTOR, '.pagination a:last-child').click()
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('page') == ['2'])
            assert browser.execute_script('return window.searchVerificationMarker') == 42
            browser.back()
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('page', ['1']) == ['1'])
            wait.until(lambda b: b.find_element(By.ID, 'search-query').get_attribute('value') == 'chicken NOT cream')
            browser.forward()
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('page') == ['2'])
            browser.find_element(By.CSS_SELECTOR, '.recipe-link').click()
            wait.until(lambda b: '/recipes/' in urlsplit(b.current_url).path)
            browser.find_element(By.CLASS_NAME, 'back-link').click()
            wait.until(lambda b: urlsplit(b.current_url).path == '/')
            params = parse_qs(urlsplit(browser.current_url).query)
            assert params['q'] == ['chicken NOT cream'] and params['page'] == ['2'] and params['sort'] == ['name']
            browser.find_element(By.LINK_TEXT, 'Clear search').click()
            wait.until(lambda b: 'q' not in parse_qs(urlsplit(b.current_url).query))
            assert browser.find_element(By.ID, 'search-query').get_attribute('value') == ''
            errors = [e for e in browser.get_log('browser') if e['level'] == 'SEVERE' and 'favicon.ico' not in e['message']]
            assert not errors, 'Browser reported JavaScript or network errors'
            # A response can arrive after another keystroke but before the next
            # debounced request starts. It must never replace the search input.
            browser.get('http://127.0.0.1:8001/')
            browser.execute_script("window.slowSearchStarted = false; window.searchInput = document.getElementById('search-query'); document.body.addEventListener('htmx:beforeRequest', e => { if (e.detail.requestConfig.verb === 'get' && e.detail.requestConfig.path === '/') window.slowSearchStarted = true; })")
            browser.execute_cdp_cmd('Network.enable', {})
            browser.execute_cdp_cmd('Network.emulateNetworkConditions', {
                'offline': False, 'latency': 700, 'downloadThroughput': -1, 'uploadThroughput': -1})
            query_input = browser.find_element(By.ID, 'search-query')
            query_input.send_keys('chicken')
            wait.until(lambda b: b.execute_script('return window.slowSearchStarted'))
            time.sleep(.5)
            query_input.send_keys(' ')
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('q') == ['chicken '])
            assert query_input.get_attribute('value') == 'chicken '
            assert browser.execute_script("return window.searchInput === document.getElementById('search-query')")
            browser.execute_cdp_cmd('Network.emulateNetworkConditions', {
                'offline': False, 'latency': 0, 'downloadThroughput': -1, 'uploadThroughput': -1})
            browser.execute_cdp_cmd('Emulation.setScriptExecutionDisabled', {'value': True})
            browser.get('http://127.0.0.1:8001/')
            browser.find_element(By.ID, 'search-query').send_keys(test_query)
            browser.find_element(By.ID, 'submit-search').click()
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('q') == [test_query])
            Select(browser.find_element(By.ID, 'sort')).select_by_value('name')
            browser.find_element(By.ID, 'sort').find_element(By.XPATH, '..').find_element(By.TAG_NAME, 'button').click()
            wait.until(lambda b: parse_qs(urlsplit(b.current_url).query).get('sort') == ['name'])
            assert parse_qs(urlsplit(browser.current_url).query)['q'] == [test_query]
            print(json.dumps({'live_typing': 'ok', 'focus_preserved': True, 'htmx_without_reload': True,
                              'sort_pagination_detail_back': 'ok', 'clear_search': 'ok',
                              'browser_history': 'ok', 'slow_response_typing': 'ok',
                              'without_javascript': 'ok'}))
        finally:
            browser.quit()
            original = os.environ.get('RECIPE_DEV_WRITES')
            try:
                os.environ['RECIPE_DEV_WRITES'] = '1'
                with get_write_engine().begin() as connection:
                    connection.execute(delete(Query_History).where(Query_History.query_text == test_query))
            finally:
                if original is None:
                    os.environ.pop('RECIPE_DEV_WRITES', None)
                else:
                    os.environ['RECIPE_DEV_WRITES'] = original


if __name__ == '__main__':
    verify()
