from time import sleep

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

PATH = r""
service = Service()
options = webdriver.ChromeOptions()

driver = webdriver.Chrome(service=service, options=options)
# Selenium Manager is now fully included with selenium 4.10.0
#from selenium.webdriver.chrome.service import Service  # Selenium Manager was added in selenium 4.10.0

#service = Service()
#options = webdriver.ChromeOptions()
#driver = webdriver.Chrome(service=service, options=options)


#driver = webdriver.Chrome()  # Optional argument, if not specified will search path.


def scrapeAR(url):
    
    driver.get(url)
    sleep(1)

    recipe_details = driver.find_elements(By.XPATH, '//div[ @class="mntl-recipe-details__item"]')
    additional_time = None
    for recipe_detail in recipe_details:
        recipe_detail = recipe_detail.text
        if 'Additional Time' in recipe_detail:
            additional_time = recipe_detail.split('\n')[1]

    instrunction_group = driver.find_element('xpath', '//ol[ @class="comp mntl-sc-block-group--OL mntl-sc-block mntl-sc-block-startgroup"]')

                     #    driver.find_element('xpath', '//ol[ @class="comp mntl-sc-block-group--OL mntl-sc-block mntl-sc-block-startgroup"]/following::p[@class="comp mntl-sc-block mntl-sc-block-html"]')

    all_instructions = []
    instructions = instrunction_group.find_elements(By.XPATH, './/p[ @class="comp mntl-sc-block mntl-sc-block-html"]')
    for instruction in instructions:
        all_instructions.append(instruction.text)

    #Get notes
    all_paragraphs = []
    paragraphs = driver.find_elements(By.XPATH, '//p[ @class="comp mntl-sc-block mntl-sc-block-html"]')
    for paragraph in paragraphs:
        if paragraph.text != (all_paragraphs or [None])[-1]: 
            if paragraph.text not in all_instructions: 
                all_paragraphs.append(paragraph.text)
    notes = all_paragraphs
    #driver.quit()
    #print(url)
    #print(driver.find_element('xpath', '//div[ @class="comp mntl-recipe-intro__content mntl-sc-page mntl-block"]').text)


    return additional_time, all_instructions, notes