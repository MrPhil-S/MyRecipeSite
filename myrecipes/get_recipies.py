import logging
import os
import random
import re
import urllib
from time import sleep

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from sqlalchemy import delete, exc, update
from sqlalchemy.ext.declarative import declarative_base

#import sqlite3  <<Need to pip uninstall
from myrecipes import ScrapeAR  # .scrapeAR
from myrecipes import db, whisk_secrets
from myrecipes.models import Recipe, Recipe_Ingredient, Recipe_Instruction

# Configuring logging to output to standard output (console)
logging.basicConfig(level=logging.DEBUG, filename='recipe_import.log', filemode='w', format='%(asctime)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)


def main(option):
  url =  'https://my.whisk.com/recipes'
  email =  whisk_secrets.email
  password =  whisk_secrets.password

  #Selenium config:
  #PATH = "C:\\projects\\chromedriver.exe"
  driver = webdriver.Chrome()

  driver.get(url)
  driver.maximize_window()


  wait = WebDriverWait(driver, 10) # wait up to 10 seconds
  username_field = wait.until(EC.presence_of_element_located((By.NAME, 'username')))

  # enter the email and click continue
  # wait for each character due to issue with every other character being input in to the field
  for char in email:
    username_field.send_keys(char)
    sleep(.1)
  username_field.send_keys(Keys.ENTER)

  #wait 30s unitl password field present
  element = WebDriverWait(driver, 30).until(
    EC.presence_of_element_located((By.ID, "_input-3"))
  )
  inputElement = driver.find_element(By.ID, '_input-3')

  #inputElement = driver.find_element_by_class_name(fieldID)
  
  # wait for each character due to issue with every other character being input in to the field
  #inputElement.send_keys(password)
  for char in password:
    inputElement.send_keys(char)
    sleep(.1)
  inputElement.send_keys(Keys.ENTER)

  sleep(2)
  #navigate to page
  driver.get("https://my.whisk.com/recipe-box")

  x = 4
  print(f'Search will start in {x} seconds')
  while x > 1:
    x -= 1
    sleep(1)
    print(f'{x}')
  print(f'{x-1} seconds left, continuing...')

  #scroll to bottom of cards
  def scroll_to_bottom():
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        print("Scrolling...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
  scroll_to_bottom() #temporarly comment out to avoid extra calls to website

    # >>>>  options: 1-Onlyaddnew, 2-Upsertall, 3-AROnly, BAOnly-4  <<<<

  #get Whisk recipe page URLs
  whisk_urls = []
  new_whisk_urls = []
  card_headers_objs = driver.find_elements(By.XPATH, '//a[ contains(@class, "s191")]')   #  s69-21 s188   
  for card_headers_obj in card_headers_objs:
    card_headers = card_headers_obj.text
    # print(f'HEADERS: {card_headers}')

    whisk_url = card_headers_obj.get_attribute("href")
    whisk_url =  whisk_url.split('?')[0]
    whisk_urls.append(whisk_url)

    if option == 2:
      name = card_headers.split('\n')[0]
      try:
        ingredient_count = card_headers.split('\n')[1]
        if "ingredients" in ingredient_count:
          ingredient_count = ingredient_count.replace('ingredients','')
        else:
          ingredient_count = None
      except:
        ingredient_count = None
      
      try:
        total_time = card_headers.split('\n')[2]
        matches = ['h ', 'h', 'min']
        if any([x in total_time for x in matches]):
          pass
        else:
          total_time = None
      except:
        total_time = None

      #UPSERT INTO recipe 
      recipe = Recipe(name=name, whisk_url=whisk_url, ingredient_count=ingredient_count, total_time=total_time)
      try:
        recipe = db.session.merge(recipe)
        db.session.commit()
        new_whisk_urls.append(whisk_url)
      except exc.IntegrityError:
        db.session.rollback()
        # Handle the case when the whisk_url already exists in the Recipe table
        print(f'{name} already exists.')

      scrape_recipe_pages(driver, whisk_urls, name, total_recipes)

     ### End for loop over cards ###
   
  #del whisk_urls[0:248]             #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
  #provide option to upsert all urls or only add new ones
  if option == 1:
    recipes = Recipe.query.order_by(Recipe.whisk_url.asc()).all()
    new_whisk_urls = list(set(whisk_urls) - set(recipes))
    whisk_urls = new_whisk_urls


  total_recipes = len(whisk_urls)
  print(f'{total_recipes} URLs found ')
  print(f'Option {option}')
  
  #TESTING - limite the amount
  #whisk_urls = whisk_urls[:30]
 

def scrape_recipe_pages(driver, whisk_urls, name, total_recipes):
  source_url_count = 0
  source_urls = []
  recipe_names = []
  sleep = 2
  for whisk_url in whisk_urls:
    if len(whisk_urls) > 5:
      random_sleep = random.uniform(3, 13) #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
      sleep(random_sleep)

    driver.get(whisk_url)
    sleep(2)       
    
    current_recipe = Recipe.query.filter_by(whisk_url=whisk_url).first()
    current_recipe_id = current_recipe.recipe_id if current_recipe else None
    recipe_name = current_recipe.name if name else None
    recipe_names = recipe_names.append(recipe_name)
    #get source URL
    source_url_path = '//a[ @class="s11736 s190 wx-link-dark s12815 s320"]'

    try:
      find_href = driver.find_elements(By.XPATH, source_url_path) 
    except:
      print(f'Could not find source URL for {recipe_name}. Waiting 10 seconds...')
      sleep(5)
      print('5s left...')
      sleep(5)
      find_href = driver.find_elements(By.XPATH, source_url_path) 
    if len(find_href) > 0:
      for source_url in find_href:
        source_url = source_url.get_attribute("href")
        source_url =  source_url.split('?')[0]
        #some recipes do not have an extranal URL. If so, this will return the current URL
        if source_url.startswith('https://my.whisk.com/profile/'):
          source_url = driver.current_url
        
        stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(source_url=source_url)
        db.session.execute(stmt)
        db.session.commit()

        source_urls.append(source_url)

      #Prints progress status
      source_url_count += 1
      print(f'{int((source_url_count/total_recipes)*100)}%. {recipe_name} processing... Remaining source urls obtained: {source_url_count} of {total_recipes} (Remaining: {total_recipes - source_url_count + 1} )')
    else:
      source_urls.append("Not Found")
      print(f'No source URL found for {recipe_name}')
    
    #get cooking time
    try:
      prep_time = None
      cook_time = None
      cook_prep_time = driver.find_element('xpath', '//div[ @class="s191 s1179"]')  #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
      cook_prep_time = cook_prep_time.text
      try:
        if cook_prep_time.split('\n')[0] == 'Prep:':
            prep_time = cook_prep_time.split('\n')[1]
      except:
        pass
      
      try:
        if cook_prep_time.split('\n')[2] == 'Cook:':
            cook_time = cook_prep_time.split('\n')[3]
      except:
        pass
    except:
      pass
      print(f'cook_prep time not found for {recipe_name}')

    ## NEW DB  ##
    stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(prep_time=prep_time, cook_time=cook_time)
    db.session.execute(stmt)
    db.session.commit()

    #get serving count
    try:
      #if provided
      servings_elment = driver.find_element(By.CLASS_NAME, "s11293") #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
      servings = servings_elment.text.split(' ')[0]
    except:
      #when no serving count is provided
      servings = None
      print(f'Servings not found for {recipe_name}')
    
    #conn.execute('''UPDATE recipe SET servings = ? WHERE whisk_url = ?''', (servings, whisk_url))

    #get short URL
    source_url_short = driver.find_element('xpath', '//span[ contains(@class, "s11890")]') #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    #get cuisine
    try:
      cuisine = driver.find_element('xpath', '//a[ contains(@href, "/search/recipes?cuisines")]').text 
    except:
      print(f'No cuisine found for {recipe_name}')

    #UPDATE Recipe
    stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(servings=servings, source_url_short=source_url_short.text, cuisine=cuisine)
    db.session.execute(stmt)
    db.session.commit()
    
    #If recipe image does not already exist, click on recipe image to expand and save to file
    if not os.path.exists (f'myrecipes//static//recipe_images//{current_recipe_id}.jpg'):
      save_image = 1
      image_path = '//img[ contains(@class, "s320")]'  #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
      try: 
        image = driver.find_element("xpath", image_path)            #s68-146 s11706 s12502 s320  
        sleep(2)
        image.click()    
      except:
        sleep(5)
        try:
          image = driver.find_element("xpath", image_path)            #s68-146 s11706 s12502 s320  
          sleep(4)
          image.click()
        except:
          print(f'Could not get recipe image for {recipe_name}')
          save_image = 0
      
      if save_image == 1:  
        
        #open file in write and binary mode
        with open(f'myrecipes//static//recipe_images//{current_recipe_id}.jpg', 'wb') as file:
          sleep(5)
          #get large image to be captured
          large_image_path = '//img[ contains(@class, "s11791")]'
          try:
            large_image = driver.find_element('xpath', large_image_path)  #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
          except:
            print(f'Retrying save of large image in 10s for {recipe_name}')
            sleep(10)
            large_image = driver.find_element('xpath', large_image_path)  #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
          #write file
          try:
            file.write(large_image.screenshot_as_png)
            #close the overlay window by clicking
            large_image.click()
            
            #Update recipe with image file
            stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(image_file=str(current_recipe_id)+'.jpg')
            db.session.execute(stmt)
            db.session.commit()
          except:
            print(f'Failed to save screenshot for {recipe_name}')

    #get ingredients
    #element.scrollIntoView({ alignToTop: "True" });
    ingredient_parents_path = '//a[contains (@class, "s13000")]'  #<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    try:
      first_ingredient = driver.find_element('xpath', ingredient_parents_path ) #class="s11674 wx-link-dark s191 s257 s5731 s251 s12919"
      first_ingredient.location_once_scrolled_into_view

      ingredient_parents = driver.find_elements(By.XPATH, ingredient_parents_path)

      stmt = delete(Recipe_Ingredient).where(Recipe_Ingredient.recipe_id == current_recipe_id)
      db.session.execute(stmt)
      db.session.commit()
      ingredient_number = 0
      for ingredient_parent in ingredient_parents:
        #scroll browser down if 10 ingredients are hit - resolved issue with capturing ingredient image       
        ingredient_number += 1
        if ingredient_number % 10 == 0:
          ingredient_parent.location_once_scrolled_into_view
        
        #get the official raw name and store image 
        ingredient_name = ingredient_parent.get_attribute("href").replace('https://my.whisk.com/ingredients/','')
        if os.path.exists (f'myrecipes//static//ingredient_images//{ingredient_name}.jpg'):
          pass
        else:
          try:
            #identify ingredient image to be captured
            ingredient_image = ingredient_parent.find_element('xpath', './/img[ @class="s68-199 s12863 s12861"]') #<<<<<<<<<<<<<<<<<<<<<<<<<<
            #write file
            with open(f'myrecipes//static//ingredient_images//{ingredient_name}.jpg', 'wb') as file:
              sleep(.5)
              file.write(ingredient_image.screenshot_as_png)
          except:
            ingredient_name == '_unknown'
                
        #get the ingredient, quantity and note from the UI
        ingredient_full = ingredient_parent.find_element("xpath", './/span[ @data-testid="recipe-ingredient"]') 

        name_written = ingredient_full.text.split('\n')[0]
        try:  
          ingredient_note = ingredient_full.text.split('\n')[1]
        except:
          ingredient_note = None

        #INSERT ingredient
        ingredient = Recipe_Ingredient(recipe_id=current_recipe_id, name_written=name_written, note=ingredient_note, name_official=ingredient_name)
        db.session.add(ingredient)
        db.session.commit()
    except:
      print(f'ingredients not found for {recipe_name}')

    update_AR_recipe(current_recipe_id, source_url)
    
    if 'https://www.allrecipes.com/' not in source_url:  
      try:
        instructions = driver.find_elements(By.XPATH, '//span[contains (@class, "s23 s27 s10139")]') #<<<<<<<use the parent to the initial span. Use "Balsamic Benihana sauce will turn any vegetable into a scene-stealer" as an example
        instruction_sequence = 0
        for instruction in instructions:
          instruction_sequence =+ 1
          #INSERT instruction
          instruction_to_db = Recipe_Ingredient(recipe_id=current_recipe_id, type=1, text_contents=instruction.text, sequence=instruction_sequence)
          db.session.add(instruction_to_db)
        db.session.commit()
      except:
        pass
  
  #recipe_names = recipe_names if recipe_names else None
  #total_recipes = total_recipes if total_recipes else 0
  return()

def update_AR_recipe(current_recipe_id, source_url):
    if 'https://www.allrecipes.com/' in source_url:  
      additional_time, all_instructions, notes = ScrapeAR.scrapeAR(source_url)
      stmt = update(Recipe).where(Recipe.recipe_id == current_recipe_id).values(additional_time=additional_time)
      db.session.execute(stmt)
      db.session.commit()

      stmt = delete(Recipe_Instruction).where(Recipe_Instruction.recipe_id == current_recipe_id)
      db.session.execute(stmt)
      db.session.commit()
      
      sequence = 0
      for instruction in all_instructions:
        sequence += 1

        #INSERT INTO recipe_instruction
        instruction_query = Recipe_Instruction(recipe_id=current_recipe_id, text_contents=instruction, type=1, sequence=sequence)
        db.session.add(instruction_query)
        db.session.commit()
      sequence = 0  
      for note in notes:
        sequence += 1
        
        #INSERT INTO recipe_instruction
        note_query = Recipe_Instruction(recipe_id=current_recipe_id, text_contents=note, type=2, sequence=sequence)
        db.session.add(note_query)
        db.session.commit()

def update_BA_recipe(current_recipe_id, source_url):
    
    instructions = Recipe_Instruction.query.filter_by(recipe_id=current_recipe_id).first()

    if 'https://www.bonappetit.com/' in source_url and instructions is None:  
      logger.debug(f'Preparing to scrape url {source_url}, Recipe_id: {current_recipe_id}')

      response = requests.get(source_url)
      if response.status_code == 200:
          html_content = response.text
      else:
          raise Exception(f"Failed to fetch the page. Status code: {response.status_code}")
          logger.warning(f'No inctructions located for url {source_url}, Recipe_id: {current_recipe_id}')


      # 4. Parse the HTML content using BeautifulSoup
      soup = BeautifulSoup(html_content, 'html.parser')

      # 5. Find the div containing the preparation steps using a wildcard match
      instruction_div = soup.select_one('ol[class*="InstructionGroupWrapper"]')

      # Check if the parent div was found
      if instruction_div is None:
          raise Exception("Could not find the preparation steps container.")

      #groups = soup.find_all('div[class*="InstructionGroupHed"]')

      # 6. Extract all the steps within the <ol> tag
      source_instruction_steps = instruction_div.find_all()

      # 7. Iterate over each step and collect the text
      clean_instruction_steps = []
      for seq, step in enumerate(source_instruction_steps, start=1):
          if step.name == 'h3':
              is_group_header = True
          elif step.name == 'p':
              is_group_header = False
          else:
            continue
          
          clean_instruction_steps.append({
              'recipe_id': current_recipe_id,
              'text_contents': step.get_text(),
              'type': 1,
              'sequence': seq,
              'is_group_header': is_group_header
              })

      print(f'Adding instructions for recipe_id: {current_recipe_id}')
      for instruciton_data in clean_instruction_steps:
        instruction = Recipe_Instruction(**instruciton_data)
        db.session.add(instruction)
      db.session.commit()
        # instruciton_data['text_contents']
        #print(i[0:10])

      #get ingerdients
      ingredient_div = soup.select_one('div[class^="List-"]')
      
      # Check if the parent div was found
      if ingredient_div is None:
          raise Exception("Could not find the preparation steps container.")

      # 6. Extract all the steps within the <ol> tag
      ingredient_steps = ingredient_div.find_all()
      print(steps)




  #driver.quit()
#if __name__ == "__main__":
  # stuff only to run when not called via 'import' here
#  main()