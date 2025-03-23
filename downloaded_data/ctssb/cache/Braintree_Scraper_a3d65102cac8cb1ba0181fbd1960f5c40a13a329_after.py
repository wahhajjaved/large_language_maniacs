import sys
from datetime import datetime
import urllib
import re
import requests
import time
from datetime import datetime
from datetime import timedelta
import pandas as pd
from StringIO import StringIO
from bs4 import BeautifulSoup
import keyring


class Braintree:
    
    def __init__(self, user_name=None, password=None):
        self.s = requests.session()
        self.s.headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_8_3) AppleWebKit/537.31 (KHTML, like Gecko) Chrome/26.0.1410.43 Safari/537.31'
        self.s.headers['Accept-Encoding'] = 'gzip,deflate,sdch'
        self.s.headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
        self.s.headers['Accept-Language'] = 'en-US,en;q=0.8'
        self.s.headers['X-Requested-With'] = 'XMLHttpRequest'
        self.url_base = 'https://www.braintreegateway.com'
        self.logged_in = False
        self.account_data = {}
        self.user_name = user_name
        self.password = password
        self.response_html = ''
        self.download_queue = []
        self.disbursement_data = []
        self.settlement_data = []
        if user_name is not None and password is not None:
            self.login()
    def check_logged_in(self):
        res = self.s.get(self.url_base)
        if res.text.find('Welcome - Braintree Gateway') != -1:
            return True
        else:
            self.login()
            return True
        
    def login(self, user_name=None, password=None):
        if user_name is not None:
            self.user_name = user_name
        if password is not None:
            self.password = password
        lg = self.s.get('https://www.braintreegateway.com/login')
        auth_token = BeautifulSoup(lg.text).find('input', {'name':'authenticity_token'})['value']
        dta = {'login':self.user_name, 
               'password':self.password, 
               'commit':'Sign In',
               'authenticity_token' : auth_token
               }
        res = self.s.post('https://www.braintreegateway.com/session', dta)
        if res.text.find('Login or password was incorrect') == -1:
            self.logged_in = True
            self.account_data['merchant_accounts'] = [ac['value'] for ac in BeautifulSoup(res.text).find('select', attrs={'name':'merchant_accounts'}).findAll('option')]
            self.account_data['merchant_tag'] = BeautifulSoup(res.text).find('a', attrs={'href':re.compile('/merchant.*/transactions/advanced_search')})['href'].split('/')[2]
            self.auth_token = BeautifulSoup(res.text).find('input', attrs={'name':'authenticity_token'})['value']
            print 'Login Success'
        self.response_html = res.text
    
    def load_disbursement_report(self, date_range_min, date_range_max, wait_time=30):
        self.check_logged_in()
        report_data = {
                        'search[created_using][]' : ['full_information', 'token'],
                        'search[credit_card_card_type][]' : ['Visa', 'MasterCard', 'Discover', 'American Express', 'JCB', 'Maestro'],
                        'search[credit_card_customer_location][]':['us', 'international'],                
                        'search[disbursement_date][min]' : date_range_min.strftime('%m/%d/%Y'),
                        'search[disbursement_date][max]' : date_range_max.strftime('%m/%d/%Y'),
                        'search[merchant_account_id][]' : self.account_data['merchant_accounts'],
                        'search[source][]' : ['api', 'control_panel', 'recurring'],
                        'search[status][]' : ['authorized', 'authorization_expired', 'submitted_for_settlement', 'settling', 
                                            'settled', 'voided', 'processor_declined', 'gateway_rejected', 'failed'],
                        'search[type][]' : ['sale', 'credit']
                        }
        # Download Disbursment Report
        ds_url = self.url_base + '/merchants/' + self.account_data['merchant_tag'] + '/transactions/advanced_search'
        dso_url = self.url_base + '/merchants/' + self.account_data['merchant_tag'] + '/transactions/download_advanced_search_results'
        ds = self.s.get(ds_url, data=report_data)
        report_data['authenticity_token'] = self.auth_token
        dsr = self.s.post(dso_url, data=report_data)
        time.sleep(wait_time)
        # Check If Download Complete, if not add to queue
        dl_blocks = self.find_download_tags()
        dq = dl_blocks[0]
        dq['type'] = 'disbursement'
        if dq['complete'] == 'true':
            return self.download_tag(dq)
        else:
            self.download_queue.append(dq)
        return False
        
    def load_settlement_batch_report(self, load_date, wait_time=30):
        self.check_logged_in()
        # Load Settlement Batch Data for specific date        
        sb_data = {
                   'search[created_using][]':['full_information', 'token'],
                    'search[credit_card_card_type][]':['Visa', 'MasterCard', 'Discover', 'American Express', 'JCB', 'Maestro'],
                    'search[credit_card_customer_location][]':['us', 'international'],
                    'search[settlement_batch_ids][]' : [load_date.strftime('%Y-%m-%d')+'_'+a for a in self.account_data['merchant_accounts']],            
                    'search[source][]':['api', 'control_panel', 'recurring'],
                    'search[status][]':['authorized', 'authorization_expired', 'submitted_for_settlement', 'settling', 
                                        'settled', 'voided', 'processor_declined', 'gateway_rejected', 'failed'],
                    'search[type][]':['sale', 'credit']
                }
        sb_data['authenticity_token'] = self.auth_token
        dso_url = self.url_base + '/merchants/' + self.account_data['merchant_tag'] + '/transactions/download_advanced_search_results'
        dsr = self.s.post(dso_url, data=sb_data)
        time.sleep(wait_time)
        # Check If Download Complete, if not add to queue
        dl_blocks = self.find_download_tags()
        dq = dl_blocks[0]
        dq['type'] = 'settlement'
        if dq['complete'] == 'true':
            return self.download_tag(dq)
        else:
            self.download_queue.append(dq)
        return False

        
    def find_download_tags(self):
        self.check_logged_in()
        dlp_url = self.url_base + '/merchants/' + self.account_data['merchant_tag'] + '/downloads/'
        dlf = self.s.get(dlp_url)
        dl_blocks = BeautifulSoup(dlf.text).find('div', attrs={'id':'categorized-downloads'}).find('div', attrs={'class':'block'}).findAll('div')
        return [{'complete':b['data-complete'], 'date':b.find('span').text.strip(), 'download_url':b.find('a')['href'].rstrip('/delete')} for b in dl_blocks]
    
    def download_tag(self, download_dict):
        try:
            self.check_logged_in()
            dlp_url = self.url_base + download_dict['download_url']
            dl = self.s.get(dlp_url)
            df = pd.read_csv(StringIO(dl.text))
            if len(df.columns) <= 1:
                return False
            if download_dict['type'] == 'disbursement':
                self.disbursement_data.append(df)
            else:
                self.settlement_data.append(df)
            return True
        except Exception:
            return False
        
    def load_download_queue(self, wait_time=None):
        self.check_logged_in()
        dtags = self.find_download_tags()
        for i, dl in enumerate(self.download_queue):
            for tag in dtags:
                if dl['download_url'] == tag['download_url'] and tag['complete']=='true':
                    if not self.download_tag(dl):
                        print dl['type'] + ' load failed: sorry bro'
                    self.download_queue.pop(i)
        if wait_time is not None and len(self.download_queue) > 0:
            print 'Waiting Again'
            time.sleep(wait_time)
            self.load_download_queue(wait_time=None)

