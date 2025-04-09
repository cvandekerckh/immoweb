import requests
import random
import sqlite3
import smtplib
from email.mime.text import MIMEText
from bs4 import BeautifulSoup, Comment
import json
import time
import os
from dotenv import load_dotenv
import openai


basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'),override=True)

# Settings
new_house_url = 'https://www.immoweb.be/fr/annonce/maison/a-louer'
url = 'https://www.immoweb.be/fr/recherche/maison-et-appartement/a-louer?countries=BE&maxPrice=1400&minPrice=1100&postalCodes=1300,1325,1340,1342,1348,1435&minBedroomCount=2&hasTerraceOrGarden=true&page=1&orderBy=relevance'
maxpages = 1
destinators = ['corentinvdk@gmail.com', 'flore.vromman@gmail.com']

smtp_host = os.environ.get('MAIL_SERVER')
smtp_port = os.environ.get('MAIL_PORT')
smtp_user = os.environ.get('MAIL_USERNAME')
smtp_pass = os.environ.get('MAIL_PASSWORD')

openai.api_key = os.environ.get('OPENAI_API_KEY')

# Period of relaunch
relaunch_period = 60 # [min]
wait_time_per_request = 1*60 # [sec]

# openai max calls per session
openai_max_calls = 200

# Options
do_email = True
print_console = True

# Messages
messages = [
    "Coucou toi! Mon moi virtuel a trouvé une nouvelle maison pour toi :",
    "Salut les lardons :) j'ai encore trouvé une nouvelle maison : ",
    "Hep hep grand chef! Voici une nouvelle maison qui peut t'intéresser: ",
    "Allo la lune ici la terre. J'ai trouvé une nouvelle maison :",
    "C'est un ami robot qui te parle, et qui te dit qu'il y a une nouvelle maison ici: ",
    "Il pleut des maisons! Une nouvelle vient d'arriver ici: ",
]

# Prompt

# Critères
prompt = """Bonjour ! Je recherche un écrire un mail par rapport à un bien loué trouvé sur un site immobilier.
Voici les informations concernant ce bien (extrait d'un document html) : \n {}"""

criteria = """
Voici les critères qui sont importants pour ma recherche (nice-to-have) : 
- disponible entre juillet 2025 et septembre 2025. Le mieux étant août 2025
- 3 chambres plutôt que deux chambre
- un jardin
- idéalement pas d'étage
- au délà de 100m^2 J'ai reçu la description
- espace de stockage

Voici les critères qui ne sont pas importants pour ma recherche :
- classe énergétique de l'appartement
- accessibilité PMR


En se bassant majoritairement sur mes critères, pourrais-tu me faire une liste des 5 points forts et 5 points faibles de ce bien ? 
Peux-tu me répondre sous le format suivant, visant à être un email : 

Bonjour Flore et Corentin,

(petite phrase sympa et originale pour dire qu'un nouveau bien a été trouvé)

Prix du bien : (indiquer le prix du bien ici)
Lieu : (indiquer ici le lieu du bien)

5 avantages du bien : 
- (avantage 1)
- (avantage 2)
- ...

5 désavantages du bien : 
- (avantage 1)
- (avantage 2)
- ...

Signé : (un nom original pour une intelligence artificielle)
"""

url_link_label = """Lien url du bien : {}"""


def send_email(smtpserver, immoweb_id, location, postal_code, email_content):
    print(f'Sending mail about new property ID {immoweb_id}.')
    immoweb_url = f"{new_house_url}/{location}/{postal_code}/{immoweb_id}"
    email = MIMEText(email_content)
    email['Subject'] = f'Nouvelle maison immoweb: {immoweb_id}'
    email['From'] = smtp_user

    for emailaddress in destinators:
        email['To'] = emailaddress
        try:
            smtpserver.sendmail(smtp_user, emailaddress, email.as_string())
            print(f"Email sent to {emailaddress}.")
        except Exception as e:
            print(f"Failed to send email to {emailaddress}: {e}")

def extract_property_html(immoweb_url):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0"
        }
        response = requests.get(immoweb_url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        content_div = soup.find('div', class_='container container--body')
        if content_div:
            return content_div.prettify()
        else:
            print(f"No matching div found in {immoweb_url}")
            return None
    except Exception as e:
        print(f"Error fetching property page {immoweb_url}: {e}")
        return None


def save_content(content, immoweb_id, extension, folder="saved_properties"):
    try:
        os.makedirs(folder, exist_ok=True)
        filepath = os.path.join(folder, f'property_{immoweb_id}.{extension}')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Saved content to {filepath}")
    except Exception as e:
        print(f"Error saving file for property {immoweb_id}: {e}")


def extract_visible_text(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    # Supprimer les balises inutiles
    for element in soup(['style', 'script', 'noscript', 'meta', 'head']):
        element.decompose()

    # Supprimer les commentaires
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    # Supprimer les éléments cachés par CSS inline
    for element in soup.select('[style*="display:none"], [style*="visibility:hidden"]'):
        element.decompose()

    # Supprimer les classes "hidden" ou similaires
    for element in soup.select('.hidden, .sr-only'):
        element.decompose()

    # Parcourir les templates pour en extraire aussi le texte
    for template in soup.find_all('template'):
        # Remplacer le template par son contenu parsé
        parsed_template = BeautifulSoup(template.decode_contents(), 'html.parser')
        template.insert_after(parsed_template)
        template.decompose()

    # Maintenant, on peut récupérer tout le texte
    text = soup.get_text(separator='\n', strip=True)

    return text


def call_chatGPT(prompt):
    client = openai.OpenAI()
    response = client.responses.create(
        model="gpt-4o",
        input=prompt,
    )
    return response.output_text

openai_calls = 0
while True:
    with sqlite3.connect('ImmowebScraper.db') as db:
        c = db.cursor()
        c.execute('CREATE TABLE IF NOT EXISTS immos (id INTEGER PRIMARY KEY UNIQUE NOT NULL);')
        db.commit()

        c.execute('SELECT COUNT(*) FROM immos;')
        firstRun = c.fetchone()[0] == 0

        smtpserver = None
        if do_email:
            try:
                smtpserver = smtplib.SMTP(smtp_host, smtp_port)
                smtpserver.ehlo()
                smtpserver.starttls()
                smtpserver.login(smtp_user, smtp_pass)
                print("SMTP server connected.")
            except Exception as e:
                print(f"Failed to set up SMTP server: {e}")
                smtpserver = None

        for page in range(1, maxpages + 1):
            print(f'Browsing page {page} ...')
            page_url = url + '&page=' + str(page)
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }

            # step 1 : retrieve general webpage
            soup = BeautifulSoup(requests.get(page_url, headers=headers).content, 'html.parser')
            data_element = soup.find('iw-search')
            if not data_element:
                print("No data element found on the page.")
                continue

            data = json.loads(data_element[':results'])
            for data_item in data:
                immoweb_id = data_item["id"]
                location = data_item["property"]["location"]["locality"].lower()
                postal_code = data_item["property"]["location"]["postalCode"]

                c.execute('SELECT COUNT(*) FROM immos WHERE id=:id;', {'id': immoweb_id})
                if c.fetchone()[0] == 0:
                    c.execute('INSERT INTO immos(id) VALUES (:id);', {'id': immoweb_id})
                    db.commit()

                    # step 2 : retrieve each webpage url
                    immoweb_url = f"{new_house_url}/{location}/{postal_code}/{immoweb_id}"
                    message = f"New property found: ID {immoweb_id}! {immoweb_url}"
                    if print_console:
                        print(message)
                    # step 3 : retrieve each webpage content
                    html_content = extract_property_html(immoweb_url)
                    save_content(html_content, immoweb_id, 'html')
                    clean_text = extract_visible_text(html_content)
                    save_content(clean_text, immoweb_id, 'txt')

                    if do_email and smtpserver:

                        # step 4 : generate message of relevancy for user
                        prompt = prompt.format(clean_text)
                        prompt += criteria.format(immoweb_url)

                        # step 5 : call chatGPT
                        openai_answer = call_chatGPT(prompt)
                        openai_calls += 1
                        openai_answer += url_link_label.format(immoweb_url)

                        send_email(smtpserver, immoweb_id, location, postal_code, openai_answer)
                        if print_console:
                            print(prompt)
                            print(openai_answer)
                        
                        if openai_calls > openai_max_calls:
                            print(f'Went over max open_ai calls ({openai_max_calls})')
                            raise

                    time.sleep(wait_time_per_request)

        if smtpserver:
            smtpserver.quit()
            print("SMTP server closed.")

    time.sleep(relaunch_period * 60)
