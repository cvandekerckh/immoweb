#!/usr/bin/python3
# Usage:
# - Fill in the settings, then run with `python3 ImmowebScraper.py`.
# - First run won't send any mails (or you'd get dozens at once).
# Requirements:
# - python3
# - selenium
# - phantomjs

import requests
import random
import sqlite3
import smtplib
from email.mime.text import MIMEText
from bs4 import BeautifulSoup
import json
import time
import os
from dotenv import load_dotenv


basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# settings
new_house_url = 'https://www.immoweb.be/fr/annonce/maison/a-louer'  # base URL (either renting or buying mode)
url = 'https://www.immoweb.be/fr/recherche/maison/a-louer?countries=BE'  # add your exact search URL here
maxpages = 2
destinators = ['XXX@gmail.com'] # sending to
smtp_host = os.environ.get('MAIL_SERVER')
smtp_port = os.environ.get('MAIL_PORT')
#smtp_mail = 'notarealemail@gmail.com'
smtp_user = os.environ.get('MAIL_USERNAME')
smtp_pass = os.environ.get('MAIL_PASSWORD')

# messages
messages = [
    "Coucou toi! Mon moi virtuel a trouvé une nouvelle maison pour toi :",
    "Salut les lardons :) j'ai encore trouvé une nouvelle maison : ",
    "Hep hep grand chef! Voici une nouvelle maison qui peut t'intéresser: ",
    "Allo la lune ici la terre. J'ai trouvé une nouvelle maison :",
    "C'est un ami robot qui te parle, et qui te dit qu'il y a une nouvelle maison ici: ",
    "Il pleut des maisons! Une nouvelle vient d'arriver ici: ",
]


# prep
while(True):
    # connect to db
    db = sqlite3.connect('ImmowebScraper.db')
    c = db.cursor()

    smtpserver = smtplib.SMTP(smtp_host, smtp_port)
    smtpserver.ehlo()
    smtpserver.starttls()
    smtpserver.login(smtp_user, smtp_pass)

    # create the immos table
    c.execute('CREATE TABLE IF NOT EXISTS immos (id INTEGER PRIMARY KEY UNIQUE NOT NULL);')
    db.commit()

    # if there are no id's yet, this is the first run
    c.execute('SELECT COUNT(*) FROM immos;')
    firstRun = c.fetchone()[0] == 0

    # zhu li, do the thing
    for page in range(1,maxpages+1):
        print('Browsing page {} ...'.format(page))
        page_url = url + '&page=' + str(page)
        soup = BeautifulSoup(requests.get(page_url).content, 'html.parser')
        data = json.loads( soup.find('iw-search')[':results'] )
        for data_item in data:
            immoweb_id = data_item["id"]
            location = data_item["property"]["location"]["locality"].lower()
            postal_code = data_item["property"]["location"]["postalCode"]
            c.execute('SELECT COUNT(*) FROM immos WHERE id=:id;', {'id':immoweb_id})
            if c.fetchone()[0] == 0:
                print('New property found: ID {}! Storing in db.'.format(immoweb_id))
                c.execute('INSERT INTO immos(id) VALUES (:id);', {'id':immoweb_id})
                db.commit()
                if not firstRun:
                    print('Sending mail about new property ID {}.'.format(immoweb_id))
                    immoweb_url = f"{new_house_url}/{location}/{postal_code}/{immoweb_id}"
                    random_message = random.choice(messages)
                    email = MIMEText(random_message + immoweb_url)
                    email['Subject'] = 'Nouvelle maison immoweb: {}'.format(immoweb_id)
                    email['From'] = smtp_user
                    for emailaddress in destinators:
                        email['To'] = emailaddress
                        smtpserver.sendmail(smtp_user,emailaddress,email.as_string())
                    print(email)
                    time.sleep(5*60) # avoid spamming in case of a bug

    smtpserver.quit()
    db.close()

    time.sleep(1*60*60)
