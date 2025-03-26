import RPi.GPIO as GPIO

import send_mail
import config

cfg = config.get_config()
pin = cfg['raspberry']['pin']

def pi_listen(callback):
	GPIO.setmode(GPIO.BOARD)
	GPIO.setup(pin, GPIO.IN, pull_up_down = GPIO.PUD_DOWN)
	GPIO.add_event_detect(pin, GPIO.RISING, callback = callback, bouncetime = 300)

def handler_listen(channel):		
	if GPIO.input(pin):
		print('Movement!')
		sent = send_mail.send(cfg)

		if sent:
			print ('Mail sent.')
		else:
			print ('An error occured')

def main():
	pi_listen(pin, handler_listen)

	while True:
			pass

main()