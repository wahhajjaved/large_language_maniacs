# coding=utf-8
import re
import datetime
import vatnumber
import pycountry

CITIES = [u"Daugavpils", u"Jēkabpils", u"Jelgava", u"Jūrmala", u"Liepāja", u"Rēzekne", u"Rīga", u"Valmiera", u"Ventspils"]

def search_by_name(soup, title):
    try:
        return soup.find('div', text=re.compile(title)).parent.find("div", {"class": "cd"}).text
    except:
        return ""


def search_by_name_dt(soup, title):
    try:
        return soup.find('dt', text=re.compile(title)).parent.find("dd", {"class": "d"}).text
    except:
        return ""

def get_title(soup):
    title = search_by_name(soup, "Company name") or search_by_name(soup, "Nosaukums")
    try:
        return re.findall(r'\"(.+?)\"', title)[0].title()
    except:
        return title.upper().replace(u"SIA", u"").replace(u"AS", u"").replace(u"BIEDRĪBA", u"").strip().title()

def convert_date(value):
    try:
        return datetime.datetime.strptime(value, "%d.%m.%Y")
    except:
        return ""

def search_block_persons(soup, id):
    block = soup.find("dl", {"id": id})
    if not block:
        return None

    block = block.find("tbody")

    if not block:
        return None

    persons = block.findAll("tr")
    person_list = []
    for person in persons:
        name_pk = person.find("div", {"class": "c_text"}) or person.find("a", {"class": "special"})
        p_data = {
            "name": name_pk.next.replace(",","").strip(),
            "pk": name_pk.findNext().text,
        }
        info = [t.text if not isinstance(t, basestring) else t for t in name_pk.find_parents("td", limit=1)[0].findNextSibling("td").contents]
        info = ", ".join(filter(None, info)).replace(u"\xa0", " ")
        p_data.update({"info": info})
        person_list.append(p_data)
    return person_list



def check_vies(vat):
    try:
        return vatnumber.check_vies(vat)
    except:
        return None

def check_vat(number):
    vat = "LV%s" % str(number)
    return {"vat": vat, "check": check_vies(vat), "valid": vatnumber.check_vat_lv(str(number))}


def short_title_replace(word):
    word_check = word.lower()
    if word_check == 'un':
        return '&'
    if len(word) == 0:
        return ''
    return word[0]

def get_short_title(title):
    title = title.decode('utf-8')
    title = title.replace("SIA", "").replace("AS", "").replace("\"", "").replace("'", "").strip()
    splitted = title.split(" ")
    if len(title) < 10 or len(splitted)==1:
        return title[:6]
    if len(splitted) > 2:
        return "".join([short_title_replace(x) for x in splitted]).upper()
    if len(splitted[0]) < 9:
        return "%s%s" % (splitted[0].capitalize(), splitted[1][0].upper())
    return "%s%s" % (splitted[0][:4].capitalize(), splitted[1][:4].capitalize())

def replace_text(string, text):
    regex = re.compile("[, ]*%s[, ]*" % text, re.IGNORECASE|re.UNICODE)
    for found in regex.findall(string):
        string = string.replace(found, "")
    return string

def get_address(address, country="Latvia"):

    # Check country name in latvian - Latvija
    if 'latvija' in address.lower():
        country = "Latvia"
        address = replace_text(address, country)
        address = replace_text(address, "Latvija")

    return_dict = {
        "postal_code": "",
        "country": country,
        "city": "",
        "address": ""
    }

    if country is None:
        # lets search for country
        for country in pycountry.countries.objects:
            if country.name.lower() in address.lower():
                return_dict.update({"country": country.name})
                address = replace_text(address, country.name)
                break
    else:
        address = replace_text(address, country)

    if address.get('country') == "Latvia":
        regex = re.compile("LV[-]{0,1}[0-9]{4}", re.IGNORECASE|re.UNICODE)
        postal_code = regex.findall(address)
        if postal_code:
            return_dict.update({"postal_code": postal_code[0]})

        address = replace_text(address, "LV[-]{0,1}[0-9]{4}")

        for city in CITIES:
            if city.lower() in address.lower():
                return_dict.update({"city": city})
                address = replace_text(address, city)
                break

    return_dict.update({"address": address})

    return return_dict