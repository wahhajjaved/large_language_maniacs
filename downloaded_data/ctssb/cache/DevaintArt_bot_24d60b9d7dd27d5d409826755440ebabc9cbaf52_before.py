from bs4 import BeautifulSoup
import requests
import json
import os


def download(result):  # dead code
    download = requests.get(result[0]['href'])
    return download


def write_file(download, file_name):
    with open(file_name, 'wb') as fd:
            for chunk in download.iter_content(chunk_size=4096):
                fd.write(chunk)


def write_log(user_name, download_link):
    with open("download_log.txt", 'a') as af:
        af.write(user_name)
        af.write(';')
        af.write(download_link)
        af.write('\n')
        print("Download logged!\n")


def fetch_html(page_url):
    da_page = requests.get(page_url)    
    mysoup = BeautifulSoup(da_page.text, 'html.parser')
    return mysoup
    

def search_pictures(url, class_tag, class_name_one, class_name_two, tag_in_list):  # not needed, delete later, json_request will do the job
    DIV = "div"
    soup = fetch_html(url)
    outer_div = soup.find(DIV, class_="torpedo-container")
    result = outer_div.find_all(class_tag, class_=class_name_two)
    links = [item[tag_in_list] for item in result]
    return links


def fetch_csrf(url):
    soup = fetch_html(url)
    all_script = soup.head.find_all('script')
    csrf = ""
    for i in all_script:
        if i.string == None:
            continue
        match_index = i.string.find('csrf')
        if int(match_index) > -1:
            res = i.string.split(",")
            for j in range(len(res)):
                if 'csrf' in res[j]:
                    csrf = res[j].split(":")
                    csrf = [[csrf[i].replace('"', '') for i in range(len(csrf))]]
                    csrf = dict(csrf)
    return csrf


def fetch_href(page_url, json_request, HEADER):
    CLASS_NAME_FOR_TAG_A = 'torpedo-thumb-link'
    TAG_A = 'a'
    OFFSET = 24
    offset_counter = 0
    response_counter = 1
    href_set = set()
    while True:
        req = requests.post(page_url, data=json_request, headers=HEADER)
        print("RESPONSE GET ------------------------ No. ", response_counter)
        print("STATUS CODE -- ", req)
        json_soup = BeautifulSoup(req.text, 'html.parser')
        out_div2 = [i['href'] for i in json_soup.find_all(TAG_A, class_= CLASS_NAME_FOR_TAG_A)]
        if len(out_div2) == 0:
            print("RESPONSE GOT WITH NO VALUABLE DATA! REQUESTING FINISHED")
            break
        else:
            href_set.update(out_div2)            
            offset_counter += OFFSET
            json_request["offset"] = str(offset_counter)       
            response_counter += 1
    return href_set
    

def fetch_src(links, user_name, already_downloaded):
    INDEX_OF_HI_RES = 0
    INDEX_OF_NAME = -1    
    saved_file_counter = 1
    all_links = len(links)

    with open("download_log.txt", 'a') as af:
        for link in links:
            print("NUMBER :: {}    PROGRESS :: {}%".format(saved_file_counter, round((saved_file_counter/all_links)*100, 1)))
            saved_file_counter += 1
            print("FETCHED LINK: ", link)    
            soup_for_img_serach = fetch_html(link)
            out_div = soup_for_img_serach.find("div", class_='dev-view-deviation')
            res = [i for i in out_div.find_all("img", class_='dev-content-full')]
            if not res:
                print("This is not a picture or NSFW content\n")
                continue
            res = [j['src'] for j in res]
            print("DOWNLOADING ------------------- ", res)
            if res[INDEX_OF_HI_RES] in already_downloaded:
                print("This file has already been downloaded!\n")
                continue
            split_name = res[INDEX_OF_HI_RES].split('/')
            filepath = ".\\" + user_name + '\\' + split_name[INDEX_OF_NAME]
            if not os.path.exists(user_name):
                os.makedirs(user_name)        
            
            download_req = requests.get(res[INDEX_OF_HI_RES])
            status_code = download_req.status_code
            if status_code != 200:
                print("Failed to download: Error {}".format(status_code))
                continue

            write_file(download_req, filepath)
            print("SAVED AS: {}".format(filepath))

            af.write(user_name)
            af.write(';')
            af.write(res[INDEX_OF_HI_RES])
            af.write('\n')
            print("Download logged!\n")


def make_url(user_name):
    url_list = []
    page_url = 'https://'
    page_url += user_name.lower()
    page_url += '.deviantart.com/gallery/?catpath=/'
    url_list.append(page_url)

    scrap_gallery = page_url[:-1] + 'scraps'
    url_list.append(scrap_gallery)
    return url_list


def read_log():
    record = []
    INDEX_OF_LOGGED_URL = 1
    if os.path.isfile("download_log.txt"):
        with open("download_log.txt", 'r') as rf:
            for line in rf:
                readed = line.strip('\n').split(';')
                record.append(readed[INDEX_OF_LOGGED_URL])        
    return record

user_name = ""
while user_name == "":
    user_name = input("\nPlease enter the user's name (make sure it's correct): ")

page_url = make_url(user_name)

#class_name_one = 'folderview-art'  # dead code
#tag_in_list = 'href'  # dead code
#links = search_pictures(page_url, TAG_A, class_name_one, CLASS_NAME_FOR_TAG_A, tag_in_list)  # not needed, json will od the job

json_request= {
"username" : "",
"offset" : "0",
"limit" : "24",
"_csrf" : "",
"dapiIid" : "0"}

USER_AGEN = "Mozilla/5.0 (Windows NT 10.0;...) Gecko/20100101 Firefox/57.0"
HEADER = {"user_agen" : USER_AGEN}
INDEX_OF_MAIN_GALLERY = 0
INDEX_OF_SCRAP_GALLERY = 1

csrf = fetch_csrf(page_url[INDEX_OF_MAIN_GALLERY])
print(csrf)
json_request["username"] = user_name
json_request["_csrf"] = csrf['csrf']
print(json_request)

href_set = fetch_href(page_url[INDEX_OF_MAIN_GALLERY], json_request, HEADER)

csrf = fetch_csrf(page_url[INDEX_OF_SCRAP_GALLERY])
print(csrf)
json_request["username"] = user_name
json_request["offset"] = "0"
json_request["catpath"] = "scraps"
json_request["_csrf"] = csrf['csrf']
print(json_request)

scrap_href_set = fetch_href(page_url[INDEX_OF_SCRAP_GALLERY], json_request, HEADER)

href_set.update(scrap_href_set)
print(href_set)
print("\nNUMBER OF LINKS FOUND ---------------- {}\n".format(len(href_set)))

already_downloaded = read_log()
fetch_src(href_set, user_name, already_downloaded)  # also write_file temporary

print("-" * 50)
print("OK")
