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
    path_result_file   = ""

    def getResultPath(self, path_config_client):
        config = ConfigParser()
        config.read(os.path.normpath(path_config_client))
        return config.get('inspec', 'result_path')

    def __init__(self, path_config_client):
        self.path_config_client = path_config_client
        self.path_result_file = self.getResultPath(path_config_client)


def update():
    print("To update please....")


def check():
    print('Start check. This may take a while..')
    subprocess.call('inspec exec /vagrant/training/ --reporter json:/tmp/result.json', shell=True)
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

    def getUptime(self):
        tuptime = subprocess.check_output('tuptime -s | grep life | cut -d: -f2', shell=True)
        uptime = float(tuptime.decode('utf-8').strip())
        uptime = uptime / 60
        uptime = round(uptime)
        return int(uptime)

    def setTimeLimit(self, time):
        self.TrainingTimeLimit = time
        self.PlayerTimeNeeded = self.getUptime()
        self.PlayerProductivity = round((time / self.PlayerTimeNeeded) * 100)

    def getResult(self):
        if (self.TrainingTotalImpact == self.PlayerImpact) and self.PlayerProductivity >= 90:
            return True
        else:
            return False


def main():
    # config
    path_config_client = '/admindojo/config/client.ini'
    player_config = Config(os.path.normpath(path_config_client))

    player_result = ResultTraining()
    # Read JSON data into the datastore variable
    with open(os.path.normpath('/tmp/result.json'), 'r') as f:
        result_json = json.load(f)
        # todo try catch

    player_result.TrainingID = result_json['profiles'][0]['name']

    # Calc total values
    calc_time_limit = 0
    for key in result_json['profiles']:
        for control in key['controls']:
            calc_time_limit += int(control['tags']['duration'])
            player_result.TrainingTotalImpact += control['impact']

    player_result.setTimeLimit(calc_time_limit)

    # Print Result

    print()
    print("Result for Training: " + result_json['profiles'][0]['title'])
    print("Training id        : " + result_json['profiles'][0]['name'])
    # todo print help url

    print('---------------------------------------------------------')

    for key in result_json['profiles']:
        for control in key['controls']:
            print(control['title'])
            control_has_failures = False
            for code in control['results']:
                if code['status'] == 'passed':
                    pass_color = 'green'
                    pass_symbol = "\N{check mark} [pass]"
                else:
                    pass_color = 'red'
                    pass_symbol = "\N{BALLOT X} [fail]"
                    control_has_failures = True
                print('\t' + colored(pass_symbol, pass_color) + " " + code['code_desc'])

            print()
            print('\tEstimated duration: ' + str(control['tags']['duration']) + ' Minutes')
            print('\tPossible score   : ' + str(control['impact']))

            if control_has_failures == True:
                # print tag help
                print('\t' + colored("This part has failures!", 'red'))
                print('\t\t' + 'See help: url')
            else:
                player_result.PlayerImpact += control['impact']

    print('---------------------------------------------------------')
    print()
    print('Total score to earn : ' + str(player_result.TrainingTotalImpact))
    print('You got             : ' + str(player_result.PlayerImpact))
    print()
    print('Your time limit was : ' + str(player_result.TrainingTimeLimit) + ' Minutes')
    print('You needed          : ' + str(player_result.PlayerTimeNeeded) + ' Minutes')

    print('Productivity        : ' + str(player_result.PlayerProductivity) + '%')

    print()

    if player_result.getResult():
        print(colored("You finished your training successfully!", 'green'))
    else:
        print(colored("You failed your training! \n" +
                      "You need to pass all tests and need a productivity of minimum 90%!", 'red'))
    print()

    shutil.copyfile(os.path.normpath('/tmp/result.json'), os.path.normpath(os.path.join(player_config.path_result_file, player_result.TrainingID) + ".json"))


if __name__ == '__main__':
    main()
