#!/usr/local/bin/python
# -*- coding: utf-8 -*-

import socket, ssl, pem
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
import subprocess
from helper import which, logger, print_h1, print_h2
from certificate import Certificate

class Server:

    x509_certs=[]
    certs=[]
    number_of_certs=0
    cipher_suites=[["TLS_DHE_RSA_WITH_AES_128_CBC_SHA256","DHE-RSA-AES128-SHA256","RSA","OPTIONAL"  ],
      ["TLS_DHE_RSA_WITH_AES_256_CBC_SHA256","DHE-RSA-AES256-SHA256", "RSA", "OPTIONAL" ],
      ["TLS_DHE_RSA_WITH_AES_128_GCM_SHA256","DHE-RSA-AES128-GCM-SHA256","RSA", "OPTIONAL"  ],
      ["TLS_DHE_RSA_WITH_AES_256_GCM_SHA384" ,"DHE-RSA-AES256-GCM-SHA384","RSA", "OPTIONAL"  ],
      ["TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA256","ECDHE-RSA-AES128-SHA256","RSA","MUST"  ],
      ["TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA384","ECDHE-RSA-AES256-SHA384","RSA", "SHOULD"  ],
      ["TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256","ECDHE-RSA-AES128-GCM-SHA256","RSA","MUST"  ],
      ["TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384","ECDHE-RSA-AES256-GCM-SHA384","RSA","SHOULD"  ],
      ["TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA","ECDHE-RSA-AES128-SHA","RSA","OPTIONAL"],
      ["TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA","","RSA","OPTIONAL"], #TODO: Mein Openssl unterstützt diese Cipher gar nicht.
      ["TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA","ECDHE-RSA-AES256-SHA","RSA","OPTIONAL"],
      ["TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA","","RSA","OPTIONAL"],#TODO: Mein Openssl unterstützt diese Cipher gar nicht.
      ["TLS_DHE_RSA_WITH_AES_128_CBC_SHA","DHE-RSA-AES128-SHA","RSA","OPTIONAL"],
      ["TLS_DHE_RSA_WITH_AES_256_CBC_SHA","DHE-RSA-AES256-SHA","RSA","OPTIONAL"],
      ["TLS_DHE_RSA_WITH_AES_128_GCM_SHA","","RSA","OPTIONAL"],#TODO: Mein Openssl unterstützt diese Cipher gar nicht.
      ["TLS_DHE_RSA_WITH_AES_256_GCM_SHA","","RSA","OPTIONAL"],#TODO: Mein Openssl unterstützt diese Cipher gar nicht.
      ["TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA256","ECDHE-ECDSA-AES128-SHA256", "EC", "MUST"],
      ["TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA384","ECDHE-ECDSA-AES256-SHA384","EC", "SHOULD"  ],
      ["TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256" ,"ECDHE-ECDSA-AES128-GCM-SHA256","EC", "MUST"  ],
      ["TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384","ECDHE-ECDSA-AES256-GCM-SHA384","EC", "SHOULD"  ],
      ["TLS_ECDHE_ECDSA_WITH_AES_128_CBC_SHA","ECDHE-ECDSA-AES128-SHA","EC", "OPTIONAL"  ],
      ["TLS_ECDHE_ECDSA_WITH_AES_256_CBC_SHA","ECDHE-ECDSA-AES256-SHA","EC", "OPTIONAL"  ],
      ["TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA","","EC", "OPTIONAL"  ],#TODO: Mein Openssl unterstützt diese Cipher gar nicht.
      ["TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA","","EC", "OPTIONAL"  ]]#TODO: Mein Openssl unterstützt diese Cipher gar nicht.


    def __init__(self, hostname, port, ca_file, certificates):
      self.hostname = hostname
      self.port=port
      if ca_file is not None:
          self.ca_file=ca_file
      else:
          self.ca_file="/usr/local/etc/openssl/cert.pem"

      self.certificates= certificates
      self.protocols=[
      [ssl.PROTOCOL_TLSv1, "TLSv1", False],
      [ssl.PROTOCOL_TLSv1_1,"TLSv1.1", False],
      [ssl.PROTOCOL_TLSv1_2,"TLSv1.2",True]]

    def test_server_for_protocol(self):
        print_h1("Test die Anforderungen aus Kapitel 2.3")
        print_h2("Anforderung 2.3.1 Überpreufe die unterstuetzten Protokolle:")
        self.test_supported_protocols()

        print_h2("Anforderung 2.3.2/2.3.3/2.3.4 Überpreufe die unterstuetzten Cipher-Suites:")
        logger.info("Im Folgenden werden die vom Server unterstützten Cipher-Suites gelistet.")
        logger.info("Unerlaubte Cipher-Suites werden direkt markiert. Allerdings muss aktuelle manuell geprpft werden ")
        logger.info("ob die verpflichtenden cipher-suites umgesetzt sind. Außerdem muss die Priorität der  ")
        logger.info("Cipher Suites aktuell manuell geprüft werden.")

        self.test_supported_cipher_suites()

        print_h1("Teste die Anforderungen aus Kapitel 2.4")
        print_h2("Anforderung 2.4.1 Überprüfe die ephemeralen Parameter")
        self.test_key_exchange()

        print_h1("Teste die Anforderungen aus Kapitel 2.5")
        print_h2("Anforderung 2.5.1 Überpruefe Session Renegotiation")
        self.test_session_renegotiation()

        print_h2("Anforderung 2.5.2 Überpruefe TLS Kompression")
        self.test_tls_compression()

        print_h2("Anforderung 2.5.3 Überpruefe auf Heartbeat-Extension")
        self.test_heartbeat_extension()

        print_h2("Anforderung 2.5.4 Überpruefe auf truncated_hmac-Extension")
        self.test_truncated_hmac_extension()

    def test_supported_protocols(self):
        #Kritierum 2.3.1
        for protocol in self.protocols:
            try:
                context = ssl.SSLContext(protocol[0])
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = True
                context.load_default_certs()

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ssl_sock = context.wrap_socket(s, server_hostname=self.hostname)

                ssl_sock.connect((self.hostname, self.port))
                if protocol[2]:
                    logger.info("Server unterstützt " + protocol[1] + " Dieses Verhalten ist OK")
                else:
                    logger.error("Server unterstützt " + protocol[1] + " Das sollte nicht der Fall sein")

            except ssl.SSLError as err:
                if "SSLV3_ALERT_HANDSHAKE_FAILURE" in err.args[1]:
                    if not protocol[2]:
                        logger.info("Server unterstützt NICHT " + protocol[1] + " Dieses Verhalten ist OK")
                    else:
                        logger.error("Server unterstützt NICHT" + protocol[1] + " Das sollte nicht der Fall sein")


    def test_supported_cipher_suites(self):
    #Anforderung 2.3.2/2.3.3/2.3.4
    #TODO: Funktioniert aktuell nur mit RSA
        crypto_type="RSA"
        openssl_cmd_getcert="openssl ciphers"
        proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()

        out = out.replace('\n', '').replace('\r', '')
        all_ciphers=out.split(":")
        all_ciphers = filter(None, all_ciphers)
        all_ciphers = filter(None, all_ciphers)

        for cipher in all_ciphers:
            try:
                cipher_list = [x for x in self.cipher_suites if x[1] == cipher and x[2]==crypto_type ]
                allowed=should=must=optional=False

                if len(cipher_list)==0:
                    allowed=False
                elif cipher_list[0][3]=="MUST":
                    must=True
                    allowed=True
                elif cipher_list[0][3]=="SHOULD":
                    should=True
                    allowed=True
                elif cipher_list[0][3]=="OPTIONAL":
                    optional=True
                    allowed=True

                context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                context.set_ciphers(cipher)
                context.verify_mode = ssl.CERT_REQUIRED
                context.check_hostname = True
                context.load_default_certs()

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                ssl_sock = context.wrap_socket(s, server_hostname=self.hostname)
                ssl_sock.connect((self.hostname, self.port))
                priority= ssl_sock.cipher()[2]

                if not allowed:
                    logger.error("Server unterstützt verbotene cipher-suite: " + cipher + " mit Priorität" + str(priority) +  " Das sollte nicht der Fall sein")

                elif must or should or optional:
                    logger.warning(cipher + " wird unterstützt mit Priorität" + str(priority) + ". Bitte in der Checkliste prüfen.")


            except ssl.SSLError as err:
                if "SSLV3_ALERT_HANDSHAKE_FAILURE" in err.args[1] or "NO_CIPHERS_AVAILABLE" in err.args[1]:
                    if must:
                        logger.error(cipher + " wird nicht unterstützt aber von der Checkliste gefordert")
                    else:
                        logger.info(cipher + " wird nicht unterstützt. Das scheint OK zu sein.")

    def test_key_exchange(self):
        #Anforderung 2.4.1
        openssl_cmd_getcert="echo | openssl s_client -msg -connect "+ self.hostname +":"+ str(self.port)+ " | grep 'ServerKey' -A 5"

        proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()
        logger.warning("Die Nachricht muss leider noch ausgewertet werden. Das ist das Einzige, was noch nicht funktioniert")
        logger.warning( out)
        #http://crypto.stackexchange.com/questions/11310/with-openssl-and-ecdhe-how-to-show-the-actual-curve-being-used


    def test_session_renegotiation(self):
    #Anforderung 2.5.1
        openssl_cmd_getcert="sslyze --regular "  + self.hostname +":"+str(self.port)

        proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()

        if "Client-initiated Renegotiation:    OK - Rejected" in out:
            logger.error("Server unterstützt unsichere session renegotiation. Das sollte nicht der Fall sein.")
        else:
            logger.info("Server unterstützt unsichere session renegotiation nicht. Das ist so OK")

        if "Secure Renegotiation:              OK - Supported" in out:
            logger.error("Der Server unterstützt die sichere Form der renegotiaion. Das sollte nicht der Fall sein.")
        else:
            logger.info("Der Server unterstützt die sichere Form der renegotiaion nicht. Das ist so OK.")


    def test_tls_compression(self):
    #Anforderung 2.5.2

        openssl_cmd_getcert=" echo "R" | openssl s_client -CAfile "+self.ca_file+" -connect "+ self.hostname +":"+str(self.port)
        proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()

        if "Compression: NONE" in out:
            logger.info("Server unterstützt keine TLS compression. Das ist das erwartete Verhalten.")
        else:
            logger.error("Server unterstützt TLS compression. Das sollte nicht der Fall sein.")


    def test_heartbeat_extension(self):
        #Anforderung 2.5.3
        #Thanks to  https://www.feistyduck.com/library/openssl-cookbook/online/ch-testing-with-openssl.html

        openssl_cmd_getcert=" echo Q | openssl s_client -CAfile "+ self.ca_file + " -connect "+ self.hostname +":"+str(self.port)+" -tlsextdebug"
        proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()

        if "heartbeat" in out:
            logger.error("Server unterstützt die Heartbeat-extension. Das sollte nicht der Fall sein.")
        else:
            logger.info("Server unterstützt die Heartbeat-Extension nicht. Das ist so OK.")

    def test_truncated_hmac_extension(self):
    #Anforderung 2.5.4
        openssl_cmd_getcert=" echo Q | openssl s_client -CAfile "+ self.ca_file +" -connect "+ self.hostname +":"+str(self.port)+" -tlsextdebug"
        proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        (out, err) = proc.communicate()


        #TODO: wir brauchen mal einen Server mit einer truncated_hmac extension um zu sehen, ob das hier funktioniert.
        if "truncated_hmac" in out:
            logger.error("Server unterstützt die truncated_hmac extension. Das sollte nicht der Fall sein.")
        else:
            logger.info("Server unterstützt die truncated_hmac extension nicht. Das ist OK.")

    def read_certificates(self,server_certificates):
        logger.info("------------------------------------------------------------------------------------")
        logger.info("Rufe die Zertifkate für die weiteren Tests ab")
        logger.info("------------------------------------------------------------------------------------")
        try:
            if server_certificates is None:
                openssl_cmd_getcert="echo 'Q' | openssl s_client -connect "+ self.hostname +":"+str(self.port)+ " -showcerts  | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p'"
                proc = subprocess.Popen([openssl_cmd_getcert], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
                (out, err) = proc.communicate()
                tmp_certs = pem.parse(out)
            else:
                tmp_certs=pem.parse_file(server_certificates)

            logger.info(str(len(tmp_certs)) +" Zertifikate wurden empfangen bzw. eingelesen.")

            for crt in tmp_certs:
                self.x509_certs.append(load_pem_x509_certificate(str(crt).encode('ascii','ignore'),default_backend()))

            for x509 in self.x509_certs:
                self.certs.append(Certificate(x509,self.ca_file))

        except Exception as err:
            print err
