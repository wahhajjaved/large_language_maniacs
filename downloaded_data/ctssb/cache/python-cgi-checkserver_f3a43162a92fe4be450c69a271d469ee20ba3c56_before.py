import socket
import sys
import thread
import math
import subprocess

BUFFER_SIZE = 4096
IP = 127.0.0.1
if len(sys.argv) < 2:
  print "Porta não encontrada"
else:
    PORT = int(sys.argv[1])

def execute(cmd): # Execucao dos comandos
        if(cmd == 1):
            return subprocess.check_output(['ps'])
        elif(cmd == 2):
            return subprocess.check_output(['df'])
        elif(cmd == 3):
            return subprocess.check_output(['finger'])
        elif(cmd == 4):
            return subprocess.check_output(['uptime'])
        else:
            return 'Erro'


def conv(d): # Trabalha em cima de um binario, jogando para uma string
            dados = (map(bin, bytearray(d)))

            for x in range(len(dados)):
                    dados[x] = dados[x] [2:].rjust(8, '0')

            dados = ''.join(dados)

            return dados


def lerPacote(p): #Fazer a leitura de cada parte do pacote
    Version =  p[0:4]
    IHL = p[4:8]
    TOS = p[8:16]
    Lenght = p[16:32]
    FragID = p[32:48]
    Flags = p[48:51]
    FragOffset = p[51:64]
    TTL = p[64:72]
    Protocol = p[72:80]
    HeaderChecksum = p[80:96]
    SourceAddr = p[96:128]
    DestinationAddr = p[128:160]
    Options = p[160:]

    return Protocol, TTL

def montaPacote(cmd, t): # Montar o pacote juntando cada parte

    Version =  '0010'
    IHL = '0101'
    TOS = '00000000'
    FragID = '0000000000000000'
    Flags = '111'
    FragOffset = '0000000000000'
    TTL = bin(int(t, 2)-1) [2:].rjust(8, '0')
    Protocol = '00000000'
    HeaderChecksum = '0000000000000000'

    t = TCP_IP.split(".")
    for i in range(len(t)):
        t[i] = (bin(int(t[i]))) [2:].rjust(8, '0')

    SourceAddr = ''.join(t)
    DestinationAddr = ''.join(t)

    Dat = conv(execute(int(cmd, 2)))

    tamPacote = (Version + IHL + TOS + Length + FragID + Flags + FragOffset + TTL + Protocol + HeaderChecksum \
    + SourceAddr + DestinationAddr + Dat)

    word32 = int(math.ceil(float(tamPacote) / 32.0))
    Length = ''.join(bin(word32 * 32)) [2:].rjust(16, '0')

    p = (Version + IHL + TOS + Length + FragID  + Flags + FragOffset + TTL + Protocol + HeaderChecksum \
    + SourceAddr + DestinationAddr + Dat)

    return p

def func(connection):
    data = connection.recv(BUFFER_SIZE)
    if data:
        comando, aux_t = lerPacote(data)
        pacote = montaPacote(comando, aux_t)
        print "OK"
        connection.send(pacote)

    connection.close()

c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
c.bind((IP, PORT))
c.listen(300)

while True:
        connect, addr = c.accept()
        print 'Addres = ', addr
        thread.start_new_thread(func, (connect,))
