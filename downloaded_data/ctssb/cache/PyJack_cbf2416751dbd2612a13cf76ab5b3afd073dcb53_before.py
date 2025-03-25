# coding=utf-8
import carta
import mazzo
import giocatore
import mazziere
import os

ListaSemi = ["Fiori", "Quadri", "Cuori", "Picche"]
ListaRanghi = [
    "Asso", "2", "3", "4", "5", "6", "7", "8", "9", "10", "Jack", "Regina",
    "Re"
]

ListaValori = {
    "Asso": (1, 11),
    "2": 2,
    "3": 3,
    "4": 4,
    "5": 5,
    "6": 6,
    "7": 7,
    "8": 8,
    "9": 9,
    "10": 10,
    "Jack": 10,
    "Regina": 10,
    "Re": 10
}


def distribuisciIniziale(_mazzo, _giocatore,_mazziere):  # metodo distribuzione carte
    if isinstance(_mazzo, mazzo.mazzo):  # controllo sulle instanze di classe

        if isinstance(_giocatore, giocatore.giocatore):
            for i in range(2):
                _giocatore.riceviCarta(_mazzo.mazzo[i], _mazzo)

        if isinstance(_mazziere, mazziere.mazziere):
            for i in range(2):
                _mazziere.riceviCarta(_mazzo.mazzo[i], _mazzo)


def distribuisciCarta(_mazzo, _giocatore):  # metodo "carta"
    if isinstance(_mazzo, mazzo.mazzo):  # controllo sulle instanze di classe
        if isinstance(_giocatore, giocatore.giocatore):
            # distribuisci la prima carta
            _giocatore.riceviCarta(_mazzo.mazzo[0], _mazzo)


def distribuisciCartaMazzziere(_mazzo, _mazziere):
    if (isinstance(_mazzo, mazzo.mazzo)):
        if isinstance(_mazziere, mazziere.mazziere):
            _mazziere.riceviCarta(_mazzo.mazzo[0], _mazzo)


def stai(_giocatore):
    # comunica di stare e chide di far ritornare risultato
    if isinstance(_giocatore, giocatore.giocatore):
        risultato = _giocatore.stai()
        return risultato


def controlloSomma(_giocatore):  # ritorno della somma del giocatore
    if isinstance(_giocatore, giocatore.giocatore):
        somma = _giocatore.controlloSomma()
        return somma

def controlloSommaMazziere(_mazziere):
    if isinstance(_mazziere, mazziere.mazziere):
        somma = _mazziere.controlloSomma()
        return somma

def controlloBlackJack(_giocatore):  # esito blackjack iniziale
    if isinstance(_giocatore, giocatore.giocatore):
        esito = _giocatore.controlloBlackJack()
        return esito

def controlloBlackJackMazziere(_mazziere):
    if isinstance(_mazziere, mazziere.mazziere):
        esito = _mazziere.controlloBlackJack()
        return esito


def menu(_giocatore, _mazzo, _mazziere):  # menu -> da riordinare(forse)
    if isinstance(_mazziere, mazziere.mazziere):
        if isinstance(_giocatore, giocatore.giocatore):
            if isinstance(_mazzo, mazzo.mazzo):

                # distribuzione carte iniziale
                distribuisciIniziale(_mazzo, _giocatore, _mazziere)
                
                continua = True  # booleano per continuità della partina, verra messo a false quando giocatore "sta" o "sfora"

                print "\n tu:\n%s \n" % _giocatore
                print "\n mazziere:\n%s \n" % _mazziere.stampaIniziale()
                # risposta da esito del blackjack iniziale
                esitoGiocatore = controlloBlackJack(_giocatore)
                esitoMazziere = controlloBlackJackMazziere(_mazziere)

                if esitoGiocatore == True and esitoMazziere == False:
                    print "complimenti hai fatto BlackJack"
                    continua = False
                if esitoGiocatore == False and esitoMazziere == True:
                    print "il mazziere ha fatto BlackJack", _mazziere
                    continua = False
                if esitoGiocatore == True and esitoMazziere == True:
                    print "pareggio BlackJack da entrambe le parti"
                    continua = False


                while continua:

                    print "\n%s decidi la tua mossa" % _giocatore.nome
                    print "1) carta"
                    print "2) stai"
                    scelta = input(("\ninserire scelta: "))

                    if scelta == 1:  # distribuzione carta
                        distribuisciCarta(_mazzo, _giocatore)

                        # controllo assi dopo ricevuta la carta
                        _giocatore.controlloAssi()

                        print "\n%s" % _giocatore
                        # controlla che si possa richiedere ancora carta
                        somma = controlloSomma(_giocatore)

                        if somma == 21:  # controllo se 21 o sforato a carta
                            print "\nhai fatto 21\n"
                            continua = False
                        elif somma > 21:
                            print "\nhai sforato con: %d\n" % somma
                            continua = False

                    elif scelta == 2:  # stop e controllo ritorno somma -> implementare controllo blackjack
                        risultato = stai(_giocatore)
                        if risultato < 22:
                            while _mazziere.somma < 17:
                                distribuisciCartaMazzziere(_mazzo, _mazziere)
                                _mazziere.controlloAssi()

                        continua = False
                        print "\n",_giocatore,"\n"
                        print "\nhai fatto: %d\n" % risultato

                print "\nmazziere: %s\n" % _mazziere
                
                if _giocatore.somma < 22:
                    if _giocatore.somma > _mazziere.somma and _mazziere.somma < 22:
                        print "%s ha vinto con: %d\n il mazziere ha fatto: %d" % (_giocatore.nome,_giocatore.somma,_mazziere.somma)
                    if _giocatore.somma < _mazziere.somma and _mazziere.somma < 22:
                        print "%s ha perso con %d\n il mazziere ha fatto: %d" % (_giocatore.nome,_giocatore.somma,_mazziere.somma)
                    if _mazziere.somma > 21:
                        print "%s ha vinto con: %d\nil mazziere ha sforato con: %d" % (_mazziere.somma,_giocatore.nome,_giocatore.somma)
                    if _mazziere.somma == _giocatore.somma:
                        print "pareggio con:%d" % _giocatore.somma
                else:
                    print "%s ha sforato con: %d\n il mazziere vince con %d" % (_giocatore.nome,_giocatore.somma,_mazziere.somma)

def main():
    os.system("clear")
    tempMazzo = []  # lista di carte temporanea

    for a in ListaSemi:
        for b in ListaRanghi:

            # carta da inserire in lista temporanea
            tempCarta = carta.carta(a, b)

            tempMazzo.append(tempCarta)

    # creo oggetto mazzo con la lista preparata prima
    _mazzo = mazzo.mazzo(tempMazzo)

    for i in range(0, 100):  # shuffle del mazzo per 100 volte
        _mazzo.mischia()

    nomeGiocatore = raw_input(
        "\n\n\ninserisci il tuo nome: ")  # inserimento giocatore

    _giocatore = giocatore.giocatore(nomeGiocatore)
    print "\n\n\n benvenuto %s" % _giocatore.nome

    _mazziere = mazziere.mazziere()

    menu(_giocatore, _mazzo, _mazziere)
    ok = raw_input("\n\n\n clicca invio per continuare...")


while True:
    main()
