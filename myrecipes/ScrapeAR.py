from selenium import webdriver
from selenium.webdriver.common.by import By
from time import sleep


#url =  'https://www.allrecipes.com/recipe/213238/indian-fish-curry/'

#Selenium config:
PATH = "C:\\projects\\chromedriver.exe"
driver = webdriver.Chrome(PATH)

def scrapeAR(url):
    
    driver.get(url)
    sleep(1)
    instrunction_group = driver.find_element('xpath', '//ol[ @class="comp mntl-sc-block-group--OL mntl-sc-block mntl-sc-block-startgroup"]')

    all_instructions = []
    instructions = instrunction_group.find_elements(By.XPATH, './/p[ @class="comp mntl-sc-block mntl-sc-block-html"]')
    for instruction in instructions:
        all_instructions.append(instruction.text)

    #Get notes
    all_paragraphs = []
    paragraphs = driver.find_elements(By.XPATH, '//p[ @class="comp mntl-sc-block mntl-sc-block-html"]')
    for paragraph in paragraphs:
        if paragraph.text != (all_paragraphs or [None])[-1]: 
            all_paragraphs.append(paragraph.text)

    notes = list(set(all_paragraphs) - set(all_instructions) )
    
    #driver.quit()
    return all_instructions, notes