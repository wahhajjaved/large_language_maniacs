import codecs
from collections import OrderedDict
import logging
import requests

from .model_interface import CachedResult, User

import bs4

logger = logging.getLogger(__name__)

class ParsingException(Exception):
    def __init__(self, public_message):
        super(ParsingException, self).__init__(public_message)
        self.public_message = public_message


class Web(object):
    URL = "http://www.empresas.bancochile.cl/cgi-bin/cgi_cpf?rut1=60910000&dv1=1&canal=BCW&tipo=2&BEN_DIAS=90&mediopago=99&rut2=%s&dv2=%s"

    # Tipos de pagina
    EXPECTED = 1
    CLIENTE = 2
    NO_PAGOS = 3
    INTENTE_NUEVAMENTE = 4

    def __init__(self, rut, digito):
        self.rut = rut
        self.digito = digito
        self.raw_page = ""
        self.results = None
        self.url = self.URL % (self.rut, self.digito)

    def get_results(self):
        # This if is only for testing purposes, if the page was loaded do not download it.
        if not self.raw_page:
            self.download()
        return self.parse()

    def get_parsed_results(self, telegram_user_id):
        """

        :param telegram_user_id:
        :return: (str, boolean) - (result, returned_from_cache)
        """
        user_id = User.get_id(telegram_user_id)
        result = CachedResult.get(user_id, self.rut)
        if result:
            logger.info("Using cache results.")
            return result, True
        logger.info("Querying the bank page")
        results = self.get_results()
        if self.page_type != self.EXPECTED:
            result = "".join(results)
        else:
            parsed_result = []
            for r in results:
                this_result = []
                for k, v in r.items():
                    this_result.append("%s: %s\n" % (k.strip(), v.strip()))
                parsed_result.append("".join(this_result).rstrip("\n"))
            result = "\n\n".join(parsed_result)

        try:
            CachedResult.update(self.rut, user_id, result)
        except Exception as e:
            logging.exception("parsed_results")
        finally:
            return result, False

    def download(self):
        try:
            r = requests.get(self.url)
        except requests.exceptions.RequestException as e:
            logger.error("Connection error:%s" %e)
            raise ParsingException("Error de conexion, (probablemente) estamos trabajando para solucionarlo.")
        if(r.status_code != 200):
            logger.warn("Couldn't get the page, error %s:%s" % (r.status_code,
                                                                r.reason))
            raise ParsingException("Error de conexion, (probablemente) estamos trabajando para solucionarlo.")

        self.raw_page = r.text

    """ Testing purposes."""
    def load_page(self, path):
        with codecs.open(path, "r", encoding='utf-8', errors='ignore') as f:
            self.raw_page = f.read()


    def parse(self):
        soup =  bs4.BeautifulSoup(self.raw_page, "html.parser")
        #TODO esto es horrible, factorizar de alguna forma brillante
        try:
            self.results = self._parse_expected(soup)
            self.page_type = self.EXPECTED
            logger.info("Parseada [%s]", self.page_type)
            return self.results
        except Exception:
            pass

        try:
            self.results = self._parse_clientes(soup)
            self.page_type = self.CLIENTE
            logger.info("Parseada [%s]", self.page_type)
            return self.results
        except Exception as e:
            pass

        try:
            self.results = self._parse_no_pagos(soup)
            self.page_type = self.NO_PAGOS
            logger.info("Parseada[%s]", self.page_type)
            return self.results
        except Exception as e:
            pass

        try:
            self.results = self._parse_error_intente_nuevamente(soup)
            self.page_type = self.INTENTE_NUEVAMENTE
            logger.info("Parseada[%s]", self.page_type)
            return self.results
        except Exception as e:
            pass
        logger.error("Error parsing, no se pudo parsear la pagina [%s]: %s", self.url, self.raw_page)
        raise ParsingException("Nadie ha escrito un parser para esta pagina aun :( reportalo en github!")

    def _parse_expected(self, soup):
        table = soup.body.form.find_all('table')[1].find_all('tr')[5].find_all('tr')
        if table[0].td.text != '\nFecha de Pago':
            raise ParsingException("Probablemente no es una pagina expected!")
        resultados = []
        for i in range(1, len(table) - 1):
            data = table[i].find_all('td')
            resultados.append(OrderedDict([ ('Fecha de Pago', data[0].text.strip('\n'))
                                          , ('Medio de Pago', data[1].text.strip('\n'))
                                          , ('Oficina/Banco', data[2].text.strip('\n'))
                                          , ('Estado', data[3].text.strip('\n'))
                                          ]))
        return resultados

    def _parse_clientes(self, soup):
        if "Para clientes del Banco de Chile" not in self.raw_page:
            raise ParsingException("Probablemente no es una pagina de clientes")
        return [("Eres cliente del banco?, no es posible consultar tu informacion por la interfaz publica.")]

    def _parse_no_pagos(self, soup):
        if "Actualmente no registra pagos a su favor" not in self.raw_page:
            raise ParsingException("Probablemente no es una pagina sin pagos")
        return [("Actualmente no registras pagos a tu favor.")]

    def _parse_error_intente_nuevamente(self, soup):
        if "Por ahora no podemos atenderle." not in self.raw_page:
            raise ParsingException ("Probablemente no es una de error intente nuevamente")
        return [("La pagina del banco tiene un error y dice que intentes nuevamente. "
                 "Intenta nuevamente en unas horas")]
