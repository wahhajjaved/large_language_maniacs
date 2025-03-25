#!/usr/bin/env python3.4
# -*- coding: UTF-8 -*-

"""
Datumsformat:
{
  "tag":tag,
  "monat":monat,
  "jahr":jahr,
  "stunde":stunde,
  "minute":minute,
}
"""

"""
Wird geworfen, wenn ein Datum nicht in der Simocracy-Epoche liegt.
"""
class SyEpocheException(Exception):
    pass

"""
Gibt zurück, wie viele Tage monat im Jahr jahr hat.
"""
def monatLen(monat, jahr):
    if monat == 2:
        if isSchaltjahr(jahr):
            return 29
        else:
            return 28
        
    monate = [
        31, #jan
        -1, #feb
        31, #mae
        30, #apr
        31, #mai
        30, #jun
        31, #jul
        31, #aug
        30, #sep
        31, #okt
        30, #nov
        31  #dez
    ]
    
    return monate[monat - 1]

"""
Gibt zurück, ob jahr ein Schaltjahr n. greg. Kalender ist.
"""
def isSchaltjahr(jahr):
    if jahr % 400 == 0:
        return True
    if jahr % 4 == 0 and jahr % 100 != 0:
        return True
    
    return False

"""
Wirft Exception, wenn datum kein valides Datum n. greg. Kalender ist.
"""
def isValidDatum(datum):
    msg = "Angegebenes Datum ist ungültig."

    if not (
      "tag" in datum
      and "monat" in datum
      and "jahr" in datum
      and "stunde" in datum
      and "minute" in datum
    ):
        raise Exception(msg)

    tag = datum["tag"] > monatLen(datum["monat"], datum["jahr"])
    tag = tag or datum["tag"] < 1
    monat = datum["monat"] < 1
    monat = monat or datum["monat"] > 12
    stunde = datum["stunde"] < 0 or datum["stunde"] > 23
    minute = datum["minute"] < 0 or datum["minute"] > 59

    if tag or monat or stunde:
        raise Exception(msg)
    

"""
Konvertiert ein RL-Datum zum zugehörigen SY-Datum.
"""
def rltosy(datum):
    # Input checken
    isValidDatum(datum)
    epochIn08 = datum["jahr"] == 2008 and datum["monat"] < 10
    if datum["jahr"] < 2008 or epochIn08:
        raise SyEpocheException(datum)
    
    # Monate des Quartals (= Sy-Jahr) sammeln
    quartalsanfang = datum["monat"] - ( datum["monat"] + 2 ) % 3
    quartal = []
    for i in range(quartalsanfang, datum["monat"]):
        quartal.append(i)
        
    # SY-Jahr berechnen
    syJahr = ( datum["jahr"] - 2008 ) * 4 + 2017
    syJahr += quartalsanfang / 3
        
    # Vergangene Tage im Quartal zusammenaddieren
    tage = datum["tag"] - 1
    for i in quartal:
        tage += monatLen(i, datum["jahr"])
        
    # Bisherige Minuten des Quartals
    minuten = tage*24*60 + datum["stunde"]*60 + datum["minute"]
    
    # In SY-Minuten umrechnen
    schalttag = 0
    if isSchaltjahr(syJahr):
        schalttag = 1
        
    syjahrMins = ( 365 + schalttag ) * 24 * 60
    
    quartalMins = 0
    for i in range(quartalsanfang, quartalsanfang + 3):
        quartalMins += monatLen(i, datum["jahr"]) * 24 * 60
        
    sydatumMins = int(float(minuten) * (float(syjahrMins) / float(quartalMins)))
    
    # Stunde und Minute berechnen
    sydatumTag = sydatumMins / ( 60 * 24 ) + 1
    syMinute = sydatumMins % 60
    syStunde = sydatumMins / 60 - sydatumTag * 24 + 24
    
    # von Tagen Monate abziehen
    volleMonate = 0 # Tage im SY-Datum, die in vergangenen Monaten liegen
    syMonat = 1
    while True:
        if volleMonate + monatLen(syMonat, syJahr) >= sydatumTag:
            break
        volleMonate += monatLen(syMonat, syJahr)
        syMonat += 1
    
    syTag = sydatumTag - volleMonate
    
    return {
        "tag"    : syTag,
        "monat"  : syMonat,
        "jahr"   : syJahr,
        "stunde" : syStunde,
        "minute" : syMinute,
    }

"""
Konvertiert ein SY-Datum zum RL-Datum.
Erwartet 5-elementige Liste als Argument.
"""
def sytorl(datum):
    # Input checken
    isValidDatum(datum)
    if datum["jahr"] < 2020:
        raise SyEpocheException()
    
    # Jahr und Quartal berechnen
    quartalNr = ( jahr - 1 ) % 4 # Zaehlung beginnt bei 0
    rlJahr = ( jahr - 2017 ) / 4 + 2008
    
    # Minuten zusammenaddieren
    minuten = (tag - 1) * 24 * 60 + datum["stunde"] * 60 + datum["minute"]
    for i in range(1, datum["monat"]):
        minuten += monatLen(i, datum["jahr"]) * 24 * 60
    
    # Minuten des gesamten Jahres berechnen
    schalttag = 0
    if isSchaltjahr(datum["jahr"]):
        schalttag = 1
    syjahrMins = ( 365 + schalttag ) * 24 * 60
    
    # Quartallaenge in Minuten berechnen
    quartal = []
    quartalMins = 0
    for i in range(quartalNr * 3 + 1, quartalNr * 3 + 4):
        quartal.append(i)
        quartalMins += monatLen(i, rlJahr) * 24 * 60
    
    # in RL-Quartal-Minuten umrechnen
    rldatumMins = int(float(minuten) / (float(syjahrMins) / float(quartalMins)))
    
    # Stunde und Minute berechnen
    rlMinute = rldatumMins % 60
    rldatumTag = rldatumMins / ( 60 * 24 ) + 1
    rlStunde = rldatumMins / 60 - (rldatumTag - 1) * 24
    
    # von Tagen Monate abziehen
    volleMonate = 0 # Tage im RL-Datum, die in vergangenen Monaten liegen
    rlMonat = quartal[0]
    while True:
        if volleMonate + monatLen(rlMonat, rlJahr) > rldatumTag - 1:
            break
        volleMonate += monatLen(rlMonat, rlJahr)
        rlMonat += 1
    
    rlTag = rldatumTag - volleMonate
    
    # 24-Stunde umklappen"
    if rlStunde == 24:
        rlStunde = 0
        rlTag += 1
        if rlTag > monatLen(rlMonat, rlJahr):
            rlMonat += 1
            rlTag = 1
    
    return {
        "tag"    : rlTag,
        "monat"  : rlMonat,
        "jahr"   : rlJahr,
        "stunde" : rlStunde,
        "minute" : rlMinute,
    }

