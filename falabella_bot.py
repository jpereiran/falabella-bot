import os
import time
import re
import requests
import urllib
import json as js
import dialogflow_v2 as dialogflow
from bs4 import BeautifulSoup
from slackclient import SlackClient
from google.protobuf.json_format import MessageToJson

#Google Credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"]="Amelia.json"
# instantiate Slack client
slack_client = SlackClient('your-slack-key')
# starterbot's user ID in Slack: value is assigned after the bot starts up
starterbot_id = None
#Dialogflow project id
dialogflow_id = 'your-dialogflow-project-id'

# constants
RTM_READ_DELAY = 1 # 1 second delay between reading from RTM
MENTION_REGEX = "^<@(|[WU].+?)>(.*)"

SAGA_COLORS = {"amarillo":"N-2588","azul":"N-2589","azul claro":"N-258a","beige":"N-258b","blanco":"N-258c","burdeo":"N-258d","café":"N-258e","crema":"N-258f",
			   "fucsia":"N-258g","gris":"N-258h","morado":"N-258i","naranja":"N-258j","negro":"N-258k","rojo":"N-258l","rosado":"N-258m","verde":"N-258n"}


#send a input text to dialogflow and retrieve the intent and response
def detect_intent_text(project_id, session_id, text, language_code):
	session_client = dialogflow.SessionsClient()
	session = session_client.session_path(project_id, session_id)
	text_input = dialogflow.types.TextInput(text=text, language_code=language_code)
	query_input = dialogflow.types.QueryInput(text=text_input)
	response = session_client.detect_intent(session=session, query_input=query_input)

	print('Detected intent: {} (confidence: {})'.format(response.query_result.intent.display_name,response.query_result.intent_detection_confidence))
	return response.query_result.intent.display_name, response.query_result.fulfillment_text, response.query_result.parameters

#parse the messages from the slack channel
def parse_bot_commands(slack_events):
	for event in slack_events:
		if event["type"] == "message" and not "subtype" in event:
			user_id, message = parse_direct_mention(event["text"])
			if user_id == starterbot_id:
				user = slack_client.api_call(method="users.info",user=event["user"])
				return message, event["channel"], user["user"]["profile"]["display_name"], user["user"]["id"]
	return None, None, None, None

#detect a direct message to the bot
def parse_direct_mention(message_text):
	matches = re.search(MENTION_REGEX, message_text)
	return (matches.group(1), matches.group(2).strip()) if matches else (None, None)

#function to do a filter on the search by color
def get_saga_color_filter(saga_color, descripcion, original_color):
	if saga_color != '':
		color_filter = SAGA_COLORS[saga_color]
		descripcion = urllib.parse.quote(descripcion.replace(original_color,"").rstrip(), encoding=' Windows-1252')
		url = 'https://www.falabella.com.pe/falabella-pe/search/'+ color_filter + '?Ntt=' + descripcion
	else:
		descripcion = urllib.parse.quote(descripcion, encoding=' Windows-1252')
		url = "https://www.falabella.com.pe/falabella-pe/search/?Ntt=" + descripcion
	print(url)
	return url

#handle a message and process it
def handle_command(command, channel, user, user_id):
	intent, response, parameters  = detect_intent_text(dialogflow_id, user_id, command,'es')
	attachments = []

	#look for sales
	if intent == 'amelia.user.sales':
		web = "https://www.falabella.com.pe/static/RDF/site/home/promotedcategories/html/after-hero.json"
		json = requests.get(web).json()
		for j in json:
			url = j['url']
			img = j['image']
			imagen= 'https://falabella.scene7.com/is/image/FalabellaPE/' + img + "?wid=500"
			split = url.split('category/')
			if len(split) > 1:
				soup = BeautifulSoup(requests.get(url).text, 'html.parser')
				cat = soup.select('title')[0].text.replace(' - Falabella.com','')
				attachments.append({"color": "#28efb0",	"title": "CAT: " + cat, "thumb_url": imagen,
				"actions": [
				{"type": "button", "text": "Promociones", "url": url, "style": "default",},
				{"type": "button", "text": "Imagen", "url": 'https://falabella.scene7.com/is/image/FalabellaPE/' + img, "style": "default",}
				]})

	#look for sales by category
	elif intent == 'amelia.user.sales.categories' or intent == 'amelia.user.sales.category':
		busqueda = ''
		if command.find('en ') != -1:
			busqueda = command.split('en ',1)[1].replace('?','')
		elif command.find('de ') != -1:
			busqueda = command.split('de ',1)[1].replace('?','')
		else:
			response = 'No entiendo que debo buscar, por favor seguir un patrón similar al siguiente: "descuentos de ropa de cama"'
		print(busqueda)
		if busqueda != '':
			url = "https://www.falabella.com.pe/falabella-pe/search/?Ntt=" + urllib.parse.quote(busqueda, encoding=' Windows-1252')
			soup = BeautifulSoup(requests.get(url = url).text, 'html.parser')
			scripts = soup.find_all('script')
			if len(scripts[-7].text.split('var fbra_browseProductListConfig = ')) == 1:
				response = 'No se encontraron ofertas'
			else:
				productos = js.loads(scripts[-7].text.split('var fbra_browseProductListConfig = ')[1].split('var fbra_browseProductList')[0].replace("};","}"))
				contador = 0
				for prod in productos['state']['searchItemList']['resultList']:
					if 'meatSticker' in prod:
						if contador == 5:
							break
						contador = contador + 1
						sku = prod['skuId']
						url_prod = prod['url']
						brand = prod['brand']
						title =prod['title']
						price_ele = prod['prices'][0]
						if 'originalPrice' in price_ele:
							price = "S/." + prod['prices'][0]['originalPrice']
						else:
							price = "S/." + prod['prices'][0]['formattedLowestPrice'] + " - S/." + prod['prices'][0]['formattedHighestPrice'] 
						disc = prod['meatSticker']['second']['title']
						attachments.append({"color": "#EF6C6C",	"title": brand + '\n' + title, "thumb_url": "https://falabella.scene7.com/is/image/FalabellaPE/" + sku + "?wid=120", 
							"text": disc +" de descuento" +"\n"+ price,
							"actions": [
							{"type":"button", "text":"Detalles", "url":"https://www.falabella.com.pe" + url_prod, "style":"default",},
							{"type":"button", "text":"Imagen", "url":'https://falabella.scene7.com/is/image/FalabellaPE/' + sku, "style":"default",}
							]})
				if contador == 0:
					response = 'No se encontraron ofertas'
	
	#do somethig if the user is bored
	elif intent == 'amelia.agent.boring' or intent == 'amelia.user.bored':
		url = "https://es.wikipedia.org/wiki/Especial:Aleatoria"
		r = requests.get(url = url).text
		soup = BeautifulSoup(r, 'html.parser')
		scripts = soup.find_all('p')
		response = response + "\n" + scripts[0].get_text()
	
	#fun function
	elif intent == 'amelia.agent.roboto':
		desc = 'default'
		if command.find("robotiza a") != -1:
			desc = command.split("robotiza a",1)[1].lstrip()
		elif command.find("robot a") != -1:
			desc = command.split("robot a",1)[1].lstrip() 
		elif command.find("robot de") != -1:
			desc = command.split("robot de",1)[1].lstrip()
		elif command.find(":robot_face:") != -1:
			desc = command.split(":robot_face:",1)[1].lstrip()
		elif command.find("robot") != -1:
			desc = command.split("robot",1)[1].lstrip()
			if desc == '':
				desc = 'default'
		url = "https://robohash.org/"+ desc.replace('?','') + "?bgset=bg2&size="
		attachments.append({"color": "#43e084",	"title": ":robot_face:" ,"image_url": url + "200x200",})

	#search a sku
	elif command.startswith('Busca SKU:'):
		sku = command.split("SKU: ",1)[1]
		print(sku) 
		response = "Por supuesto, para que meche vea que si te entiendo, la imagen del sku: " + sku + " es la siguiente" 
		attachments = [
			{
				"color": "#36a64f",
				"title": "SKU " + sku,
				"image_url": "https://falabella.scene7.com/is/image/FalabellaPE/" + sku + "?wid=320",
				"footer": "Starter Bot",
			}
		]

	#search anything
	elif intent == 'amelia.user.search':
		parameters_json = js.loads(MessageToJson(parameters))
		print(parameters_json['saga_color'])
		descripcion = ''
		if command.find("busca") != -1:
			descripcion = command.split("busca",1)[1].lstrip() 
		elif command.find("hay") != -1:
			descripcion = command.split("hay",1)[1].lstrip()
		else:
			response = 'No entiendo que debo buscar, por favor seguir un patrón similar al siguiente: "busca ropa de cama"'

		if descripcion != '':					
			if re.search("^cat[0-9]+$", descripcion) == None:
				if response != '':
					color = response
				else:
					color = ""
				url = get_saga_color_filter(parameters_json['saga_color'],descripcion,color)
			else:
				url = "https://www.falabella.com.pe/falabella-pe/category/" + descripcion + "/"

			response ="@, esto es lo que encontré:"	
			soup = BeautifulSoup(requests.get(url = url).text, 'html.parser')
			scripts = soup.find_all('script')
			if len(scripts[-7].text.split('var fbra_browseProductListConfig = ')) == 1:
				response = 'No se encontraron resultados para tu búsqueda, intenta con terminos mas generales'
			else:
				productos = js.loads(scripts[-7].text.split('var fbra_browseProductListConfig = ')[1].split('var fbra_browseProductList')[0].replace("};","}"))
				contador = 0
				for prod in productos['state']['searchItemList']['resultList']:
					if contador == 5:
						break
					contador = contador + 1
					sku = prod['skuId']
					url_prod = prod['url']
					brand = prod['brand']
					title =prod['title']
					price_ele = prod['prices'][0]
					if 'originalPrice' in price_ele:
						price = "S/." + prod['prices'][0]['originalPrice']
					else:
						price = "S/." + prod['prices'][0]['formattedLowestPrice'] + " - S/." + prod['prices'][0]['formattedHighestPrice'] 

					attachments.append({"color": "#439FE0",	"title": brand + "\n" + title, "thumb_url": "https://falabella.scene7.com/is/image/FalabellaPE/" + sku + "?wid=120",
					"text": "SKU: " + sku +"\n"+ price,
					"actions": [
					{"type":"button", "text":"Detalles", "url":"https://www.falabella.com.pe"+url_prod,	"style": "default",},
					{"type":"button", "text":"Imagen", "url":'https://falabella.scene7.com/is/image/FalabellaPE/' + sku, "style":"default",}
					]})		

				if contador == 0:
					response = 'No se encontraron ofertas'		

	#default fallback
	elif intent == 'amelia.default' and command.lstrip().rstrip().startswith(':') and command.lstrip().rstrip().endswith(':'):
		response = "Lo siento @, yo no hablo en emojis :gun:" 

	response = response.replace('@', user)
	slack_client.api_call("chat.postMessage", channel=channel, text=response, attachments=attachments)


if __name__ == "__main__":
	if slack_client.rtm_connect(with_team_state=False):
		print("Starter Bot connected and running!")
		# Read bot's user ID by calling Web API method `auth.test`
		starterbot_id = slack_client.api_call("auth.test")["user_id"]
		while True:
			command, channel, user, user_id = parse_bot_commands(slack_client.rtm_read())
			if command:
				handle_command(command, channel, user, user_id)
			time.sleep(RTM_READ_DELAY)
	else:
		print("Connection failed. Exception traceback printed above.")
