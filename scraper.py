# All of the necessary imports
from bs4 import BeautifulSoup as bs
import pandas as pd
import json
import time
import io
import os
import numpy as np
import requests
import sys
from datetime import timedelta, datetime
import gspread
from selenium import webdriver
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.os_manager import ChromeType
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from oauth2client.service_account import ServiceAccountCredentials

# Setup Chrome WebDriver with options
chrome_service = Service(ChromeDriverManager(chrome_type=ChromeType.CHROMIUM).install())

chrome_options = Options()
options = [
    "--headless",
    "--disable-gpu",
    "--window-size=1920,1200",
    "--ignore-certificate-errors",
    "--disable-extensions",
    "--no-sandbox",
    "--disable-dev-shm-usage"
]
for option in options:
    chrome_options.add_argument(option)

driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

# Define the scope for Google Sheets API
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# Load credentials from environment variable
credentials_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
creds_dict = json.loads(credentials_json)

# Create credentials and authorize the client sheet
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Get the Google Sheet
sheet = client.open('Restaurant_inspection_database(auto_scraper)')

# Add preferences for Chrome options
prefs = {'safebrowsing.enabled': False}
chrome_options.add_experimental_option('prefs', prefs)

# Navigate to the desired URL
driver.get("https://envapp.maricopa.gov/Report/WeeklyReport")

# Wait for the page to load
time.sleep(11)

# Calculate the date for the third last Friday
today = datetime.now()
days_to_friday = (today.weekday() - 4) % 7
last_friday = today - timedelta(days=days_to_friday)
third_last_friday = last_friday - timedelta(weeks=2)
friday_date_str = third_last_friday.strftime("%m-%d-%Y")

# Input the date into the date field
date_input = driver.find_element(By.ID, 'endDate')
desired_date = friday_date_str
date_input.send_keys(desired_date)

# Handle the reCAPTCHA
recaptcha_iframe = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.XPATH, "//iframe[@title='reCAPTCHA']"))
)
driver.switch_to.frame(recaptcha_iframe)
recaptcha_checkbox = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.recaptcha-checkbox-border"))
)
recaptcha_checkbox.click()
driver.switch_to.default_content()

# Click the "Get Report" button
get_report_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.ID, "reportsubmit"))
)
get_report_button.click()

# Add a delay to ensure the table is loaded
time.sleep(10)

# Parse the table HTML with BeautifulSoup
soup = bs(driver.page_source, 'html.parser')
table = soup.find('table', {'id': 'weekly-report-table'})

# Check if the table is found
if not table:
    print("Table not found!")
    driver.quit()
    sys.exit()

# Extract table headers
headers = [th.text.strip() for th in table.find('thead').find_all('th')]
headers.append('Inspection details')  # Add new column header for links
all_rows = [headers]

# Base URL for the inspection details links
base_url = "https://envapp.maricopa.gov"

# Scrape data from the first page
for tr in table.find('tbody').find_all('tr'):
    # Skip rows with the 'No data available' message
    if 'No data available' in tr.text:
        continue
    
    cells = tr.find_all('td')
    row = [cell.text.strip() for cell in cells]

    # Ensure the row has the correct number of columns before adding the link
    if len(row) == len(headers) - 1:  # The link is an extra column, so -1
        # Extract the href link from the 'Inspection date' column
        inspection_date_cell = tr.find('td', {'class': 'text-center'})
        
        if inspection_date_cell:
            a_tag = inspection_date_cell.find('a')
            
            if not a_tag:
                print(f"No <a> tag found in the 'text-center' cell: {inspection_date_cell}")
                full_link = None
            else:
                inspection_link = a_tag['href']
                full_link = base_url + inspection_link  # Construct full URL
            
            # Append the full link to the row
            row.append(full_link)
        else:
            print(f"No 'text-center' cell found in this row: {tr}")
            row.append(None)

        all_rows.append(row)

# Pagination Handling
while True:
    try:
        # Find the pagination container
        pagination = driver.find_element(By.CLASS_NAME, 'dataTables_paginate')
        next_page_button = pagination.find_element(By.ID, 'weekly-report-table_next')

        # Check if the 'Next' button is disabled
        if 'disabled' in next_page_button.get_attribute('class'):
            print("Reached the last page.")
            break

        # Scroll the next page button into view and click
        driver.execute_script("arguments[0].scrollIntoView();", next_page_button)

        # Click the next page button
        attempts = 0
        while attempts < 3:
            try:
                next_page_button.click()
                break
            except ElementClickInterceptedException:
                time.sleep(1)
                attempts += 1

        # Wait for the table to reload
        time.sleep(2)

        # Parse the new page's HTML with BeautifulSoup
        soup = bs(driver.page_source, 'html.parser')
        table = soup.find('table', {'id': 'weekly-report-table'})

        # Scrape data from the current page
        for tr in table.find('tbody').find_all('tr'):
            # Skip rows with the 'No data available' message
            if 'No data available' in tr.text:
                continue

            cells = tr.find_all('td')
            row = [cell.text.strip() for cell in cells]

            # Ensure the row has the correct number of columns before adding the link
            if len(row) == len(headers) - 1:
                inspection_date_cell = tr.find('td', {'class': 'text-center'})
                
                if inspection_date_cell:
                    a_tag = inspection_date_cell.find('a')
                    
                    if not a_tag:
                        print(f"No <a> tag found in the 'text-center' cell: {inspection_date_cell}")
                        full_link = None
                    else:
                        inspection_link = a_tag['href']
                        full_link = base_url + inspection_link  # Construct full URL
                    
                    # Append the full link to the row
                    row.append(full_link)
                else:
                    print(f"No 'text-center' cell found in this row: {tr}")
                    row.append(None)

                all_rows.append(row)
        
    except Exception as e:
        print(f"Finished scraping. Last page reached or an error occurred: {e}")
        break

# Create a DataFrame from the scraped data
df = pd.DataFrame(all_rows[1:], columns=all_rows[0])
print(len(df))

# Quit the driver after the scraping and updating is complete
driver.quit()

# Data cleaning and processing
df['Address'] = df['Address'].str.strip() + ', ' + df['City'] + ', AZ'

# Limit dataset to only 'Eating & Drinking' permit type
df2 = df[df['Permit Type'] == 'Eating & Drinking']

# Filter out restaurant chains that are not "mom and pop" establishments
df3 = df2[~df2['Business Name'].str.contains(
    "Target|AMC Threatres|Arby's|Walmart|Wal-Mart|Hilton|Kyoto|Waffle House|Barro's Pizza|Clinic|Living Center|Hospice|Children|School|Food City|7-Eleven|Sheraton Phoenix Airport Hotel|Fitness|Cold Stone|Chipotle Mexican Grill|Papa Johns|Five Guys Burgers|Albertson's|Senior Living|Assisted Living|McDonald's|Church|El Sabroso Hot-Dog|\
                                Cafe|Coffee|Safeway|Edible Arrangements|ATL Wings|Del Taco|Wienerschnitzel|Church|Resort|Club|Whataburger|\
                                Streets|American Legion|Wingstop|Jamba Juice|Marriott|Pizza Patron|Carl's Jr|\
                                Church's Chicken|Canyon|Applebees|Arco|Sonic Drive|Pizza Hut|Raising Canes|Little Caesars|Aldo's|Frys|\
                                Denny's|QuikTrip|Dickey's|AFC Sushi|Jersey Mike's|Snow Fox|Dunkin|Chick-fil-A|Chick-Fil-A|Popeyes\
                                |Domino's|El Pollo Loco|Pilot Travel Center|SnowFox|Peter Piper|Wendy's|Burger King|Fry's|Circle K|Taco Bell|Quiktrip|\
                                Safeway|Little Caesar's|Panda Express|Lucky Lou's|Filibertos|Filiberto's|Bosa Donuts|Starbucks|\
                                Chipotle|Golf|Subway|Outback Steakhouse|Shell|AJ's Fine Foods|McDonalds|Jimmy John|Ice Cream|Market|Inn|Suites|LLC|Deli|Denny's|College|Farms|Farm|\
                                Popeyes|Express|Panera Bread|ARCO|Senior", case=False, regex=True)].copy()

# Number of restaurants inspected this week
ins = df['Permit ID'].count()
summary_data = []
summary_data.append([f"{ins} restaurants were inspected in the week of {friday_date_str}"])

# Restaurants with 4 priority violations and above
df3['Priority Violation'] = df3['Priority Violation'].astype(int)
df4 = df3[df3['Priority Violation'] > 3].copy()

if len(df4) == 0:
    summary_data.append([f"No restaurant had more than 3 priority violations of {friday_date_str}"])
    sheet_summary = sheet.worksheet('Summary')
    sheet_summary.update('A1', summary_data)
    sys.exit()
else:
    summary_data.append([f"{len(df4)} restaurants had more than 3 priority violations"])

# Use the environment variable for the API key
api_key = os.getenv('GOOGLE_MAPS_API_KEY')

# Geocoding logic remains the same
base_url = 'https://maps.googleapis.com/maps/api/geocode/json?'

def geocode_address(address, api_key):
    params = {
        'key': api_key,
        'address': address
    }
    response = requests.get(base_url, params=params).json()

    if response['status'] == 'OK' and len(response['results']) > 0:
        geometry = response['results'][0]['geometry']
        lat = geometry['location']['lat']
        lng = geometry['location']['lng']
        return lat, lng
    else:
        print(f"Geocoding failed for address: {address}")
        return None, None

for index, row in df4.iterrows():
    address = row['Address']
    lat, lng = geocode_address(address, api_key)
    df4.at[index, 'latitude'] = lat
    df4.at[index, 'longitude'] = lng
    time.sleep(0.1)  # Adjust the delay as needed

df4['Priority Violation'] = df4['Priority Violation'].astype(str)
df4['Priority Violation'] = 'Priority violations: ' + df4['Priority Violation']
df4b = df4[['Business Name', 'latitude', 'longitude', 'Address', 'Inspection date', 'Priority Violation']].copy()

# A-rated restaurants
df5 = df3[df3.Grade == "A"]
summary_data.append([f"{len(df5)} restaurants were rated 'A'"])

# Separate A-rated restaurants by region
df5a = df5[df5.City == "Phoenix"]
df5b = df5[df5.City == "Scottsdale"]
east = ['Apache Junction', 'Chandler', 'Gilbert', 'Mesa', 'Queen Creek', 'Tempe']
df5c = df5[df5.City.isin(east)]
west = ['Goodyear', 'Avondale', 'Buckeye', 'Tolleson', 'Sun City', 'Wickenburg', 'Glendale', 'Surprise']
df5d = df5[df5.City.isin(west)]

# Update the Google Sheets with the dataframes
sheet_top_violators = sheet.worksheet('topViolators')
sheet_phoenix = sheet.worksheet('Phoenix')
sheet_scottsdale = sheet.worksheet('Scottsdale')
sheet_east_valley = sheet.worksheet('eastValley')
sheet_west_valley = sheet.worksheet('westValley')
sheet_summary = sheet.worksheet('Summary')

# Convert DataFrame to list of lists and update Google Sheets
data_list_4b = df4b.values.tolist()
data_list_5a = df5a.values.tolist()
data_list_5b = df5b.values.tolist()
data_list_5c = df5c.values.tolist()
data_list_5d = df5d.values.tolist()

sheet_top_violators.update('A1', [df4b.columns.values.tolist()] + data_list_4b)
sheet_phoenix.update('A1', [df5a.columns.values.tolist()] + data_list_5a)
sheet_scottsdale.update('A1', [df5b.columns.values.tolist()] + data_list_5b)
sheet_east_valley.update('A1', [df5c.columns.values.tolist()] + data_list_5c)
sheet_west_valley.update('A1', [df5d.columns.values.tolist()] + data_list_5d)
sheet_summary.update('A1', summary_data)
