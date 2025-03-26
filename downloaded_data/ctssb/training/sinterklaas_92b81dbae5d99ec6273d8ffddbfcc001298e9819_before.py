#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Helper script for "Secret Santa"-like events. """

import argparse
import configparser
import copy
import getpass
import random
import smtplib

class Person:
    def __init__(self, name, email):
        self.name = name
        self.email = email
        self.target = None
    def __str__(self):
        return "<%s: %s>" % (self.name, self.email)
    def __repr__(self):
        return "<%s: %s>" % (self.name, self.email)

def parse_arguments():
    ''' Define and parse command line arguments '''
    parser = argparse.ArgumentParser(description='Random Secret Santa assignements \
                                                  and email sending.')
    parser.add_argument('action', metavar='action',
                        type=str, nargs='+',
                        choices=['test', 'execute'],
                        help='the action to perform')
    return parser.parse_args()

def interpret_arguments(args):
    ''' Warn the user if test mode is off.
        Return whether test mode is enabled '''
    if 'test' in args.action:
        test = True
    else:
        print('/!\\ Warning /!\\')
        print('This will perform the final draw and send out emails to everyone.')
        print('Are you sure you want to continue?')
        response = input('[y/n]')
        if response is not 'y':
            print('No action performed, exiting')
            exit()
        else:
            test = False
    return test

def read_config():
    ''' Read the config.ni file '''
    config = {
        'participants' : [],
    }
    parser = configparser.ConfigParser()
    parser.optionxform = str # don't convert keys to lower-case
    if not parser.read('config.cfg', encoding='utf-8'):
        print('-- Error: could not find config.cfg file, exiting.')
        exit()
    config['participants'] = [Person(name, email) for (name, email) in list(parser['Participants'].items())]
    return config

def draw(people):
    ''' Draw Secret Santas '''
    print("--- Draw in progress ---")
    print("{} people are in the list:".format(len(people)))
    for person in people: print(person)

    # Create a randomized version of the list of people
    randomized_people = copy.deepcopy(people)
    random.shuffle(randomized_people)
    
    # Each person's target is their successor in the randomized list
    for i, person in enumerate(randomized_people):
        person.target = randomized_people[(i+1) % len(randomized_people)]

    print("--- Draw finished ---")
    for person in randomized_people: print("{} picked {}".format(person.name, person.target.name))

    return randomized_people

def notify(people):
    ''' Notify participants by email '''
    print("--- Sending emails ---")
    # Ask sender email and password
    email = input("Sender email:")
    password = getpass.getpass("password:")

    try:
        for person in people:
            # Create message
            msg = ("From: %s\r\nTo: %s\r\nSubject: Mail automatique de tirage au sort pour la Saint-Nicolas\r\n\r\n" % (email, person.email))
            msg += "Bonsoir " + person.name + ",\nL'ordinateur a parlé, tu dois offrir un cadeau à " + person.target.name + ".\n"
            msg += "Merci de conserver ce message, il ne sera délivré aucun duplicata du fait de sa génération automatique au moment du tirage au sort.\n\n"
            msg += "Rappel des modalités:\n"
            msg += "\t- RDV le samedi 16 décembre chez Lolo (9 rue de la Piquetière)\n"
            msg += "\t- prix max du cadeau: 15 euros\n"
            msg += "\t- l'emballage doit être original, si possible en rapport avec le cadeau ou la personne\n"
            msg += "\t- un poème devra être joint au tout, idéalement aussi en rapport avec le cadeau ou la personne\n"
            msg += "\t- suite à une remarque pertinente de Pillou il y a quatre ans et dans un soucis d'ouverture culturelle, les Haiku seront tolérés\n"
            msg += "\n\n"
            msg += "Ceci est un message automatique, merci de ne pas y répondre sous risque de dévoiler votre cible à l'organisateur.\n"
            msg += "Pour toute réclamation ou compliment sur la qualité ce système de tirage au sort innovant, merci d'ouvrir un ticket: https://github.com/fvarose/sinterklaas/issues/new"

            # Send the email
            server = smtplib.SMTP('smtp.gmail.com:587')
            server.starttls()
            server.login(email, password)
            server.sendmail(email, person.email, msg.encode('utf8'))
            server.quit()
            
            print("Mail successfully sent to {}".format(person.name))
    except smtplib.SMTPAuthenticationError as err:
        print("Failed to send e-mail")
        print(err)

def main():
    ''' Main '''
    args = parse_arguments()
    config = read_config()
    test = interpret_arguments(args)

    people = config['participants']
    people = draw(people)
    if not test:
        notify(people)

if __name__ == "__main__":
    main()
