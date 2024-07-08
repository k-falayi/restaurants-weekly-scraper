import pandas as pd
from bs4 import BeautifulSoup as bs
import time
import sys
import json
import os
import requests
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, TimeoutException
from oauth2client.service_account import ServiceAccountCredentials
import gspread
from webdriver_manager.chrome import ChromeDriverManager

# Define the scope
scope = ["https://spreadsheets.google.com/feeds", 'https://www.googleapis.com/auth/spreadsheets',
         "https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]

# Load credentials from environment variable
credentials_json = os.environ.get('GOOGLE_SHEETS_CREDENTIALS')
creds_dict = json.loads(credentials_json)

# Add your service account file
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

# Authorize the clientsheet
client = gspread.authorize(creds)

# Get the Google Sheet
sheet = client.open('Restaurant_inspection_database(auto_scraper)')

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("window-size=1400,800")
chrome_options.add_argument("--headless")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--remote-debugging-port=9222")

# Initialize the WebDriver with options
driver_path = ChromeDriverManager().install()
driver = webdriver.Chrome(executable_path=driver_path, options=chrome_options)

driver.get("https://envapp.maricopa.gov/Report/WeeklyReport")

# Calculate the date for the third last Friday
today = datetime.now()
# Find the most recent Friday
days_to_friday = (today.weekday() - 4) % 7
last_friday = today - timedelta(days=days_to_friday)
# Find the third last Friday
third_last_friday = last_friday - timedelta(weeks=2)
friday_date_str = third_last_friday.strftime("%m-%d-%Y")

# Enter the desired date
date_input = driver.find_element(By.ID, 'endDate')
desired_date = friday_date_str
date_input.send_keys(desired_date)

# Wait for the reCAPTCHA iframe to be present
recaptcha_iframe = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.XPATH, "//iframe[@title='reCAPTCHA']"))
)

# Switch to the reCAPTCHA iframe
driver.switch_to.frame(recaptcha_iframe)

# Wait for the reCAPTCHA checkbox to be clickable
recaptcha_checkbox = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.CSS_SELECTOR, "div.recaptcha-checkbox-border"))
)

# Click the reCAPTCHA checkbox
recaptcha_checkbox.click()

# Switch back to the default content
driver.switch_to.default_content()

# Wait for the "Get Report" button to be clickable
get_report_button = WebDriverWait(driver, 10).until(
    EC.element_to_be_clickable((By.ID, "reportsubmit"))
)

# Click the "Get Report" button
get_report_button.click()

# Add a delay to see the result
time.sleep(9)

# Wait for the table to be present
table = WebDriverWait(driver, 10).until(
    EC.presence_of_element_located((By.ID, "weekly-report-table"))
)

all_rows = []
# Parse the table HTML with BeautifulSoup
soup = bs(driver.page_source, 'html.parser')
table = soup.find('table', {'id': 'weekly-report-table'})

# Extract table headers
headers = []
for th in table.find('thead').find_all('th'):
    headers.append(th.text.strip())
all_rows.append(headers)

# Extract data from the first page
for tr in table.find('tbody').find_all('tr'):
    cells = tr.find_all('td')
    row = [cell.text.strip() for cell in cells]
    all_rows.append(row)

# Iterate over each page
while True:
    try:
        # Find the pagination container and the active page button
        pagination = driver.find_element(By.CLASS_NAME, 'dataTables_paginate')
        active_page = pagination.find_element(By.CLASS_NAME, 'active')
        
        # Find the next page button
        next_page_button = active_page.find_element(By.XPATH, 'following-sibling::li/a')
        
        # Scroll the next page button into view and click
        driver.execute_script("arguments[0].scrollIntoView();", next_page_button)
        
        # Attempt to click the next page button
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
        
        # Use BeautifulSoup to parse the page source
        soup = bs(driver.page_source, 'html.parser')
        table = soup.find('table', {'id': 'weekly-report-table'})
        
        # Extract data from the current page
        for tr in table.find('tbody').find_all('tr'):
            cells = tr.find_all('td')
            row = [cell.text.strip() for cell in cells]
            all_rows.append(row)
    except Exception as e:
        print(f"Finished scraping. Last page reached or an error occurred: {e}")
        break

# Create a DataFrame
df = pd.DataFrame(all_rows[1:], columns=all_rows[0])

df['Address'] = df['Address'].str.strip()
df['Address'] = df['Address'] + ', ' + df.City + ', ' + 'AZ'

# Limit dataset to only E & D type
df2 = df[df['Permit Type'] == 'Eating & Drinking']

# Filter out restaurant chains that are not mom and pop
df3 = df2[~df2['Business Name'].str.contains("Children|School|Food City|7-Eleven|Sheraton Phoenix Airport Hotel|Fitness|Cold Stone|Chipotle Mexican Grill|Papa Johns|Five Guys Burgers|Albertson's|Senior Living|Assisted Living|McDonald's|Church|El Sabroso Hot-Dog|\
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

# Rest of your geocoding logic remains the same
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

# A rated restaurants
df5 = df3[(df3.Grade == "A")]
summary_data.append([f"{len(df5)} restaurants were rated 'A'"])

# Phoenix A-rated restaurants
df5a = df5[df5.City == "Phoenix"]

# Scottsdale A-rated restaurants
df5b = df5[df5.City == "Scottsdale"]

# East Valley
east = ['Apache Junction', 'Chandler', 'Gilbert', 'Mesa', 'Queen Creek', 'Tempe']
df5c = df5[df5.City.isin(east)]

# West Valley
west = ['Goodyear', 'Avondale', 'Buckeye', 'Tolleson', 'Sun City', 'Wickenburg', 'Glendale', 'Surprise']
df5d = df5[df5.City.isin(west)]

# Update the Google Sheets with the dataframes
sheet_top_violators = sheet.worksheet('topViolators')
sheet_phoenix = sheet.worksheet('Phoenix')
sheet_scottsdale = sheet.worksheet('Scottsdale')
sheet_east_valley = sheet.worksheet('eastValley')
sheet_west_valley = sheet.worksheet('westValley')
sheet_summary = sheet.worksheet('Summary')

# Convert DataFrame to list of lists
data_list_4b = df4b.values.tolist()
data_list_5a = df5a.values.tolist()
data_list_5b = df5b.values.tolist()
data_list_5c = df5c.values.tolist()
data_list_5d = df5d.values.tolist()

# Update the Google Sheets
sheet_top_violators.update('A1', [df4b.columns.values.tolist()] + data_list_4b)
sheet_phoenix.update('A1', [df5a.columns.values.tolist()] + data_list_5a)
sheet_scottsdale.update('A1', [df5b.columns.values.tolist()] + data_list_5b)
sheet_east_valley.update('A1', [df5c.columns.values.tolist()] + data_list_5c)
sheet_west_valley.update('A1', [df5d.columns.values.tolist()] + data_list_5d)
sheet_summary.update('A1', summary_data)
