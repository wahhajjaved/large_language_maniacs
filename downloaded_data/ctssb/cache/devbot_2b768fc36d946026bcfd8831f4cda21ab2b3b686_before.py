import os
import json
import gspread
import twilio
from oauth2client.client import SignedJwtAssertionCredentials

__author__ = 'Devon'


class Spreadsheet:

    # Spreadsheet key is extracted from the spreadsheet URL, stored in environment variables
    sheetKey = os.environ.get('GOOGLE_SHEET_KEY')
    spreadsheet = []
    messages = {}
    sheet_name = []
    current_date = []
    admin_number = []
    debug_flag = []
    responses = []

    def __init__(self):
        # Login to Google and create the worksheet object
        self.spreadsheet = self.login()

        # Get the current run properties from the admin sheet
        self.parse_admin_sheet()

        # Retrieve main sheet for parsing
        self.main_sheet = self.spreadsheet.worksheet(self.sheet_name)
        self.weekCol = None
        self.numbers = self.get_phone_numbers()
        self.responses = self.get_responses()
        self.text_bool = self.get_text_flag()

        # Parse the numbers and responses into a dict
        self.data = {}
        for ind, number in enumerate(self.numbers):
            self.data[number] = self.responses[ind]

    def exist(self, number):
        for num in self.numbers:
            if num == number:
                return True
        return False

    def get_row_for_number(self, number):
        for index, num in enumerate(self.numbers):
            if num == number:
                return index + 2

    def add_new_member(self, number, name):
        exist = False
        for num in self.numbers:
            if number == num:
                row = self.get_row_for_number(number)
                exist = True
                self.main_sheet.update_cell(row, 1, name)
        if not exist:
            self.numbers.append(number)
            self.data[number] = None

            formatted_number = number[1:4] + '-' + number[4:7] + '-' + number[7:11]
            self.main_sheet.update_cell(len(self.numbers)+1, 1, name)
            self.main_sheet.update_cell(len(self.numbers)+1, 2, "Y")
            self.main_sheet.update_cell(len(self.numbers)+1, 3, formatted_number)

    def login(self):
        # Use OAuth2 to sign in to Google Sheets
        json_key = json.load(open('/home/pi/devbot/devbot-047d0e03ef6e.json'))
        scope = ['https://spreadsheets.google.com/feeds']
        credentials = SignedJwtAssertionCredentials(json_key['client_email'], json_key['private_key'], scope)
        gc = gspread.authorize(credentials)

        # Login to Google and create the worksheet object
        return gc.open_by_key(self.sheetKey)

    def get_text_flag(self):
        col = self.main_sheet.find('Text').col

        texting = self.main_sheet.col_values(col)[1:len(self.numbers)+1]
        text_bool = []
        for text in texting:
            if text == 'Y':
                text_bool.append(True)
            else:
                text_bool.append(False)

        return text_bool

    def parse_admin_sheet(self):
        # Get the Admin spreadsheet
        admin = self.spreadsheet.worksheet('Admin')

        # Extract the indices for the different sections
        ind_10 = admin.find("1.0 - Main").row
        ind_11 = admin.find("1.1 - Response Tree").row
        ind_12 = admin.find("1.2 - Input Key").row

        # 1.0 Main Section
        self.sheet_name = admin.cell(ind_10+1, 2).value
        self.current_date = admin.cell(ind_10+2, 2).value
        self.admin_number = admin.cell(ind_10+3, 2).value
        self.debug_flag = admin.cell(ind_10+4, 2).value

        # 1.1 Response Tree Section
        self.messages = {
            'standard message f':    admin.cell(ind_11+1, 2).value,
            'standard message s':    admin.cell(ind_11+2, 2).value,
            'first text':            admin.cell(ind_11+3, 2).value,
            'removal':               admin.cell(ind_11+4, 2).value,
            'response text':         admin.cell(ind_11+5, 2).value,
            'unrecognized response': admin.cell(ind_11+6, 2).value,
            'new member':            admin.cell(ind_11+7, 2).value,
        }

        # 1.2 Input Key
        key = admin.col_values(1)[ind_12:]
        output = admin.col_values(2)[ind_12:]
        self.responses = dict(zip(key, output))

    def get_responses(self):
        try:
            self.weekCol = self.main_sheet.find(self.current_date).col
        except gspread.exceptions.CellNotFound:
            values_list = self.main_sheet.row_values(1)
            self.weekCol = len(values_list)+1

            self.main_sheet.update_cell(1, self.weekCol, self.current_date)

        responses = self.main_sheet.col_values(self.weekCol)
        return responses[1:len(self.numbers)+1]

    def get_phone_numbers(self):
        col = self.main_sheet.find('Cell Phone #').col
        numbers = self.main_sheet.col_values(col)
        numbers.pop(0)

        final_numbers = []
        for number in numbers:
            if not number:
                break
            else:
                final_numbers.append(format_number(number))

        return final_numbers

    def get_response(self, number):
        return self.data[number]

    def update_response(self, number, response):
        formatted_response = '="' + response + '"'
        self.main_sheet.update_cell(self.get_row_for_number(number), self.weekCol, formatted_response)
        self.data[number] = response

    def texting_number_list(self):
        send_text = []

        for ind, response in enumerate(self.responses):
            if response is None and self.text_bool[ind]:
                send_text.append(self.numbers[ind])

        return send_text

    def disable_text(self, number):
        self.main_sheet.update_cell(self.get_row_for_number(number), 2, "N")

    def enable_text(self, number):
        self.main_sheet.update_cell(self.get_row_for_number(number), 2, "Y")


def format_number(number):
    number = number.replace('-', '')
    number = number.replace(':', '')
    number = number.replace('+', '')

    if len(number) < 11:
        return '1' + number
    else:
        return number


class Phone:
    def __init__(self):
        TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID')
        TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN')
        self.TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER')

        self.client = twilio.rest.TwilioRestClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    def send_text(self, numbers, text):
        if type(numbers) is str:
            numbers = [numbers]

        for number in numbers:
            self.client.messages.create(
                to=number,
                from_=self.TWILIO_PHONE_NUMBER,
                body=text,
            )

        return None


class ResponseAI:
    def __init__(self, number, sheet, text):
        fnumber = format_number(number)

        self.recognized_member = sheet.exist(fnumber)
        self.incoming_text = text
        self.number = fnumber
        self.sheet = sheet
        self.text = ''
        self.log = ''

    def get_response_from_member(self):
        recognized_text = False
        for key in self.sheet.responses:
            if self.incoming_text.lower() == key:
                self.text = self.sheet.messages['response text']
                self.sheet.update_response(self.number, self.sheet.responses[key])
                recognized_text = True

        if self.incoming_text.lower() == 'remove':
            self.text = self.sheet.admin_sheet.messages['removal']
            self.sheet.disable_text(self.number)
        elif not recognized_text:
            self.text = self.sheet.messages['unrecognized response']

    def get_response_from_nonmember(self):
        if self.incoming_text.lower() == 'yes':
            self.text = "That's great! Respond with your name so we can add you to the spreadsheet."
            self.sheet.add_new_member('temp', self.number)
            self.sheet.disable_text(self.number)
        else:
            self.text = self.sheet.messages['first text']

    def add_member_to_spreadsheet(self):
            self.text = self.sheet.messages['new member']
            self.sheet.add_new_member(self.number, self.incoming_text)

    def execute_response(self):
        return self.text

    def recognized_member(self):
        return self.sheet.exist(self.number)


def main():
    sheet = Spreadsheet()
    sheet.debug_flag = True
    
    ai = ResponseAI()
    sheet.ai("15855904906","Devon Jedamski")
    sheet.disable_text("15855904906")


if __name__ == "__main__":
    main()
