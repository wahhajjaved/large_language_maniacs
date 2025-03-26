# -*- coding: utf-8 -*-
'''
Created on 23 deb. 2018

@author: C. Guychard
@copyright: ©2018 Article 714
@license: AGPL v3
'''

from copy import copy
from enum import IntEnum, unique
import re

from odoo.addons.goufi_base.utils.converters import toString

from .csv_support_mixins import CSVImporterMixin
from .processor import LineIteratorProcessor
from .xl_base_processor import XLImporterBaseProcessor


#---------------------------------------------------------
# Global values
DEFAULT_LOG_STRING = u" [ line %d ] -> %s"


#---------------------------------------------------------
# utility function(s)

@unique
class MappingType(IntEnum):
    Standard = 0
    One2Many = 1
    Many2One = 2
    ContextEval = 3
    Constant = 4
    FunctionCall = 5

#-------------------------------------------------------------------------------------
# MAIN CLASS


class ExpressionProcessorMixin(object):
    """
    TODO: translate documentation
    TODO: optimize perfs by better using cache of header analysis

    TODO: document the creation parameter for relational fields


    Cette classe permet de traiter des fichiers CSV, XLS ou XLSX pour importer les données qu'ils contiennent dans une instance d'Odoo

    Les fichiers sont importés depuis un répertoire (y compris les sous-répertoires) après avoir été trié par ordre alphabétique

    POUR LES FICHIERS XLS/XLSX

        * chaque feuille est importée séparément
        * le nom du modèle cible est le nom de la feuille

    POUR LES FICHIERS CSV

        * le nom du fichier est du format XX_NOM.csv
             -- XX contenant 2 chiffres pour ordonner l'import,
             -- NOM contient le nom du modèle cible en remplaçant les '.' par des '_'

             /ex, pour importer des res.partner le fichier sera nommé : 00_res_partner.csv

    TRAITEMENT DES LIGNES d'ENTETES (1ere ligne de la feuille (xls*) ou du fichier (csv)

        * la première ligne du fichier définit la façon dont la valeur des colonnes seront importées/traitées:

            -- si la cellule contient le nom d'un champs du modèle, sans modificateur, alors les données de la colonne sont affectés au champs du même nom
                    dans la base
                    /ex. si le modèle cible est res.partner, le contenu de la colonne 'name', sera affecté au champ name de l'enregistrement correspondant

            -- toutes les colonnes contenant des valeurs non retrouvées dans le modèle sont ignorées

            -- Le contenu de la colonne peut démarrer par un modificateur

                    => ">nom_modele_lie/nom_champs_recherche&(filtre)"
                            le champs a adresser (target_field) est un champs relationnel vers le modèle (nom_model_lie),
                            de type Many2One
                            pour retrouver l'enregistrement lié, on construit une chaine de recherche avec
                            [noms_champs_recherche=valeur_colonne], le filtre étant utilisé pour restreindre encore la recherche

                            si un enregistrement est trouvé dans le modèle lié, alors l'enregistrement courant est mis à jour/créé avec
                            la valeur "nom_champs" pointant vers ce dernier, sinon, une erreur est remontée et la valeur du champs est ignorée

                    => "*nom_modele_lie/nom_champs_recherche&(filtre)"
                            le champs a adresser (target_field) est un champs relationnel vers le modèle (nom_model_lie),
                            de type One2Many
                            pour retrouver les enregistrements liés, on itère sur toutes les valeurs (séparées par des ';' points virgules)
                            pour construire une chaine de recherche avec [noms_champs_recherche=valeur_colonne],
                            le filtre étant utilisé pour restreindre encore la recherche

                            pour chaque enregistrement trouvé dans le modèle lié, l'enregistrement courant est mis à jour en ajoutant
                            à la collection  "target_field" un pointeur vers l'enregistrement cible

                    => "+nom_modele_lie"

                            le champs a adresser (target_field) est un champs relationnel vers le modèle (nom_model_lie),
                            de type One2Many

                            on crée un ou plusieurs enregistrements cibles avec les valeurs données sous forme de dictionnaire
                            (/ex.: {'name':'Mardi','dayofweek':'1',...})
                            séparés par des ';' points virgules

    """

    def __init__(self, parent_config):

        # error reporting mechanism
        self.errorCount = 0

        # hooks
        self.register_hook('_prepare_mapping_hook', ExpressionProcessorMixin.prepare_mapping_hook)

        # variables use during processing
        self.mandatoryFields = {}
        self.idFields = {}
        self.delOrArchMarkers = {}
        self.col2fields = {}
        self.allMappings = {}

        self.header_line_idx = self.parent_config.default_header_line_index
        self.target_model = None

        self.m2o_create_if_no_target_instance = ()
        for param in parent_config.processor_parameters:
            if param.name == u'm2o_create_if_no_target_instance':
                self.m2o_create_if_no_target_instance = param.value.split(',')
        self.target_model = None

    #-------------------------------------------------------------------------------------
    # maps a line of data from column/mapping name to field name
    # and change non json-compatible values

    def map_values(self, row):
        result = copy(row)
        keys = [x for x in row.keys()]
        for f in keys:
            if f in self.col2fields:
                # replace non json-compatible values
                val = result[f]
                if val == "False" or val == "True":
                    val = eval(val)
                elif val == None:
                    del(result[f])
                    continue
                # replace actual col name by actual field name
                col = self.col2fields[f]
                if col != f:
                    result[col] = val
                    del(result[f])
                else:
                    result[f] = val
            else:
                del(result[f])

        return result

    #-------------------------------------------------------------------------------------
    # Process mappings configuration hook for each tab
    def prepare_mapping_hook(self, tab_name="Unknown", colmappings=None):

        if colmappings == None:
            self.logger.error("Not able to process mappings")
            return -1

        self.mandatoryFields = {}
        self.idFields = {}
        self.delOrArchMarkers = {}
        self.col2fields = {}
        self.column_groups = {}
        self.allMappings = {}
        numbOfFields = 0

        # We should have a model now
        if self.target_model == None:
            self.logger.error("MODEL NOT FOUND ")
            return -1
        else:
            self.logger.info("#-----------------------------------------------------------------------------")
            self.logger.info("NEW SHEET [%s]:  Import data for model %s",
                             tab_name, toString(self.target_model))

        # List of fields in target model
        target_fields = None
        if self.target_model == None:
            raise Exception('FAILED', u"FAILED => NO TARGET MODEL FOUND")
        else:
            target_fields = self.target_model.fields_get_keys()

        #***********************************
        # process column mappings
        if colmappings == None:
            self.logger.warning("NO Column mappings provided => fail")
            return -1

        for val in MappingType:
            self.allMappings[val] = {}

        for val in colmappings:

            mappingType = None

            if val.target_field.name in target_fields:
                self.col2fields[val.name] = val.target_field.name

                if val.is_constant_expression:
                    mappingType = MappingType.Constant
                    if val.mapping_expression and len(val.mapping_expression) > 2:
                        self.allMappings[mappingType][val.name] = [val.target_field.name, val.mapping_expression]
                    else:
                        self.logger.error("Wrong mapping expression: too short (%s)", val.name)
                elif val.is_contextual_expression_mapping:
                    mappingType = MappingType.ContextEval
                    if val.mapping_expression and len(val.mapping_expression) > 2:
                        self.allMappings[mappingType][val.name] = [val.target_field.name, val.mapping_expression]
                    else:
                        self.logger.error("Wrong mapping expression: too short (%s)", val.name)
                elif val.is_function_call:
                    mappingType = MappingType.FunctionCall
                    if val.mapping_expression and len(val.mapping_expression) > 2 and hasattr(self, val.mapping_expression):
                        self.allMappings[mappingType][val.name] = [
                            val.target_field.name, getattr(self, val.mapping_expression)]
                    else:
                        self.logger.error(u"Wrong mapping expression for %s: too short or method does not exist (%s)",
                                          val.name, str(val.mapping_expression))
                elif val.mapping_expression and len(val.mapping_expression) > 2:
                    if re.match(r'\*.*', val.mapping_expression):
                        mappingType = MappingType.One2Many
                        v = val.mapping_expression.replace('*', '')
                        vals = [0, val.target_field.name] + v.split('/')
                        if re.match(r'.*\&.*', vals[2]):
                            (_fieldname, cond) = vals[2].split('&')
                            vals[2] = _fieldname
                            try:
                                vals.append(eval(cond))
                            except:
                                self.logger.exception("Could not parse given conditions %s", str(cond))
                        self.allMappings[mappingType][val.name] = vals
                    elif re.match(r'\+.*', val.mapping_expression):
                        mappingType = MappingType.One2Many
                        v = val.mapping_expression.replace('+', '')
                        vals = [1, val.target_field.name] + v.split('/')
                        self.allMappings[mappingType][val.name] = vals
                    elif re.match(r'\>.*', val.mapping_expression):
                        mappingType = MappingType.Many2One
                        v = val.mapping_expression.replace('>', '')
                        vals = [val.target_field.name] + v.split('/')
                        if re.match(r'.*\&.*', vals[2]):
                            (_fieldname, cond) = vals[2].split('&')
                            vals[2] = _fieldname
                            try:
                                vals.append(eval(cond))
                            except:
                                self.logger.exception("Could not parse given conditions %s", str(cond))
                        self.allMappings[mappingType][val.name] = vals
                else:
                    mappingType = MappingType.Standard
                    self.allMappings[mappingType][val.name] = val.target_field.name

            if mappingType != None:
                numbOfFields += 1
                if val.is_mandatory:
                    self.mandatoryFields[val.name] = mappingType

                if val.is_identifier:
                    self.idFields[val.name] = mappingType

            if val.is_deletion_marker or val.is_archival_marker:
                self.delOrArchMarkers[val.name] = (
                    val.is_deletion_marker, val.delete_if_expression, val.is_archival_marker)

        return numbOfFields

    #-------------------------------------------------------------------------------------
    # Process line values
    def process_values(self, line_index, data_values):

        currentObj = None
        TO_BE_ARCHIVED = False
        TO_BE_DELETED = False

        # List of fields in target model
        target_fields = None
        if self.target_model == None:
            raise Exception('FAILED', u"FAILED => NO TARGET MODEL FOUND")
        else:
            target_fields = self.target_model.fields_get_keys()

        # Detects if record needs to be deleted or archived
        CAN_BE_ARCHIVED = ('active' in target_fields)

        search_criteria = []

        if self.target_model == None:
            return False

        # Process contextual values
        for val in self.allMappings[MappingType.ContextEval]:
            try:
                value = eval(self.allMappings[MappingType.ContextEval][val][1])
                data_values[val] = value
            except Exception as e:
                self.logger.exception("Failed to evaluate expression from context: %s ", str(val))

        # Process Function Call values
        for val in self.allMappings[MappingType.FunctionCall]:
            try:
                if val in data_values:
                    function = self.allMappings[MappingType.FunctionCall][val][1]
                    value = function(data_values[val])
                    if value != None:
                        data_values[val] = value
                    else:
                        del data_values[val]
            except:
                self.logger.exception("Failed to compute value from function call: %s", str(val))

        # Many To One Fields, might be mandatory, so needs to be treated first and added to StdRow
        for f in self.allMappings[MappingType.Many2One]:

            if f in data_values:
                config = self.allMappings[MappingType.Many2One][f]
                # reference Many2One,
                if data_values[f] and len(data_values[f]) > 0:
                    cond = []
                    if len(config) > 3:
                        cond = []
                        for v in config[3]:
                            cond.append(v)
                        cond.append((config[2], '=', data_values[f]))
                    else:
                        cond = [(config[2], '=', data_values[f])]

                    # search in active and archived records if model contains an 'active' property

                    search_model = self.odooenv[config[1]]
                    if 'active' in search_model.fields_get_keys():
                        cond.append('|')
                        cond.append(('active', '=', True))
                        cond.append(('active', '=', False))

                    # do search for a record
                    vals = self.odooenv[config[1]].search(cond, limit=1)

                    if len(vals) == 1:
                        data_values[f] = vals[0].id

                    elif f in self.m2o_create_if_no_target_instance:
                        # Create if not found on m2one
                        try:
                            data_values[f] = self.odooenv[config[1]].create({config[2]: data_values[f]}).id
                        except:
                            self.logger.error(DEFAULT_LOG_STRING, line_index + 1, u" failed to create a new record for %s   for model  %s" % (
                                toString(data_values[f]), toString(config[1])))
                            del data_values[f]

                    else:
                        self.logger.warning(DEFAULT_LOG_STRING, line_index + 1, u" found %d values for %s  ,unable to reference %s -> %s" %
                                            (len(vals), toString(data_values[f]), toString(config[1]), toString(vals)))
                        del data_values[f]

        # TODO: Document this!
        # If there exists an id config we can process deletion, archival and updates
        # if there is no, we can only process creation
        found = []
        if len(self.idFields) > 0 and self.target_model != None:

            for f in self.delOrArchMarkers:
                if f in data_values:
                    config = self.delOrArchMarkers[f]
                    if config[0]:
                        # deletion config
                        TO_BE_DELETED = (re.match(config[1], data_values[f]) != None)
                        TO_BE_ARCHIVED = TO_BE_DELETED and config[2]
                        if TO_BE_ARCHIVED and not CAN_BE_ARCHIVED:
                            self.logger.error(DEFAULT_LOG_STRING, line_index + 1,
                                              "This kind of records can not be archived")
                            TO_BE_ARCHIVED = False
                    else:
                        # archival config
                        TO_BE_ARCHIVED = (re.match(config[1], data_values[f]) != None)
                        if TO_BE_ARCHIVED and not CAN_BE_ARCHIVED:
                            self.logger.error(DEFAULT_LOG_STRING, line_index + 1,
                                              "This kind of records can not be archived")
                            TO_BE_ARCHIVED = False

            # compute search criteria
            # based on Id fiedls (standard mapping, constant mapping of Many2One are supported
            for k in self.idFields:
                mapType = self.idFields[k]
                value = None
                keyfield = None
                if mapType == MappingType.Standard or mapType == MappingType.FunctionCall:
                    keyfield = self.allMappings[mapType][k]
                    if k in data_values:
                        value = data_values[k]
                elif mapType in (MappingType.Constant, MappingType.ContextEval):
                    (keyfield, value) = self.allMappings[mapType][k]
                elif mapType == MappingType.Many2One:
                    keyfield = self.col2fields[k]
                    if k in data_values:
                        value = data_values[k]
                else:
                    self.logger.error(DEFAULT_LOG_STRING, line_index + 1, u"Wrong identifier column %s" % k)
                    return 0

                if value != None and value != str(''):
                    search_criteria.append((keyfield, '=', value))
                else:
                    self.logger.warning(DEFAULT_LOG_STRING, line_index + 1,
                                        "GOUFI: Do not process line n.%d, as Id column (%s) is empty" % (line_index + 1, k))
                    self.errorCount += 1
                    return

            # ajout d'une clause pour rechercher tous les enregistrements
            if CAN_BE_ARCHIVED:
                search_criteria.append('|')
                search_criteria.append(('active', '=', True))
                search_criteria.append(('active', '=', False))

            # recherche d'un enregistrement existant
            if len(search_criteria) > 0:
                found = self.target_model.search(search_criteria)

            if len(found) == 1:
                currentObj = found[0]
            elif len(found) > 1:
                self.logger.warning(DEFAULT_LOG_STRING, line_index + 1, u"FOUND TOO MANY RESULT FOR " + toString(self.target_model) +
                                    " with " + toString(search_criteria) + "=>   [" + toString(len(found)) + "]")
                return
            else:
                currentObj = None

        # hook for objects needing to be marked as processed
        # by import
        # TODO: document and check this
        if currentObj != None and ('import_processed' in self.target_model.fields_get_keys()):
            currentObj.write({'import_processed': True})
            currentObj.import_processed = True
            self.odooenv.cr.commit()

        # processing archives or deletion and returns
        if TO_BE_DELETED:
            if not currentObj == None:
                try:
                    currentObj.unlink()
                except:
                    if TO_BE_ARCHIVED:
                        self.odooenv.cr.rollback()
                        self.logger.warning(DEFAULT_LOG_STRING, line_index + 1,
                                            "Archiving record as it can not be deleted (line n. %d)" % (line_index + 1,))
                        try:
                            currentObj.write({'active': False})
                            currentObj.active = False
                        except Exception as e:
                            self.odooenv.cr.rollback()
                            self.logger.warning(
                                DEFAULT_LOG_STRING, line_index + 1, u"Not able to archive record (line n. %d) : %s" % (line_index + 1, toString(e),))
                currentObj = None
                self.odooenv.cr.commit()
            return True
        elif TO_BE_ARCHIVED:
            if not currentObj == None:
                try:
                    currentObj.write({'active': False})
                    currentObj.active = False
                    self.odooenv.cr.commit()
                except Exception as e:
                    self.odooenv.cr.rollback()
                    self.logger.warning(DEFAULT_LOG_STRING, line_index + 1, u"Not able to archive record (line n. %d) : %s" %
                                        (line_index + 1, toString(e),))
        elif CAN_BE_ARCHIVED:
            if not currentObj == None:
                try:
                    currentObj.write({'active': True})
                    currentObj.active = True
                    self.odooenv.cr.commit()
                except Exception as e:
                    self.odooenv.cr.rollback()
                    self.logger.warning(DEFAULT_LOG_STRING, line_index + 1, u"Not able to activate record (line n. %d) : %s" %
                                        (line_index + 1, toString(e),))

        # Pre Write Hooks
        try:
            if currentObj != None:
                self.run_hooks('_pre_write_record_hook', data_values)
        except:
            self.odooenv.cr.rollback()
            self.logger.exception(DEFAULT_LOG_STRING, line_index + 1,
                                  u" Error raised during _pre_write_record_hook processing")

        # Create Object if it does not yet exist, else, write updates
        actual_values = None
        try:

            # check mandatory fields
            for f in self.mandatoryFields:
                if f not in data_values:
                    self.errorCount += 1
                    self.logger.error(DEFAULT_LOG_STRING, line_index + 1,
                                      u"missing value for mandatory column: %s" % f)
                    return False
            actual_values = self.map_values(data_values)
            if currentObj == None:
                currentObj = self.target_model.create(actual_values)
            else:
                currentObj.write(actual_values)

            self.odooenv.cr.commit()
        except ValueError as e:
            self.odooenv.cr.rollback()
            self.logger.exception(DEFAULT_LOG_STRING, line_index + 1, u" wrong values where creating/updating object: %s -> %s [%s] " % (
                str(self.target_model), toString(actual_values), toString(currentObj)))
            self.logger.error(u"                    MSG: %s", toString(e))
            currentObj = None
        except:
            self.odooenv.cr.rollback()
            self.errorCount += 1
            self.logger.exception(DEFAULT_LOG_STRING, line_index + 1, u" Generic Error raised Exception")
            currentObj = None

        # One2Many Fields,

        try:
            for f in self.allMappings[MappingType.One2Many]:
                if f in data_values:
                    members = data_values[f].split(';')
                    config = self.allMappings[MappingType.One2Many][f]
                    if len(members) > 0 and currentObj != None:
                        if config[0] == 1:
                            currentObj.write({config[1]: [(5, False, False)]})
                        for m in members:
                            if len(m) > 0:
                                # References records in  One2Many
                                if config[0] == 0:
                                    vals = self.odooenv[config[1]].search([(config[2], '=', m)], limit=1)
                                    if len(vals) == 1:
                                        currentObj.write({config[2]: [(4, vals[0].id, False)]})
                                    else:
                                        self.logger.warning(
                                            DEFAULT_LOG_STRING, line_index + 1, u"found %d  values for %s =>   unable to reference" % (len(vals), toString(m)))

                                # Creates records in  One2Many
                                elif config[0] == 1:
                                    values = eval(m)
                                    currentObj.write({config[2]: [(0, False, values)]})
            self.odooenv.cr.commit()
        except ValueError as e:
            self.odooenv.cr.rollback()
            self.logger.exception(DEFAULT_LOG_STRING, line_index + 1, u" Wrong values where updating object: " +
                                  self.target_model.name + " -> " + toString(data_values))
            self.logger.error("                    MSG: %s", toString(e))
            currentObj = None
        except:
            self.odooenv.cr.rollback()
            self.logger.exception(DEFAULT_LOG_STRING, line_index + 1, u" Generic Error raised Exception")
            currentObj = None

        # Post Write Hooks
        try:
            if currentObj != None:
                self.run_hooks('_post_write_record_hook',  currentObj, data_values, actual_values)
        except:
            self.odooenv.cr.rollback()
            self.logger.exception(DEFAULT_LOG_STRING, line_index + 1,
                                  u" Error raised during _post_write_record_hook processing")

        # Finally commit
        self.odooenv.cr.commit()


#-------------------------------------------------------------------------------------
# Process CSV Only
class CSVProcessor(ExpressionProcessorMixin, CSVImporterMixin, LineIteratorProcessor):
    """
    Processes csv files
    """

    def __init__(self, parent_config):
        LineIteratorProcessor.__init__(self, parent_config)
        ExpressionProcessorMixin.__init__(self, parent_config)
        CSVImporterMixin.__init__(self, parent_config)

    def get_rows(self, import_file=None):

        reader = self._open_csv(import_file, asDict=True)
        idx = 0
        for row in reader:
            yield (idx, row)
            idx += 1


#-------------------------------------------------------------------------------------
# Process XL* Only


class XLProcessor(ExpressionProcessorMixin, XLImporterBaseProcessor):
    """
    Processes xls and xlsx files
    """
    #----------------------------------------------------------

    def __init__(self, parent_config):
        XLImporterBaseProcessor.__init__(self, parent_config)
        ExpressionProcessorMixin.__init__(self, parent_config)
