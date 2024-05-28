import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
from urllib.request import urlopen
from bs4 import BeautifulSoup as bs
import time
import sys
import numpy as np
import requests
import getpass
import os

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

# Calculate the date for the third last Friday
today = datetime.now()
# Find the most recent Friday
days_to_friday = (today.weekday() - 4) % 7
last_friday = today - timedelta(days=days_to_friday)
# Find the third last Friday
third_last_friday = last_friday - timedelta(weeks=2)
friday_date_str = third_last_friday.strftime("%m/%d/%Y")

# Scraper logic
base_url = "http://envapp.maricopa.gov/EnvironmentalHealth/FoodGrade?"
full_url = f"{base_url}d={friday_date_str}&a=true"

url = urlopen(full_url)
soup_doc = bs(url, "html.parser")
table = soup_doc.find_all("tr")

master_data = []
for row in table[1:]: #skip the first row, it contains headers
    rest_list = row.find_all('td')
    inspection_link = row.find('td', {'class': 'boldTextCenter'}).a['href'] # grab the a tag's href attribute
    list_headers = ['biz', 'address', 'city', 'permit_ID', 'type', 'class', 'inspectionDate', 'inspectionType', 'grade', 'pv', 'cuttingEdge','inspectionLink'] # added link to the column heads
    rest_data = []
    for index, col in enumerate(rest_list):
        rest_data.append(col.text)
    rest_data.append('http://envapp.maricopa.gov' + inspection_link) # appending the base url to the inspection subquery

    rest_dict = dict(zip(list_headers, rest_data))
    master_data.append(rest_dict)

df = pd.DataFrame(master_data)
df['address'] = df['address'].str.strip()
df['address'] = df['address'] + ', ' + df.city + ', ' + 'AZ'

# Limit dataset to only E & D type
df2 = df[(df.type == "E & D  10+ Seating  ") | (df.type == "E & D  0-9 Seating  ")].copy()

# Filter out restaurant chains that are not mom and pop
df3 = df2[~df2.biz.str.contains("Children|School|Food City|7-Eleven|Sheraton Phoenix Airport Hotel|Fitness|Cold Stone|Chipotle Mexican Grill|Papa Johns|Five Guys Burgers|Albertson's|Senior Living|Assisted Living|McDonald's|Church|El Sabroso Hot-Dog|\
                                Cafe|Coffee|Safeway|Edible Arrangements|ATL Wings|Del Taco|Wienerschnitzel|Church|Resort|Club|Whataburger|\
                                Streets|American Legion|Wingstop|Jamba Juice|Marriott|Pizza Patron|Carl's Jr|\
                                Church's Chicken|Canyon|Applebees|Arco|Sonic Drive|Pizza Hut|Raising Canes|Little Caesars|Aldo's|Frys|\
                                Denny's|QuikTrip|Dickey's|AFC Sushi|Jersey Mike's|Snow Fox|Dunkin|Chick-fil-A|Chick-Fil-A|Popeyes\
                                |Domino's|El Pollo Loco|Pilot Travel Center|SnowFox|Peter Piper|Wendy's|Burger King|Fry's|Circle K|Taco Bell|Quiktrip|\
                                Safeway|Little Caesar's|Panda Express|Lucky Lou's|Filibertos|Filiberto's|Bosa Donuts|Starbucks|\
                                Chipotle|Golf|Subway|Outback Steakhouse|Shell|AJ's Fine Foods|McDonalds|Jimmy John|Ice Cream|Market|Inn|Suites|LLC|Deli|Denny's|College|Farms|Farm|\
                                Popeyes|Express|Panera Bread|ARCO|Senior", case=False, regex=True)].copy()

# Number of restaurants inspected this week
ins = df['permit_ID'].count()
print(ins, "restaurants were inspected in the week", )

# Restaurants with 4 priority violations and above
df3['pv'] = df3.pv.astype(int)
df4 = df3[df3['pv'] > 3]

if len(df4) == 0:
    sys.exit("No restaurant had more than 3 priority violations")
else:
    print(f"{len(df4)} restaurants had more than 3 priority violations")

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
    address = row['address']
    lat, lng = geocode_address(address, api_key)
    df4.at[index, 'latitude'] = lat
    df4.at[index, 'longitude'] = lng
    time.sleep(0.1)  # Adjust the delay as needed

df4['pv'] = df4.pv.astype(str)
df4['pv'] = 'Priority violations: ' + df4.pv
df4b = df4[['biz', 'latitude', 'longitude', 'address', 'inspectionDate', 'pv', 'inspectionLink']].copy()
df4b.to_csv('topviolators.csv')

# A rated restaurants
df5 = df3[(df3.grade == "A")]

# Phoenix A-rated restaurants
df5a = df5[df5.city == "Phoenix"]

# Scottsdale A-rated restaurants
df5b = df5[df5.city == "Scottsdale"]

# East Valley
east = ['Apache Junction', 'Chandler', 'Gilbert', 'Mesa', 'Queen Creek', 'Tempe']
df5c = df5[df5.city.isin(east)]

# West Valley
west = ['Goodyear', 'Avondale', 'Buckeye', 'Tolleson', 'Sun City', 'Wickenburg', 'Glendale', 'Surprise']
df5d = df5[df5.city.isin(west)]

# Update the Google Sheets with the dataframes
sheet_top_violators = sheet.worksheet('topViolators')
sheet_phoenix = sheet.worksheet('Phoenix')
sheet_scottsdale = sheet.worksheet('Scottsdale')
sheet_east_valley = sheet.worksheet('eastValley')
sheet_west_valley = sheet.worksheet('westValley')

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




