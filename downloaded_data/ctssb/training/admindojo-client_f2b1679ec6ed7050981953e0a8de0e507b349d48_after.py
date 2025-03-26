#!/usr/bin/env python
# -*- coding: utf-8 -*-

import codecs
from configparser import ConfigParser
import json
from termcolor import colored
import subprocess
import os
import shutil


class Config(object):
    path_config_client = ""
    path_result_file = ""
    devMode = False

    def getResultPath(self, path_config_client):
        config = ConfigParser()
        config.read(os.path.normpath(path_config_client))
        return config.get('inspec', 'result_path')

    def getDevMode(self, path_config_client):
        config = ConfigParser()
        config.read(os.path.normpath(path_config_client))
        return config.getboolean('admindojo', 'devmode')

    def __init__(self, path_config_client):
        self.path_config_client = path_config_client
        self.path_result_file = self.getResultPath(path_config_client)
        self.devMode = self.getDevMode(path_config_client)


def update():
    print("To update please....(Update not implemented yet)")


def start():
    if os.path.isfile(os.path.normpath('/vagrant/tmp/admindojo_start.txt')):
        print("Looks like you already started the training and the stopwatch is already running.")
        print("To restart please run from outside VM: 'vagrant destroy; vagrant up' and start again.")
        exit()

    tuptime = subprocess.check_output('tuptime -s | grep life | cut -d: -f2', shell=True)
    uptime = float(tuptime.decode('utf-8').strip())
    with open(os.path.normpath('/vagrant/tmp/admindojo_start.txt'), 'w') as f:
        f.write(str(uptime))
    # todo try catch

    print("Stopwatch is running! Have fun.")


def generateToken(pathToScript):
    token = ""

    if not os.path.isfile(os.path.normpath(pathToScript)):
        print("Sorry - looks like no script to generating the token was found. Please contact us at github.com/admindojo")
        exit()

    token = subprocess.check_output(pathToScript, shell=True, universal_newlines=True)
    return token


def check():
    if not os.path.isfile(os.path.normpath('/vagrant/tmp/admindojo_start.txt')):
        print("Training not started. \nPlease run 'admindojo start' first")
        exit(0)

    print('Start check. This may take a minute..')
    subprocess.call('sudo inspec exec /vagrant/training/ --reporter json:/vagrant/tmp/result.json', shell=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    print()
    print("Check done. Here are your results:")
    print()
    main()


class ResultTraining(object):
    TrainingID = ""

    PlayerImpact = 0.0
    TrainingTimeLimit = 0
    TrainingTotalImpact = 0.0
    PlayerProductivity = 0
    PlayerTimeNeeded = 0.0

    devmode = False

    def getUptime(self):
        with open(os.path.normpath('/vagrant/tmp/admindojo_start.txt'), 'r') as f:
            start = float(f.read())

        tuptime = subprocess.check_output('tuptime -s | grep life | cut -d: -f2', shell=True)
        uptime = float(tuptime.decode('utf-8').strip())

        if uptime > start:
            uptime -= start

        uptime = uptime / 60
        uptime = round(uptime)
        if uptime < 1:
            uptime = 1
        return int(uptime)

    def setTimeLimit(self, time):
        self.TrainingTimeLimit = time
        self.PlayerTimeNeeded = self.getUptime()
        self.PlayerProductivity = round((time / self.PlayerTimeNeeded) * 100)

    def getResult(self):
        if self.TrainingTotalImpact == self.PlayerImpact:
            if self.devmode and self.PlayerProductivity >= 90:
                return True
            if not self.devmode:
                return True
        else:
            return False


def main():
    # config
    path_config_client = '/admindojo/config/client.ini'
    player_config = Config(os.path.normpath(path_config_client))

    player_result = ResultTraining()
    player_result.devmode = player_config.devMode

    # Read JSON data into the datastore variable
    with open(os.path.normpath('/vagrant/tmp/result.json'), 'r') as f:
        result_json = json.load(f)
        # todo try catch

    player_result.TrainingID = result_json['profiles'][0]['name']

    # Calc total values
    calc_time_limit = 0
    for key in result_json['profiles']:
        for control in key['controls']:
            if player_config.devMode:
                calc_time_limit += int(control['tags']['duration'])
            player_result.TrainingTotalImpact += control['impact']

    if player_config.devMode:
        player_result.setTimeLimit(calc_time_limit)

    # Print Result

    print("Training id        : " + result_json['profiles'][0]['name'])
    print("Instructions       : " + 'https://admindojo.org/instructions/' + result_json['profiles'][0]['name'])

    print('---------------------------------------------------------')

    for key in result_json['profiles']:
        for control in key['controls']:
            print(control['title'])
            control_has_failures = False
            for code in control['results']:
                if code['status'] == 'passed':
                    pass_color = 'green'
                    pass_symbol = "✓ [pass]"
                else:
                    pass_color = 'red'
                    pass_symbol = "✗ [fail]"
                    control_has_failures = True
                print('\t' + colored(pass_symbol, pass_color) + " " + code['code_desc'])

            #print()
            if player_config.devMode:
                print('\tEstimated duration: ' + str(control['tags']['duration']) + ' Minutes')
                print('\tPossible score   : ' + str(control['impact']))

            if control_has_failures:
                # print tag help
                print('\t' + colored("This part has failures!", 'red'))
                if str(control['tags']['help']) != "":
                    print('\t\t' + 'See help: ' + str(control['tags']['help']))
            else:
                player_result.PlayerImpact += control['impact']

            print()


    print('---------------------------------------------------------')
    print()
    if player_config.devMode:
        print('Total score to earn : ' + str(player_result.TrainingTotalImpact))
        print('You got             : ' + str(player_result.PlayerImpact))
    if player_config.devMode:
        print()
        print('Your time limit was : ' + str(player_result.TrainingTimeLimit) + ' Minutes')
        print('You needed          : ' + str(player_result.PlayerTimeNeeded) + ' Minutes')

        print('Productivity        : ' + str(player_result.PlayerProductivity) + '%')

    path_training = os.path.normpath(os.path.join(player_config.path_result_file, player_result.TrainingID))

    if player_result.getResult():
        print(colored("You finished the training successfully!", 'green'))
        token = generateToken(os.path.join('/vagrant/training/', player_result.TrainingID, 'token.sh'))
        print("The admindojo.org token is: " + colored(token, 'green'))

    else:
        if player_config.devMode:
            print(colored("Something is missing! Training not completed. \n" +
                          "You need to pass all tests and need a productivity of minimum 90%!", 'red'))
        else:
            print(colored("Something is missing! Training not completed. \n", 'red'))
    print()

    if os.path.isdir(os.path.normpath(os.path.join(path_training, player_config.path_result_file, player_result.TrainingID))):
        overwrite = ""
        while overwrite != "n" and overwrite != "y":
            overwrite = input("A result already exits, do you want to overwrite it with new result?[y|n]: ")

        if overwrite is "n":
            print("Result not saved.")
            exit(0)

    os.makedirs(path_training, exist_ok=True)

    shutil.copyfile(os.path.normpath('/vagrant/tmp/result.json'), os.path.normpath(os.path.join(path_training, player_result.TrainingID) + "-report" + ".json"))
    with open(os.path.normpath(os.path.join(path_training, player_result.TrainingID) + "-timeNeeded" + ".txt"), 'w') as f:
        f.write(str(player_result.PlayerTimeNeeded))
    with open(os.path.normpath(os.path.join(path_training, player_result.TrainingID) + "-token" + ".txt"), 'w') as f:
        f.write(str(token))

    print("Result saved!")


if __name__ == '__main__':
    main()
