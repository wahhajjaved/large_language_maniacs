#!/usr/bin/python3
import base64
import hashlib
import sys
import time
import socket
import os
import struct
from Crypto import Random
from Crypto.Cipher import AES

COMMAND = ''
FILENAME = ''
DEST = ''
CIPHER = ''
KEY = ''
PW = ''
IV = ''

def main():
  global COMMAND
  global FILENAME
  global DEST
  global CIPHER
  global KEY 
  global PW
  global IV
#  print(hashlib.sha256("string".encode()).digest())  # This gives a 32-byte key value
#  print(hashlib.md5("string".encode()).hexdigest()) # This gives a 16-byte key value
#  rand = os.urandom(32)
#  print(hashlib.md5(rand).hexdigest()) # Randomly generate 16-byte key
#  print(os.urandom(32)) # Randomly generate 32-byte key 
#  print(Random.new().read(AES.block_size))

  IV = Random.new().read(AES.block_size)  # This generates a random IV

  if (len(sys.argv) < 4):
    print("Use this application with the following:")
    print("python3 client.py [read/write] filename hostname:port [none|aes128|aes256] key")
    print("You must use at least four of the above arguments, in the specified order")
    sys.exit("Incorrect user input")

  if (sys.argv[4]=='none'):
    COMMAND = str(sys.argv[1])
    FILENAME = str(sys.argv[2])
    DEST = str(sys.argv[3])
    CIPHER = 'none'

  else:
    if(len(sys.argv)==6):
      COMMAND = str(sys.argv[1])
      FILENAME = str(sys.argv[2])
      DEST = str(sys.argv[3])
      CIPHER = str(sys.argv[4])
      PW = str(sys.argv[5])
#      print("Password: " + PW)

    elif(len(sys.argv)==4):
      COMMAND = str(sys.argv[1])
      FILENAME = str(sys.argv[2])
      DEST = str(argv[3])
      CIPHER = 'none'

  # The following code block is used to parse the user input and execute the appropriate functions
  if(COMMAND=="read"):
    if(CIPHER=="none"):
       startClientNone()
    elif(CIPHER=="aes128") or (CIPHER=="aes256"):
      separator = DEST.find(":")
      ipDEST = DEST[0:separator]
      sockDEST = DEST[separator+1:]
      clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      clientSocket.connect((ipDEST,int(sockDEST)))

      recvFileEncryption(COMMAND, FILENAME, CIPHER, PW, 16, clientSocket)
    else:
      sys.exit("Unsupported Cryptography Cipher")
  elif(COMMAND=="write"):
    if(CIPHER=="none"):
       startClientNone()
    elif(CIPHER=="aes128") or (CIPHER=="aes256"):
      separator = DEST.find(":")
      ipDEST = DEST[0:separator]
      sockDEST = DEST[separator+1:]
      clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      clientSocket.connect((ipDEST,int(sockDEST)))

      sendFileEncryption(COMMAND, FILENAME, CIPHER, PW, 16, clientSocket)
    else:
      sys.exit("Unsupported Cryptography Cipher")


def str_to_bytes(data):
  utype = type(b''.decode('utf-8'))
  if isinstance(data, utype):
    return data.encode('utf-8')
  return data

def startClientNone():
  global COMMAND
  global DEST
  global FILE
  global IV
  separator = DEST.find(":")
  ipDEST = DEST[0:separator]
  sockDEST = DEST[separator+1:]
  clientSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  clientSocket.connect((ipDEST,int(sockDEST)))

  if(COMMAND=="read"):

    #Send Welcome message
    segment_size = 1024 
    first_message = CIPHER + "\n"
    first_message_length = len(first_message)
    padding = 1024 - first_message_length
    padding_arg1 = str(padding)+"B"
    padded_message = bytes(first_message,'UTF-8') + struct.pack(padding_arg1,*([0]*padding))
    clientSocket.send(padded_message)
    clientSocket.send(IV)
    print("Hi server --> sending cipher + IV(nonce) + padding: "+ str(len(padded_message))+" bytes")
    getFileNoEncryption(clientSocket)
 
  elif(COMMAND=='write'):
    
    ## Write data from sys.stdin.buffer byte by byte to stdin
    payload_file = "temp_data"
    with open(payload_file,'wb+') as f:
    
      while True: 
        data = sys.stdin.buffer.read(1)
        if not data:
          break
        f.write(data) 
    f.close()

    #Send welcome message to the server. message = (CIPHER,IV) | 1024 bytes
    first_message = CIPHER + "\n"
    first_message_length = len(first_message)
    padding = 1024 - first_message_length
    padding_arg1 = str(padding)+"B"
    padded_message = bytes(first_message,'UTF-8') + struct.pack(padding_arg1,*([0]*padding))
    clientSocket.send(padded_message)
    clientSocket.send(IV)
    print("Hi server --> sending cipher + IV(nonce) + padding: "+ str(len(padded_message))+" bytes")

    segment_size = 1024
    sendFileNoEncryption(payload_file,segment_size,clientSocket)
    
  else:
    print("I don't know how to " + COMMAND)

def getFileNoEncryption(clientSocket):

  #Send request header to the server
  sendHeaderNoEncrypt(COMMAND,FILENAME,clientSocket)
  
  #get file_size from the server first
  segment_size = 1024
  temp_data = clientSocket.recv(segment_size)
  array = temp_data.split(b". .") 
  file_size = int(array[0])

  #Now recieve payload from the server, and push to sys.stdout
  #1024 bytes at a time
  bytes_written = 0
  while(bytes_written < file_size):
    data = clientSocket.recv(segment_size)
    if not data:
      break
    if len(data) + bytes_written > file_size:
      data = data[:file_size-bytes_written]
    bytes_written += len(data)
    sys.stdout.buffer.write(data)

  print("OK")
      
def sendFileNoEncryption(payload_file,segment_size,clientSocket):
  global COMMAND
  global DEST
  global FILENAME
 
  #Send header before payload
  sendHeaderNoEncrypt(COMMAND,FILENAME,clientSocket)
    
  with open(payload_file,'rb') as f:
    
    # Get payload size, and send to server so it knows how much data to recieve
    payload_size = len(f.read())
    print("Client sending file of size: " + str(payload_size) + " bytes")  ## TEST
    clientSocket.send( bytes(str(payload_size)+'. .','UTF-8'))

    #reset read pointer on payload file, and send file 1024 bytes at a time
    f.seek(0) 
    data = f.read(segment_size)
    while data:
      clientSocket.send(data)
      data = f.read(segment_size)
    f.close()

def sendHeaderNoEncrypt(COMMAND,FILENAME,clientSocket):
  header = bytes(COMMAND+"\n"+FILENAME+"\n","UTF-8")
  clientSocket.send( header )

def sendFileEncryption(COMMAND, FILENAME, CIPHER, PW, segment_s, clientSocket):
  global IV
  pad = lambda s: s + (segment_s - len(s) % segment_s) * chr(segment_s - len(s) % segment_s) # This defines a pad function that can be called with pad(string)
  cheader = CIPHER + "\n" 
  padding = 1024 - len(cheader)
  padded_header = bytes(cheader,'UTF-8') + struct.pack(str(padding)+"B",*([0]*padding))
  clientSocket.send(padded_header) # Send crypto header, containing crypto mode
  clientSocket.send(IV)

# The following code counts the size of the file it is about to send
  fileSize = 0
  tempFile = "temp_dat"

  with open(tempFile,'wb+') as f:
    while(True):
      chunk = sys.stdin.buffer.read(1)
      if not chunk:
        break
      f.write(chunk)
      fileSize += 1
    f.close() 

#  unpad = lambda s : s[0:-ord(s[len-1:])] # This defines an unpad function that can be called with unpad(decryptedString)
  
  if(CIPHER=="aes128"): # This block reads from stdin in 16 byte segments, encrypts and sends them as they are read
    key = hashlib.md5(PW.encode()).hexdigest() # Generates a 16-byte key from the given password
    encryptor = AES.new(key,AES.MODE_CBC,IV) # The encyptor keeps track of the IV as it changes form chunk to chunk

#    c_checker = "HELLO"
#    pad(c_checker)
#    crypto_checker = 
         
    c_header = COMMAND + "\n" + FILENAME + "\n" + str(fileSize) + ". ."  # The crypto header needs to be filled with the command, filename, and filesize 
    crypt_header = pad(c_header)
    crypto_header = encryptor.encrypt(crypt_header.encode("UTF-8"))
    clientSocket.send(crypto_header)
    
    with open(tempFile,'rb') as inload:
      while(True):
        chunk = inload.read(segment_s)
        if(len(chunk)==0):
          break
        elif(len(chunk) % segment_s != 0):
          dchunk = b'\x00' * (segment_s - len(chunk) % 16)
          chunk = b"".join([chunk,dchunk])
        if(len(chunk) % segment_s == 0):
          encrypted = encryptor.encrypt(chunk)
          clientSocket.send(encrypted)

  elif(CIPHER=="aes256"): # This block reads from stdin in 16 byte segments, encrypts and sends them as they are read
    key = hashlib.sha256(PW.encode()).digest() # Generates a 32-byte key from the given password
    encryptor = AES.new(key,AES.MODE_CBC,IV) # The encyptor keeps track of the IV as it changes form chunk to chunk

    c_header = COMMAND + "\n" + FILENAME + "\n" + str(fileSize) + ". ."  # The crypto header needs to be filled with the command, filename, and filesize 
    crypt_header = pad(c_header)
    crypto_header = encryptor.encrypt(crypt_header.encode("UTF-8"))
    clientSocket.send(crypto_header)

    with open(tempFile,'rb') as inload:
      while(True):
        chunk = inload.read(segment_s)
        if(len(chunk)==0):
          break
        elif(len(chunk) % 16 != 0):
          dchunk = b'\x00' * (16 - len(chunk) % 16)
          chunk = b"".join([chunk,dchunk])
        if(len(chunk) % 16 == 0):
          encrypted = encryptor.encrypt(chunk)
          clientSocket.send(encrypted)
    
def recvFileEncryption(COMMAND, FILENAME, CIPHER, PW, segment_s, clientSocket):
  global IV
  pad = lambda s: s + (segment_s - len(s) % segment_s) * chr(segment_s - len(s) % segment_s) # This defines a pad function that can be called with pad(string)
  unpad = lambda s : s[0:-ord(s[len-1:])] # This defines an unpad function that can be called with unpad(decryptedString)
  cheader = CIPHER + "\n" 
  padding = 1024 - len(cheader)
  padded_header = bytes(cheader,'UTF-8') + struct.pack(str(padding)+"B",*([0]*padding))
  clientSocket.send(padded_header) # Send crypto header, containing crypto mode
  clientSocket.send(IV)

  if(CIPHER == "aes128"):
    key = hashlib.md5(PW.encode()).hexdigest()
    encryptor = AES.new(key,AES.MODE_CBC,IV)
    decryptor = AES.new(key,AES.MODE_CBC,IV)

    c_header = COMMAND + "\n" + FILENAME + "\n" + str(128) + ". ."  # The crypto header needs to be filled with the command, filename, and filesize 
    crypt_header = pad(c_header)
    crypto_header = encryptor.encrypt(crypt_header.encode("UTF-8"))
    clientSocket.send(crypto_header)

    decryptHeader = ''
    while True:
      chunk = clientSocket.recv(segment_s)
      if len(chunk) > 0:
        decryptedByteString = decryptor.decrypt(chunk)
        decryptedString = decryptedByteString.decode("UTF-8") #decodes the bytestring segment into a string
        decryptHeader = decryptHeader + decryptedString
        if (decryptHeader.find(". .") != -1):
          index = decryptHeader.find(". .") 
          decryptHeader = decryptHeader[:index]
          break
    header_array = decryptHeader.split("\n")
    verify = header_array[0]
    fileSize = int(header_array[1])

    if(verify == "False"):
      sys.exit("File does not exist")

    bytes_written = 0
    while(bytes_written < fileSize):
      data = clientSocket.recv(segment_s)
      if not data:
        break
      decryptedData = decryptor.decrypt(data)
      #bytes_written += len(data)
      if len(data) + bytes_written > fileSize:
      #if(bytes_written > fileSize):
        decryptedData = decryptedData[:fileSize - segment_s]
      bytes_written += len(data)
      sys.stdout.buffer.write(decryptedData)
  

  elif(CIPHER == "aes256"):
    key = hashlib.sha256(PW.encode()).digest()
    encryptor = AES.new(key,AES.MODE_CBC,IV)
    decryptor = AES.new(key,AES.MODE_CBC,IV)

    c_header = COMMAND + "\n" + FILENAME + "\n" + str(256) + ". ."  # The crypto header needs to be filled with the command, filename, and filesize 
    crypt_header = pad(c_header)
    crypto_header = encryptor.encrypt(crypt_header.encode("UTF-8"))
    clientSocket.send(crypto_header)

    rcHeader = clientSocket.recv(segment_s)
    ruHeader = int(decryptor.decrypt(rcHeader))

    bytes_written = 0
    while(True):
      data = clientSocket.recv(segment_s)
      if not data:
        break
      decryptedData = decryptor.decrypt(data)
      bytes_written += segment_s
      if(bytes_written > ruHeader):
        decryptedData = decryptedData[:ruHeader % segment_s]
        sys.stdout.buffer.write(decryptedData)
      sys.stdout.buffer.write(decryptedData)

if __name__ == '__main__':
  main()

