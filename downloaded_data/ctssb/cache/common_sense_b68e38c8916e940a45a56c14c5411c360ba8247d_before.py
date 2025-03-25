import io
import re
import bs4
import arrow
import requests

from optparse import make_option
from urllib.parse import urljoin

from django.core.management.base import BaseCommand

from consultations.models import Consultation
from consultations.enums import ConsultationStateEnum
from consultations.pdfutils import pdf_to_text


class Command(BaseCommand):

    option_list = BaseCommand.option_list + (
        make_option(
            '--get-documents',
            action='store_true',
            default=False,
            dest='get_documents',
            help='Get documents',
        ),
    )

    session = requests.Session()

    def handle(self, *args, **options):
        get_documents = options.get('get_documents')
        for consultation in self.get_consultations(get_documents):
            Consultation.objects.get_or_create(
                url=consultation['url'],
                defaults=consultation,
            )

    def get_consultations(self, get_documents=False):
        total_pages = 1
        current_page = 1

        while current_page <= total_pages:
            print("Scraping page: %d" % current_page)

            response = self.session.get(
                'https://www.gov.uk/government/publications.json',
                params={
                    'publication_filter_option': 'consultations',
                    'page': current_page,
                }
            )

            response.raise_for_status()
            data = response.json()

            for publication in data['results']:
                consultation_data = self.parse_publication(
                    publication,
                    response.url,
                    get_documents=get_documents,
                )

                if consultation_data:
                    yield consultation_data

            current_page += 1
            total_pages = data['total_pages']

    def parse_publication(self, publication, base_url, get_documents=False):
        if publication['type'] != 'consultation':
            return None

        consultation_state = \
            ConsultationStateEnum.DISPLAY_TYPE_TO_ENUM_TYPE.get(
                publication['display_type']
            )

        if not consultation_state:
            return None

        print("  Scraping consultation:", publication['title'])

        publication_url = urljoin(base_url, publication['url'])
        print("    URL:", publication_url)

        root = bs4.BeautifulSoup(publication['organisations']).find('abbr')
        try:
            organisation = root.attrs['title']
            organisation_abbr = root.text
        except:
            organisation = ''
            organisation_abbr = ''

        root = bs4.BeautifulSoup(self.session.get(publication_url).content)

        closing_date_str = root.select('.closing-at')[0]['title']
        closing_date = arrow.get(closing_date_str).to('utc').datetime

        try:
            summary = root.find(
                'div', class_='consultation-summary-inner'
            ).find('p').text
        except:
            summary = ''

        contact_email = ''
        contact_address = ''
        response_form = ''
        response_document = ''

        response_formats = root.find('section', id='response-formats')
        if response_formats:
            try:
                contact_email = response_formats.find('dd', class_ = 'email').find('a').text
            except:
                pass
            try:
                contact_address = '\n'.join(response_formats.find('dd', class_ = 'postal-address').stripped_strings)
            except:
                pass
            try:
                response_form = response_formats.find(class_='response-form').find('a').attrs['href']
            except:
                pass
            try:
                response_document = response_formats.find(class_='online').find('a').attrs['href']
            except:
                pass
        # Try dealing with malformed documents
        else:
            try:
                contact_email = root.find(text = re.compile(r'By email:')).parent.find(href = re.compile(r'mailto:')).text
            except:
                pass
            try:
                contact_address = '\n'.join(root.find(class_='address').stripped_strings)
            except:
                pass

        pub = {
            'url': publication_url,
            'title': publication['title'],
            'state': consultation_state,
            'closing_date': closing_date,
            'last_update': arrow.get(publication['public_timestamp']).to('utc').datetime,
            'organisation': organisation,
            'organisation_abbr': organisation_abbr,
            'contact_email': contact_email,
            'contact_address': contact_address,
            'summary': summary,
            'response_form': response_form,
            'response_document': response_document,
        }

        if get_documents:
            documents = root.find('h1', text=re.compile(r'Documents'))
            if documents:
                documents = documents.parent.parent.findAll(
                    'section', class_='attachment',
                )

                document_raw_text = ""

                for document in documents:
                    document_type = document.find(
                        'p', class_='metadata',
                    ).find(
                        'span', class_='type'
                    ).text

                    document_url = urljoin(
                        base_url,
                        document.find(
                            'h2', class_='title',
                        ).find('a').attrs['href']
                    )

                    document_name = document.find(
                        'h2', class_='title',
                    ).find('a').text

                    print("      Scraping document:", document_name)
                    print("        URL:", document_url)

                    if document_type == 'PDF':
                        try:
                            content = self.session.get(document_url).content
                            with io.BytesIO(content) as pdf_file:
                                document_raw_text += pdf_to_text(pdf_file)
                        except ValueError:
                            print("Invalid PDF")

                pub['raw_text'] = document_raw_text

        return pub
