import requests
from bs4 import BeautifulSoup
import urllib
from operator import itemgetter
from DKPostRequestBuilder import* 

def getContractsDict(user_ID): 
	s = requests.Session()

	r= requests.get("http://www.dschungelkompass.ch/mobile/welcomeErweitertesprofil.xhtml")
	# print(r.headers)
	soup = BeautifulSoup(r.content)
	soupH = (r.headers)
	sessionID = soupH["Set-Cookie"]
	sessionID = sessionID.split(';')[0]
	print(sessionID)
	# id="javax.faces.ViewState"
	viewState = soup.find("input", {"id": "javax.faces.ViewState"})
	values = viewState['value'].split(":")
	value1  = values[0]
	value2 = values[1]

	url ="http://www.dschungelkompass.ch/mobile/welcomeSchnellprofil.xhtml"

	url2 ="http://www.dschungelkompass.ch/mobile/welcomeErweitertesprofil.xhtml"



	data4 = {
	"inputfelderform":"inputfelderform",
	"inputfelderform:inputFelder:anzMinEingabe":totalCallsMinutesCH(user_ID), #Minuten telefonieren CH pro Monat
	"inputfelderform:inputFelder:anzAnrufeEingabe":totalCallsNumberCH(user_ID), # Anzalh Anrufe pro Monat
	"inputfelderform:inputFelder:anteil3NrEingabe":getTrafficPercentageTop3Numbers(user_ID),
	"inputfelderform:inputFelder:alterAuswahl":getUserAgeField(user_ID), #Alter: kann 15 (unter 18), 25 (unter 26), 26 (unter 27), 29 (unter 30), 65 (65 oder aelter), 30 (zwischen 30 und 65)
	"inputfelderform:inputFelder:j_idt117":getUserCurrentContractPrice(user_ID),  #wie viel ich jetzt pro Monat bezahle
	"inputfelderform:inputFelder:providerFilterSB":getUserOperator(user_ID), #jetziger Anbieter
	"inputfelderform:inputFelder:j_idt106_collapsed":"false",
	"inputfelderform:inputFelder:j_idt127":"on",
	"inputfelderform:inputFelder:aufFestnetzSwisscom":"20",
	"inputfelderform:inputFelder:aufFestnetzUPC":"0",
	"inputfelderform:inputFelder:j_idt136_collapsed":"false",
	"inputfelderform:inputFelder:aufSwisscom":"40",#Verteilung: Swisscom
	"inputfelderform:inputFelder:aufOrange":"30",#Verteilung: Orange
	"inputfelderform:inputFelder:aufSunrise":"30",#Verteilung: Sunrise
	"inputfelderform:inputFelder:aufMbudget":"0",
	"inputfelderform:inputFelder:aufCoopMobile":"0",
	"inputfelderform:inputFelder:j_idt147_collapsed":"false",
	"inputfelderform:inputFelder:aufAldi":"0",
	"inputfelderform:inputFelder:aufOk":"0",
	"inputfelderform:inputFelder:aufLebara":"0",
	"inputfelderform:inputFelder:aufTalkTalk":"0",
	"inputfelderform:inputFelder:aufYallo":"0",
	"inputfelderform:inputFelder:aufLyca":"0",
	"inputfelderform:inputFelder:aufOrtel":"0",
	"inputfelderform:inputFelder:aufMobileUPC":"0",
	"inputfelderform:inputFelder:aufAndere":"0",
	"inputfelderform:inputFelder:j_idt169_collapsed":"true",
	"inputfelderform:inputFelder:anzSMSEingabe":SMS_toCH(user_ID),#Sms pro Monat CH
	"inputfelderform:inputFelder:anzTageSMS":"30", #Innerhalb von x Tagen
	"inputfelderform:inputFelder:j_idt212_collapsed":"false",
	"inputfelderform:inputFelder:datenmengeMBEingabe":dataCH(user_ID),#Datenmenge pro Monat
	"inputfelderform:inputFelder:intVerwendungAnzTageEingabe":"30", #Innerhalb von x Tagen
	"inputfelderform:inputFelder:speedAuswahl":"1.0",
	"inputfelderform:inputFelder:j_idt223_collapsed":"false",
	"inputfelderform:inputFelder:SmsAusland":SMS_toABROAD(user_ID), #SMS ins Ausland
	"inputfelderform:inputFelder:j_idt253_input":callsToAbroadLandX(user_ID, 0).get('country'), #Anrufe ins Ausland: Land1
	"inputfelderform:inputFelder:Land1FixMin":callsToAbroadLandX(user_ID, 0).get('duration'), #Festnetz minuten anrufe ins ausland
	"inputfelderform:inputFelder:Land1FixAnzAnr":callsToAbroadLandX(user_ID, 0).get('number'), #Festnetz Anzahl Anrufe ins Ausland
	"inputfelderform:inputFelder:Land1MobMin":callsToAbroadLandX(user_ID, 0).get('duration'),
	"inputfelderform:inputFelder:Land1MobAnzAnr":callsToAbroadLandX(user_ID, 0).get('number'),
	"inputfelderform:inputFelder:j_idt250_collapsed":"false",
	"inputfelderform:inputFelder:j_idt277_input":callsToAbroadLandX(user_ID, 1).get('country'), #Anrufe ins Auland: Land2
	"inputfelderform:inputFelder:Land2FixMin":callsToAbroadLandX(user_ID, 1).get('duration'),
	"inputfelderform:inputFelder:Land2FixAnzAnr":callsToAbroadLandX(user_ID, 1).get('number'),
	"inputfelderform:inputFelder:Land2MobMin":callsToAbroadLandX(user_ID, 1).get('duration'),
	"inputfelderform:inputFelder:Land2MobAnzAnr":callsToAbroadLandX(user_ID, 1).get('number'),
	"inputfelderform:inputFelder:j_idt274_collapsed":"false",
	"inputfelderform:inputFelder:j_idt301_input":callsToAbroadLandX(user_ID, 2).get('country'),
	"inputfelderform:inputFelder:Land3FixMin":callsToAbroadLandX(user_ID, 2).get('duration'),
	"inputfelderform:inputFelder:Land3FixAnzAnr":callsToAbroadLandX(user_ID, 2).get('number'),
	"inputfelderform:inputFelder:Land3MobMin":callsToAbroadLandX(user_ID, 2).get('duration'),
	"inputfelderform:inputFelder:Land3MobAnzAnr":callsToAbroadLandX(user_ID, 2).get('number'),
	"inputfelderform:inputFelder:j_idt298_collapsed":"false",
	"inputfelderform:inputFelder:j_idt325_input":callsToAbroadLandX(user_ID, 3).get('country'),
	"inputfelderform:inputFelder:Land4FixMin":callsToAbroadLandX(user_ID, 3).get('duration'),
	"inputfelderform:inputFelder:Land4FixAnzAnr":callsToAbroadLandX(user_ID, 3).get('number'),
	"inputfelderform:inputFelder:Land4MobMin":callsToAbroadLandX(user_ID, 3).get('duration'),
	"inputfelderform:inputFelder:Land4MobAnzAnr":callsToAbroadLandX(user_ID, 3).get('number'),
	"inputfelderform:inputFelder:j_idt322_collapsed":"false",
	"inputfelderform:inputFelder:j_idt349_input":callsToAbroadLandX(user_ID, 4).get('country'),
	"inputfelderform:inputFelder:Land5FixMin":callsToAbroadLandX(user_ID, 4).get('duration'),
	"inputfelderform:inputFelder:Land5FixAnzAnr":callsToAbroadLandX(user_ID, 4).get('number'),
	"inputfelderform:inputFelder:Land5MobMin":callsToAbroadLandX(user_ID, 4).get('duration'),
	"inputfelderform:inputFelder:Land5MobAnzAnr":callsToAbroadLandX(user_ID, 4).get('number'),
	"inputfelderform:inputFelder:j_idt346_collapsed":"false",
	"inputfelderform:inputFelder:j_idt374_input":getMostVisitedForeignCountry(user_ID),
	"inputfelderform:inputFelder:Roaming1AnzTage":getDaysInMostVisitedCountry(user_ID),
	"inputfelderform:inputFelder:RoamingSMS":getSMSWhileRoaming(user_ID),
	"inputfelderform:inputFelder:RoamingDatenMB":dataRoaming(user_ID),
	"inputfelderform:inputFelder:RoamingIncomingMin":incomingCallsAbroad(user_ID).get('duration'),
	"inputfelderform:inputFelder:RoamingIncomingAnr":incomingCallsAbroad(user_ID).get('number'),
	"inputfelderform:inputFelder:j_idt388_collapsed":"false",
	"inputfelderform:inputFelder:RoamingToCHMin":callsToCHfromAbroad(user_ID).get('duration'),
	"inputfelderform:inputFelder:RoamingToCHAnr":callsToCHfromAbroad(user_ID).get('number'),
	"inputfelderform:inputFelder:j_idt397_collapsed":"false",
	"inputfelderform:inputFelder:RoamingToLocalMin":callsWithinVisitedForeignCountry(user_ID).get('duration'),
	"inputfelderform:inputFelder:RoamingToLocalAnr":callsWithinVisitedForeignCountry(user_ID).get('number'),
	"inputfelderform:inputFelder:j_idt406_collapsed":"false",
	"inputfelderform:inputFelder:LandlisteDB_R_Land1":callsToAbroadFromAbroadLandX(user_ID, 0).get('country'),
	"inputfelderform:inputFelder:RoamingToLand1Min":callsToAbroadFromAbroadLandX(user_ID, 0).get('duration'),
	"inputfelderform:inputFelder:RoamingToLand1Anr":callsToAbroadFromAbroadLandX(user_ID, 0).get('number'),
	"inputfelderform:inputFelder:j_idt415_collapsed":"false",
	"inputfelderform:inputFelder:LandlisteDB_R_Land2":callsToAbroadFromAbroadLandX(user_ID, 1).get('country'),
	"inputfelderform:inputFelder:RoamingToLand2Min":callsToAbroadFromAbroadLandX(user_ID, 1).get('duration'),
	"inputfelderform:inputFelder:RoamingToLand2Anr":callsToAbroadFromAbroadLandX(user_ID, 1).get('number'),
	"inputfelderform:inputFelder:j_idt428_collapsed":"false",
	"inputfelderform:inputFelder:LandlisteDB_R_Land3":callsToAbroadFromAbroadLandX(user_ID, 2).get('country'),
	"inputfelderform:inputFelder:RoamingToLand3Min":callsToAbroadFromAbroadLandX(user_ID, 2).get('duration'),
	"inputfelderform:inputFelder:RoamingToLand3Anr":callsToAbroadFromAbroadLandX(user_ID, 2).get('number'),
	"inputfelderform:inputFelder:j_idt441_collapsed":"false",
	"inputfelderform:inputFelder_activeIndex":"4",
	"inputfelderform:j_idt482":"",
	"javax.faces.ViewState":value1 + ":"+value2
	}

	for k in data4:
		print( k + " - '" + str(data4.get(k)) + "' ")

	testdata = "inputfelderform=inputfelderform&inputfelderform%3AinputFelder%3AanzMinEingabe="+totalCallsMinutesCH(user_ID)+"&inputfelderform%3AinputFelder%3AanzAnrufeEingabe="+totalCallsNumberCH(user_ID)+"&inputfelderform%3AinputFelder%3Aanteil3NrEingabe="+str(getTrafficPercentageTop3Numbers(user_ID))+"&inputfelderform%3AinputFelder%3AalterAuswahl=30&inputfelderform%3AinputFelder%3Aj_idt117=0.0&inputfelderform%3AinputFelder%3AproviderFilterSB=&inputfelderform%3AinputFelder%3Aj_idt106_collapsed=false&inputfelderform%3AinputFelder%3Aj_idt127=on&inputfelderform%3AinputFelder%3AaufFestnetzSwisscom=20&inputfelderform%3AinputFelder%3AaufFestnetzUPC=0&inputfelderform%3AinputFelder%3Aj_idt136_collapsed=false&inputfelderform%3AinputFelder%3AaufSwisscom=40&inputfelderform%3AinputFelder%3AaufOrange=20&inputfelderform%3AinputFelder%3AaufSunrise=20&inputfelderform%3AinputFelder%3AaufMbudget=0&inputfelderform%3AinputFelder%3AaufCoopMobile=0&inputfelderform%3AinputFelder%3Aj_idt147_collapsed=false&inputfelderform%3AinputFelder%3AaufAldi=0&inputfelderform%3AinputFelder%3AaufOk=0&inputfelderform%3AinputFelder%3AaufLebara=0&inputfelderform%3AinputFelder%3AaufTalkTalk=0&inputfelderform%3AinputFelder%3AaufYallo=0&inputfelderform%3AinputFelder%3AaufLyca=0&inputfelderform%3AinputFelder%3AaufOrtel=0&inputfelderform%3AinputFelder%3AaufMobileUPC=0&inputfelderform%3AinputFelder%3AaufAndere=0&inputfelderform%3AinputFelder%3Aj_idt169_collapsed=true&inputfelderform%3AinputFelder%3AanzSMSEingabe=12&inputfelderform%3AinputFelder%3AanzTageSMS=12&inputfelderform%3AinputFelder%3Aj_idt212_collapsed=false&inputfelderform%3AinputFelder%3AdatenmengeMBEingabe=12&inputfelderform%3AinputFelder%3AintVerwendungAnzTageEingabe=12&inputfelderform%3AinputFelder%3AspeedAuswahl=0.2&inputfelderform%3AinputFelder%3Aj_idt223_collapsed=false&inputfelderform%3AinputFelder%3ASmsAusland=12&inputfelderform%3AinputFelder%3Aj_idt253_input=Deutschland&inputfelderform%3AinputFelder%3ALand1FixMin=12&inputfelderform%3AinputFelder%3ALand1FixAnzAnr=12&inputfelderform%3AinputFelder%3ALand1MobMin=12&inputfelderform%3AinputFelder%3ALand1MobAnzAnr=12&inputfelderform%3AinputFelder%3Aj_idt250_collapsed=false&inputfelderform%3AinputFelder%3Aj_idt277_input=&inputfelderform%3AinputFelder%3ALand2FixMin=0&inputfelderform%3AinputFelder%3ALand2FixAnzAnr=0&inputfelderform%3AinputFelder%3ALand2MobMin=0&inputfelderform%3AinputFelder%3ALand2MobAnzAnr=0&inputfelderform%3AinputFelder%3Aj_idt274_collapsed=true&inputfelderform%3AinputFelder%3Aj_idt301_input=&inputfelderform%3AinputFelder%3ALand3FixMin=0&inputfelderform%3AinputFelder%3ALand3FixAnzAnr=0&inputfelderform%3AinputFelder%3ALand3MobMin=0&inputfelderform%3AinputFelder%3ALand3MobAnzAnr=0&inputfelderform%3AinputFelder%3Aj_idt298_collapsed=true&inputfelderform%3AinputFelder%3Aj_idt325_input=&inputfelderform%3AinputFelder%3ALand4FixMin=0&inputfelderform%3AinputFelder%3ALand4FixAnzAnr=0&inputfelderform%3AinputFelder%3ALand4MobMin=0&inputfelderform%3AinputFelder%3ALand4MobAnzAnr=0&inputfelderform%3AinputFelder%3Aj_idt322_collapsed=true&inputfelderform%3AinputFelder%3Aj_idt349_input=&inputfelderform%3AinputFelder%3ALand5FixMin=0&inputfelderform%3AinputFelder%3ALand5FixAnzAnr=0&inputfelderform%3AinputFelder%3ALand5MobMin=0&inputfelderform%3AinputFelder%3ALand5MobAnzAnr=0&inputfelderform%3AinputFelder%3Aj_idt346_collapsed=true&inputfelderform%3AinputFelder%3Aj_idt374_input=Deutschland&inputfelderform%3AinputFelder%3ARoaming1AnzTage=12&inputfelderform%3AinputFelder%3ARoamingSMS=12&inputfelderform%3AinputFelder%3ARoamingDatenMB=12&inputfelderform%3AinputFelder%3ARoamingIncomingMin=12&inputfelderform%3AinputFelder%3ARoamingIncomingAnr=12&inputfelderform%3AinputFelder%3Aj_idt388_collapsed=false&inputfelderform%3AinputFelder%3ARoamingToCHMin=12&inputfelderform%3AinputFelder%3ARoamingToCHAnr=12&inputfelderform%3AinputFelder%3Aj_idt397_collapsed=false&inputfelderform%3AinputFelder%3ARoamingToLocalMin=12&inputfelderform%3AinputFelder%3ARoamingToLocalAnr=12&inputfelderform%3AinputFelder%3Aj_idt406_collapsed=false&inputfelderform%3AinputFelder%3ALandlisteDB_R_Land1=&inputfelderform%3AinputFelder%3ARoamingToLand1Min=0&inputfelderform%3AinputFelder%3ARoamingToLand1Anr=0&inputfelderform%3AinputFelder%3Aj_idt415_collapsed=true&inputfelderform%3AinputFelder%3ALandlisteDB_R_Land2=&inputfelderform%3AinputFelder%3ARoamingToLand2Min=0&inputfelderform%3AinputFelder%3ARoamingToLand2Anr=0&inputfelderform%3AinputFelder%3Aj_idt428_collapsed=true&inputfelderform%3AinputFelder%3ALandlisteDB_R_Land3=&inputfelderform%3AinputFelder%3ARoamingToLand3Min=0&inputfelderform%3AinputFelder%3ARoamingToLand3Anr=0&inputfelderform%3AinputFelder%3Aj_idt441_collapsed=true&inputfelderform%3AinputFelder_activeIndex=4&inputfelderform%3Aj_idt482=&javax.faces.ViewState="+value1 +"%3A" + value2


	data4 = urllib.urlencode(data4)

	# print(formDataExt)

	headers = { 
	'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
	'Accept-Encoding':'gzip, deflate',
	'Accept-Language':'en-US,en;q=0.8',
	'Connection':'keep-alive',
	'Content-Type':'application/x-www-form-urlencoded',
	'Cookie':sessionID,
	'Host':'dschungelkompass.ch',
	'Origin':'http://www.dschungelkompass.ch',
	'Referer':'http://www.dschungelkompass.ch/mobile/welcomeSchnellprofil.xhtml',
	'Upgrade-Insecure-Requests':'1',
	'User-Agent':'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/51.0.2704.103 Safari/537.36'
	}
	req = requests.post(url2, data = data4, headers = headers)

	resultsSouped = BeautifulSoup(req.content)



	contracts = resultsSouped.find_all("div", {"class": "ausgabeTabelleRow"})
	
	print("contracts are " + str(contracts))

	i = 0;
	contractsParsed =[]


	for c in contracts:
		cParsed = {}
		# print("---------------- ......... -----------------------------")
		providerundAbo = c.find("div",{"class": "ausgabeTabelleProviderUndAbo"})
		providerHTML = providerundAbo.children.next()
		planHTML= providerHTML.next_sibling
		cParsed['Anbieter'] = providerHTML.string
		cParsed['PlanName'] = planHTML.string
		

		priceHTML = c.find("span",{"class": "ausgabeTabelleLabelsKostenTotal"})
		
		cParsed['Price']  = float(priceHTML.string)


		SpeedTypeNetwork = c.find("div",{"class": "ausgabeTabelleSpeed"})
		aboType=""
		for child in SpeedTypeNetwork.children:
			if child.string=="Art: ":
				aboType = child.next_sibling.string
				
		
		cParsed['Abo Type'] = aboType
		details = c.find("div",{"class": "ausgabeTabelleCell3"})
		for d in details.find_all("br"):
			fieldHTML = d.next_sibling
			valueHTML = fieldHTML.next_sibling
			cParsed[fieldHTML.string] = valueHTML.string
		
		bemerkungenSection = c.find("div",{"class": "ausgabeTabelleBemerkungen"})
		minDurationValue = bemerkungenSection.find("span",{"class": "greenText"})
		cParsed["Minium Duration"] = minDurationValue.string + " Months"
		

		contractsParsed.append(cParsed)
			
	contractsParsed = sorted(contractsParsed, key=itemgetter('Price'), reverse=True) 
	# contractsParsedDict  = {}
	# i = 0
	# for c in contractsParsed:
	# 	contractsParsedDict[str(i)]= contractsParsed[i]
		
	return contractsParsed

