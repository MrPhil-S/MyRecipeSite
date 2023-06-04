from myrecipes import db
from myrecipes.models import Recipe, Recipe_Ingredient, Recipe_Instruction

from sqlalchemy import delete, exc
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import update

import os
import re
import random
import urllib
#import sqlite3  <<Need to pip uninstall
from myrecipes import whisk_secrets
from myrecipes import ScrapeAR  #.scrapeAR

from time import sleep
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

def main():
  url =  'https://my.whisk.com/recipes'
  email =  whisk_secrets.email
  password =  whisk_secrets.password

  #Selenium config:
  PATH = "C:\\projects\\chromedriver.exe"
  driver = webdriver.Chrome(PATH)

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
  print(f'{x} seconds left, continuing...')

  #scroll to bottom of cards
  def scroll_to_bottom():
    last_height = driver.execute_script("return document.body.scrollHeight")
    while True:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        sleep(2)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
  scroll_to_bottom() #temporarly commented out to avoid extra calls to website

  #get Whisk recipe page URLs
  whisk_urls = []
  card_headers_objs = driver.find_elements(By.XPATH, '//a[ contains(@class, "s188")]')   #  s69-21 s188   
  for card_headers_obj in card_headers_objs:
    card_headers = card_headers_obj.text
    # print(f'HEADERS: {card_headers}')

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

    whisk_url = card_headers_obj.get_attribute("href")
    whisk_url =  whisk_url.split('?')[0]
    whisk_urls.append(whisk_url)

    #UPSERT INTO recipe 
    recipe = Recipe(name=name, whisk_url=whisk_url, ingredient_count=ingredient_count, total_time=total_time)
    try:
      recipe = db.session.merge(recipe)
      db.session.commit()
    except exc.IntegrityError:
      db.session.rollback()
      # Handle the case when the whisk_url already exists in the Recipe table
      print(f'{whisk_url} already exists.')

    #######

    
  total_recipes = len(whisk_urls)
  print(f'{total_recipes} URLs found ')
  #TESTING - limite the amount
  #whisk_urls = whisk_urls[:30]

  ####for each Whisk page, navigate within and scrape
  source_url_count = 0
  source_urls = []
  for whisk_url in whisk_urls:
    driver.get(whisk_url)
    random_sleep = random.uniform(1.5, 3)
    sleep(random_sleep)
    
    #get source URL
    find_href = driver.find_elements(By.XPATH, '//a[ contains(@class, "s320")]') #class="s11674 s190 wx-link-dark s12746 s320" 
    if len(find_href) > 0:
      for source_url in find_href:
        source_url = source_url.get_attribute("href")
        source_url =  source_url.split('?')[0]
        #some recipes do not have an extranal URL. If so, this will return the current URL
        if source_url.startswith('https://my.whisk.com/profile/'):
          source_url = driver.current_url
        
        #conn.execute('''UPDATE recipe SET source_url = ? WHERE whisk_url = ?''', (source_url, whisk_url))
        #conn.commit()
        

        ## NEW DB  ##
        #recipe.source_url = source_url
        #db.session.commit()

        stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(source_url=source_url)
        db.session.execute(stmt)
        db.session.commit()

        #######


        source_urls.append(source_url)

      

      #Prints progress status
      source_url_count += 1
      print(f'{int((source_url_count/total_recipes)*100)}%. {whisk_url} completed. (Remaining source urls obtained: {source_url_count} of {total_recipes} (Remaining: {total_recipes - source_url_count + 1} )))')
    else:
      source_urls.append("Not Found")
      print(f'No source URL found for {whisk_url}')
    
    #get cooking time
    cook_prep_times = driver.find_elements(By.XPATH, '//div[ @class="s191 s1179"]')  #class="s191 s1179"
    try:
      for cook_prep_time in cook_prep_times:
        cook_prep_time = cook_prep_time.text
        if cook_prep_time.split('\n')[0] == 'Prep:':
            prep_time = cook_prep_time.split('\n')[1]
        else:
            prep_time = -1
        if cook_prep_time.split('\n')[2] == 'Cook:':
            cook_time = cook_prep_time.split('\n')[3]
        else:
            cook_time = -1
        
      ## NEW DB  ##
      stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(prep_time=prep_time, cook_time=cook_time)
      db.session.execute(stmt)
      db.session.commit()
    except:
      print(f'cook_prep_time failed for {whisk_url}')
      

    #get serving count
    try:
      #if provided
      servings_elment = driver.find_element(By.CLASS_NAME, "s11297") #old: s11293
      servings = servings_elment.text.split(' ')[0]
    except:
      #when no serving count is provided
      servings = None
    
    #conn.execute('''UPDATE recipe SET servings = ? WHERE whisk_url = ?''', (servings, whisk_url))

    #get short URL
    source_url_short = driver.find_element('xpath', '//span[ contains(@class, "s11799")]') #s28 s30 s31 s11799
    
    ##conn.execute('''UPDATE recipe SET servings = ?, source_url_short = ? WHERE whisk_url = ?''', (servings, source_url_short.text, whisk_url))

    ## NEW DB  ##
    stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(servings=servings, source_url_short=source_url_short.text)
    db.session.execute(stmt)
    db.session.commit()

    current_recipe = Recipe.query.filter_by(whisk_url=whisk_url).first()
    current_recipe_id = current_recipe.recipe_id if current_recipe else None

    #If recipe image does not already exist, click on recipe image to expand and save to file
    if not os.path.exists (f'myrecipes//static//recipe_images//{current_recipe_id}.jpg'):
      image = driver.find_element("xpath", '//img[ contains(@class, "s320")]')            #s68-146 s11706 s12502 s320
      sleep(2)
      image.click()    
      sleep(5)
      #open file in write and binary mode
      with open(f'myrecipes//static//recipe_images//{current_recipe_id}.jpg', 'wb') as file:

        #get large image to be captured
        large_image = driver.find_element('xpath', '//img[ contains(@class, "s11744")]')  #class="s68-148 s11744"
        #write file
        file.write(large_image.screenshot_as_png)
      #close the overlay window by clicking
      large_image.click()
      #Update recipe with image file
      stmt = update(Recipe).where(Recipe.whisk_url == whisk_url).values(image_file=str(current_recipe_id)+'.jpg')
      db.session.execute(stmt)
      db.session.commit()

    #get ingredients
    #element.scrollIntoView({ alignToTop: "True" });
    first_ingredient = driver.find_element('xpath', '//a[contains (@class, "s12919")]') #class="s11674 wx-link-dark s191 s257 s5731 s251 s12919"
    first_ingredient.location_once_scrolled_into_view

    ingredient_parents = driver.find_elements(By.XPATH, '//a[contains (@class, "s12919")]')

    stmt = delete(Recipe_Ingredient).where(Recipe_Ingredient.recipe_id == current_recipe_id)
    db.session.execute(stmt)
    db.session.commit()

    for ingredient_parent in ingredient_parents:
        #get the official raw name and store image 
        #sleep(.5)
        ingredient_name = ingredient_parent.get_attribute("href").replace('https://my.whisk.com/ingredients/','')
        if os.path.exists (f'myrecipes//static//ingredient_images//{ingredient_name}.jpg'):
          pass
        else:
          try:
            #identify ingredient image to be captured
            ingredient_image = ingredient_parent.find_element('xpath', './/img[ contains(@class, "s12806")]') #class="s68-145 s12808 s12806"
            #write file
            with open(f'myrecipes//static//ingredient_images//{ingredient_name}.jpg', 'wb') as file:
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

        update_AR_recipes(current_recipe_id, source_url)
  return(whisk_urls)


def update_AR_recipes(current_recipe_id, source_url):
    if 'https://www.allrecipes.com/' in source_url:  
      all_instructions, notes = ScrapeAR.scrapeAR(source_url)
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


  #driver.quit()
if __name__ == "__main__":
  # stuff only to run when not called via 'import' here
  main()