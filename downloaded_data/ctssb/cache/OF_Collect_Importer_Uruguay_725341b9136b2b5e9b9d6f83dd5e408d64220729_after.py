#!/usr/bin/env python
# -*- coding: utf-8 -*-s

import csv
import logging
import os
import sys

from src.model import class_lib
from src.model import code_lists
from src.utils import tools_lib


def import_fni_plots_2015(survey,species_list,infile):
    """Function to import_modules plot data in the 2015 file format

       :param survey: An instance of class survey
       :param infile: The file path to the 2015 plot data
       """

    # Check if survey is of class survey
    try:
        isinstance(survey, class_lib.Survey)
        print "Using survey {}".format(survey.survey_id)
    except:
        print "Survey is not of class Survey"
        sys.exit(0)

    # Check if files exits and readable
    try:
        f = open(infile, 'r')
    except IOError:
        print "Input file {} is missing or is not readable".format(infile)
        sys.exit(0)

    with open(infile, 'rb') as csvfile:
        datareader = csv.DictReader(csvfile, delimiter=',')
        counter = []
        for row in datareader:
            ID = row['nombre_pm']
            if ID in survey.plots.keys():
                if ID not in counter:
                    counter.append(ID)
                survey.plots[ID].pm_altitude = ''
                survey.plots[ID].pm_altitude_unit_name = 'metros'
                survey.plots[ID].general_datos_parcela_estado_1 = 1

                if row['name'] == 'Punto':
                    survey.plots[ID].pm_coord_crs = ''
                    survey.plots[ID].pm_coord_y = tools_lib.import_variable(row, 'lat_pm', 'float', ID)
                    survey.plots[ID].pm_coord_x = tools_lib.import_variable(row, 'lon_pm', 'float', ID)

                if row['name'] == 'DatosGenerales':
                    survey.plots[ID].general_datos_parcela_bosque_tipo =\
                        tools_lib.import_variable(row, 'tipoDeBosque', 'code', ID, code_lists.bosque_tipo)
                    if survey.plots[ID].general_datos_parcela_bosque_tipo == 2:
                        #Set the nivel 3 catagory for all plantations to DAB > 3cm by default
                        survey.plots[ID].general_datos_parcela_estado_3 = 2
                    survey.plots[ID].general_datos_parcela_bosque_sub_tipo =\
                        tools_lib.import_variable(row, 'subbosque', 'code', ID, code_lists.subbosque_tipo)

                    survey.plots[ID].general_datos_parcela_accesibilidad = \
                        tools_lib.import_variable(row, 'facilidadProgresion', 'code', ID, code_lists.accesibilidad)

                    survey.plots[ID].pm_departamento = \
                        tools_lib.import_variable(row, 'departamento', 'code', ID, code_lists.departamento)

                    survey.plots[ID].general_datos_parcela_propietario = \
                        tools_lib.import_variable(row, 'propietario', 'string', ID)

                    survey.plots[ID].general_datos_parcela_predio = \
                        tools_lib.import_variable(row, 'predio', 'string', ID)


                    date = str.split(row['fecha'], '/')
                    try:
                        date.__len__() == 3
                        survey.plots[ID].general_datos_parcela_fecha_observation_year = date[2]
                        survey.plots[ID].general_datos_parcela_fecha_observation_month = date[0]
                        survey.plots[ID].general_datos_parcela_fecha_observation_day = date[1]
                    except ValueError:
                        warn_msg = 'Cannot convert the variable fecha wit value :\"{date}\" into a date \
                                    for plot {plotid}'.format(date=row['fecha'], plotid=ID)
                        logging.warn(warn_msg)
                #Nativo
                if row['name'] == 'Observaciones' and row.has_key('Observaciones'):
                    if row['Observaciones'] in ['',' ']:
                        survey.plots[ID].general_datos_parcela_commentario = '-'
                    else:
                        survey.plots[ID].general_datos_parcela_commentario = \
                            tools_lib.import_variable(row, 'Observaciones', 'string', ID)
                #Plantado
                if row['name'] == 'Observaciones'and row.has_key('observacion'):
                        if row['observacion'] in ['', ' ']:
                            survey.plots[ID].general_datos_parcela_commentario = '-'
                        else:
                            survey.plots[ID].general_datos_parcela_commentario = \
                                tools_lib.import_variable(row, 'observacion', 'string', ID)

                # If there is no observation record found in the database set '-'
                if survey.plots[ID].general_datos_parcela_commentario is None:
                    survey.plots[ID].general_datos_parcela_commentario = '-'

                if row['name'] == 'Distancias':
                    survey.plots[ID].track_archivo = row['track']

                if row['name'] == 'CoordenadasParcela':
                    survey.plots[ID].parcela_coordenadas_gps_coord_x = tools_lib.import_variable(row, 'oeste', 'float', ID)
                    survey.plots[ID].parcela_coordenadas_gps_coord_y = tools_lib.import_variable(row, 'sur', 'float', ID)
                    survey.plots[ID].parcela_coordenadas_gps_altidud = tools_lib.import_variable(row, 'altitud', 'int', ID)
                    survey.plots[ID].parcela_coordenadas_gps_altiudud_unit = 'metros'
                    survey.plots[ID].parcela_coordenadas_gps_coord_srs = 'EPSG:4326'

                if row['name'] == 'Agua':
                    survey.plots[ID].agua_agua_caudal = \
                        tools_lib.import_variable(row, 'tipoCaudal', 'code', ID, code_lists.agua_agua_caudal)
                    #If there is a tipocaudal code then there is water
                    if survey.plots[ID].agua_agua_caudal:
                        survey.plots[ID].agua_agua_presencia = 1
                    if row.has_key('manejo'):
                        survey.plots[ID].agua_agua_manejo = \
                            tools_lib.import_variable(row, 'manejo', 'code', ID, code_lists.si_no)
                    else:
                        survey.plots[ID].agua_agua_manejo = \
                            tools_lib.import_variable(row, 'Manejo', 'code', ID, code_lists.si_no)

                    if row.has_key('frecuencia_caudal'):
                        survey.plots[ID].agua_agua_frec = \
                            tools_lib.import_variable(row, 'frecuencia_caudal', 'code', ID, code_lists.agua_agua_frec)
                    else:
                        survey.plots[ID].agua_agua_frec = \
                            tools_lib.import_variable(row, 'frecuencia', 'code', ID, code_lists.agua_agua_frec)

                    if row.has_key('acuacultura'):
                        survey.plots[ID].agua_agua_acuicultura =\
                            tools_lib.import_variable(row, 'acuacultura', 'code', ID, code_lists.si_no)
                    else:
                        survey.plots[ID].agua_agua_acuicultura =\
                            tools_lib.import_variable(row, 'Acuacultura', 'code', ID, code_lists.si_no)

                    survey.plots[ID].agua_agua_contaminacion = \
                        tools_lib.import_variable(row, 'gradoContaminacion', 'code', ID, code_lists.agua_agua_contaminacion)

                if row['name'] == 'NombreAfluentes':
                    if row.has_key('nom_afluente'):
                           survey.plots[ID].agua_agua_nombre =\
                               tools_lib.import_variable(row, 'nom_afluente', 'string', ID)
                    else:
                        survey.plots[ID].agua_agua_nombre = \
                            tools_lib.import_variable(row, 'Nomb_afluente', 'string', ID)

                    survey.plots[ID].agua_agua_distancia_unit_name = 'metros'

                    survey.plots[ID].agua_agua_distancia =\
                        tools_lib.import_variable(row, 'distancia_agua', 'int', ID)

                if row['name'] == 'Relieve':
                    survey.plots[ID].relieve_relieve_ubicacion = \
                        tools_lib.import_variable(row, 'ubicación_relieve', 'code', ID, code_lists.relieve_ubicaion)
                    survey.plots[ID].relieve_relieve_exposicion = \
                        tools_lib.import_variable(row, 'exposicion_relieve', 'code', ID, code_lists.relieve_exposicion)
                    survey.plots[ID].relieve_relieve_pendiente = \
                        tools_lib.import_variable(row, 'pendiente', 'float', ID)
                    survey.plots[ID].relieve_relieve_pendiente_forma = \
                        tools_lib.import_variable(row, 'formaPendiente', 'code', ID, code_lists.relieve_pediente_forma)

                if row['name'] == 'Suelo':
                    survey.plots[ID].suelo_suelo_coneat = \
                        tools_lib.import_variable(row, 'grupoConeat', 'code', ID, code_lists.suelo_suelo_coneat)
                    survey.plots[ID].suelo_suelo_uso_tierra = \
                        tools_lib.import_variable(row, 'usoTierra', 'code', ID, code_lists.suelo_suelo_uso_tierra)
                    survey.plots[ID].suelo_suelo_uso_previo = \
                        tools_lib.import_variable(row, 'usoPrevio', 'code', ID, code_lists.suelo_suelo_uso_previo)
                    survey.plots[ID].suelo_suelo_labranza =\
                        tools_lib.import_variable(row, 'tipoLabranza', 'code', ID, code_lists.suelo_suelo_labranza)
                    survey.plots[ID].suelo_suelo_erosion_grado = \
                        tools_lib.import_variable(row, 'gradoErosion', 'code', ID, code_lists.suelo_suelo_erosion_grado)
                    survey.plots[ID].suelo_suelo_erosion_tipo = \
                        tools_lib.import_variable(row, 'tipoErosion', 'code', ID, code_lists.suelo_suelo_erosion_tipo)
                    survey.plots[ID].suelo_suelo_profundidad_horizonte = \
                        tools_lib.import_variable(row, 'profundidadPrimerHorizonte', 'code', ID, code_lists.suelo_suelo_profundidad_horizonte)
                    survey.plots[ID].suelo_suelo_profundidad_mantillo =  \
                        tools_lib.import_variable(row, 'profundidadMantillo', 'code', ID, code_lists.suelo_suelo_profundidad_humus_y_mantillo)
                    survey.plots[ID].suelo_suelo_profundidad_humus = \
                        tools_lib.import_variable(row, 'profundidadHumus', 'code', ID, code_lists.suelo_suelo_profundidad_humus_y_mantillo)
                    survey.plots[ID].suelo_suelo_color = \
                        tools_lib.import_variable(row, 'color', 'code', ID, code_lists.suelo_suelo_color)
                    survey.plots[ID].suelo_suelo_textura = \
                        tools_lib.import_variable(row, 'textura', 'code', ID, code_lists.suelo_suelo_textura)
                    survey.plots[ID].suelo_suelo_estructura = \
                        tools_lib.import_variable(row, 'estructura_suelo', 'code', ID, code_lists.suelo_suelo_estructura)
                    survey.plots[ID].suelo_suelo_drenaje = \
                        tools_lib.import_variable(row, 'drenaje', 'code', ID, code_lists.suelo_suelo_drenaje)
                    survey.plots[ID].suelo_suelo_infiltracion = \
                        tools_lib.import_variable(row, 'infiltracion', 'code', ID, code_lists.suelo_suelo_infiltracion)
                    survey.plots[ID].suelo_suelo_impedimento = \
                        tools_lib.import_variable(row, 'impedimento', 'code', ID, code_lists.si_no)
                    survey.plots[ID].suelo_suelo_olor = \
                        tools_lib.import_variable(row, 'olor', 'code', ID, code_lists.si_no)
                    survey.plots[ID].suelo_suelo_humedad = \
                        tools_lib.import_variable(row, 'humedad', 'code', ID, code_lists.suelo_suelo_humedad)
                    survey.plots[ID].suelo_suelo_pedregosidad = \
                        tools_lib.import_variable(row, 'pedregosidad', 'int', ID)
                    survey.plots[ID].suelo_suelo_rocosidad = \
                        tools_lib.import_variable(row, 'rocosidad', 'int', ID)
                    survey.plots[ID].suelo_suelo_pedregosidad_unit_name = 'porciento'
                    survey.plots[ID].suelo_suelo_rocosidad_unit_name = 'porciento'
                    survey.plots[ID].suelo_suelo_micorrizas = \
                        tools_lib.import_variable(row, 'micorrizas', 'code', ID, code_lists.si_no)
                    survey.plots[ID].suelo_suelo_fauna = \
                        tools_lib.import_variable(row, 'faunaSuelo', 'code', ID, code_lists.si_no)
                    survey.plots[ID].suelo_suelo_raices = \
                        tools_lib.import_variable(row, 'raices', 'code', ID, code_lists.suelo_suelo_raices)

                if row['name'] == 'CoberturaVegetal':
                    survey.plots[ID].cobertura_vegetal_cobertura_copas = \
                        tools_lib.import_variable(row, 'gradoCoberturaCopas', 'code', 'ID', code_lists.cobertura_grado)
                    survey.plots[ID].cobertura_vegetal_cobertura_sotobosque = \
                        tools_lib.import_variable(row, 'gradoSotobosque', 'code', ID, code_lists.cobertura_grado)
                    if survey.plots[ID].cobertura_vegetal_cobertura_sotobosque > 1:
                        survey.plots[ID].flora_soto_flora_soto_presencia= 1
                    else:
                        survey.plots[ID].flora_soto_flora_soto_presencia= 2
                    if row.has_key('coberturaHerbacea'):
                        survey.plots[ID].cobertura_vegetal_cobertura_herbacea = \
                        tools_lib.import_variable(row, 'coberturaHerbacea', 'code', ID, code_lists.cobertura_grado)
                    else:
                        survey.plots[ID].cobertura_vegetal_cobertura_herbacea = \
                        tools_lib.import_variable(row, 'coberturaHerbacea (%)', 'code', ID, code_lists.cobertura_grado)

                    survey.plots[ID].cobertura_vegetal_cobertura_residuos_plantas = \
                        tools_lib.import_variable(row, 'coberturaResiduosPlantas', 'code', ID, code_lists.cobertura_grado_residos)
                    survey.plots[ID].cobertura_vegetal_cobertura_residuos_cultivos = \
                        tools_lib.import_variable(row, 'coberturaResiduosCultivos', 'code', ID, code_lists.cobertura_grado_residos)

                if row['name'] == 'ProductosNoMadereros':
                    survey.plots[ID].ntfp_ntfp_ganado_tipo_1 = \
                        tools_lib.import_variable(row, 'tipoGanado', 'code', ID, code_lists.ntfp_ntfp_ganado_tipo)
                    survey.plots[ID].ntfp_ntfp_pastoreo_intens = \
                        tools_lib.import_variable(row, 'intensidadPastoreo', 'code', ID, code_lists.ntfp_ntfp_pastoreo_intens)
                    survey.plots[ID].ntfp_ntfp_prod_cultivo = \
                        tools_lib.import_variable(row, 'sistemasProduccion', 'code', ID, code_lists.ntfp_ntfp_prod_cultivo)
                    survey.plots[ID].ntfp_ntfp_prod_apicola = \
                        tools_lib.import_variable(row, 'produccionApicola', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_sombra = \
                        tools_lib.import_variable(row, 'sombra', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_rompe_vientos = \
                        tools_lib.import_variable(row, 'rompeVientos', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_hongos = \
                        tools_lib.import_variable(row, 'recoleccionHongos', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_aceites = \
                        tools_lib.import_variable(row, 'aceitesEsenciales', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_semillas = \
                        tools_lib.import_variable(row, 'obtencionSemillas', 'code', ID, code_lists.si_no)
                    #This variable is not available in all files
                    if row.has_key('actividadesCasaPesca'):
                        survey.plots[ID].ntfp_ntfp_caza_pesca = \
                            tools_lib.import_variable(row, 'actividadesCasaPesca', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_recreacion = \
                        tools_lib.import_variable(row, 'actividadesRecreacion', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_cientificos = \
                        tools_lib.import_variable(row, 'estudiosCientificos', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ntfp_ntfp_carbono = \
                        tools_lib.import_variable(row, 'fijacionCarbono', 'code', ID, code_lists.si_no)

                if row['name'] == 'ProblemasAmbientales':
                    survey.plots[ID].ambiental_ambiental_potabilidad = \
                        tools_lib.import_variable(row, 'pobreCalidadAgua', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ambiental_ambiental_polucion = \
                        tools_lib.import_variable(row, 'polucionAire', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ambiental_ambiental_fertalidad = \
                        tools_lib.import_variable(row, 'perdidaFertilidad', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ambiental_ambiental_invasion = \
                        tools_lib.import_variable(row, 'invasionEspecies', 'code', ID, code_lists.si_no)
                    survey.plots[ID].ambiental_ambiental_pesticida = \
                        tools_lib.import_variable(row, 'presenciaPesticidas', 'code', ID, code_lists.si_no)

                if row['name'] == 'Fuego':
                    survey.plots[ID].fuego_fuego_evidencia = \
                        tools_lib.import_variable(row, 'evidenciaFuego', 'code', ID, code_lists.fuego_fuego_evidencias)
                    survey.plots[ID].fuego_fuego_tipo = \
                        tools_lib.import_variable(row, 'tipoFuego', 'code', ID, code_lists.fuego_fuego_tipo)
                    survey.plots[ID].fuego_fuego_proposito = \
                        tools_lib.import_variable(row, 'propositoFuego', 'code', ID, code_lists.fuego_fuego_proposito)

                if survey.plots[ID].general_datos_parcela_bosque_tipo == 2:
                    if row['name'] == 'ForestacionMantenimientoEstructura':
                        survey.plots[ID].forestacion_forest_origen = \
                            tools_lib.import_variable(row, 'origenPlantacion', 'code', ID, code_lists.forestacion_forest_origen)
                        survey.plots[ID].forestacion_forest_estructura = \
                            tools_lib.import_variable(row, 'estructura_forestacion', 'code', ID,
                                                      code_lists.forestacion_forest_estructura)
                        survey.plots[ID].forestacion_forest_propiedad = \
                            tools_lib.import_variable(row, 'propiedadTierra', 'code', ID,
                                                      code_lists.forestacion_forest_propiedad)
                        survey.plots[ID].forestacion_forest_plan_manejo = \
                            tools_lib.import_variable(row, 'planManejo', 'code', ID,
                                                      code_lists.si_no)
                        survey.plots[ID].forestacion_forest_intervencion = \
                            tools_lib.import_variable(row, 'gradoIntervencion', 'code', ID,
                                                      code_lists.human_intervention_degree)
                        survey.plots[ID].forestacion_forest_madera_destino_1 = \
                            tools_lib.import_variable(row, 'destinoMadera', 'code', ID,
                                                      code_lists.forestacion_forest_madera_destino)
                        survey.plots[ID].forestacion_forest_silvicultura = \
                            tools_lib.import_variable(row, 'manejoSilvicultural', 'code', ID,
                                                      code_lists.si_no)
                        survey.plots[ID].forestacion_forest_tecnologia = \
                            tools_lib.import_variable(row, 'tecnologiaExplotacion', 'code', ID,
                                                      code_lists.forestacion_forest_tecnologia)
                    if row['name'] == 'Plantacion':
                        plant_especies = row['genero']+' '+row['especie_plantacion']
                        index = tools_lib.find_species_scientific(species_list, plant_especies)
                        warn_msg = "Could not find the species \"{species}\" in the species code list for plot: {plotid}" \
                            .format(species=plant_especies, plotid=ID)
                        try:
                            if index.__len__()>0:
                                survey.plots[ID].plantacion_plant_especie_code = species_list[index[0]].species_code
                                survey.plots[ID].plantacion_plant_especie_scientific_name = species_list[index[0]].scientific_name
                                survey.plots[ID].plantacion_plant_especie_vernacular_name = species_list[index[0]].common_name
                            else:
                                logging.warn(warn_msg)
                        except ValueError:
                                logging.warn(warn_msg)

                        warn_msg = "Could not convert the variable \"rango_edad\" with value: \"{value}\" to edad class for plot{plotid}" \
                            .format(value=row['rangoEdad'], plotid=ID)
                        if row.has_key('rangoEdad') and row['rangoEdad'] not in ['',' ','No se define']:
                            try:
                                edad_nr = tools_lib.convert_text_to_numbers(row['rangoEdad'], 'max', 'real')
                                if edad_nr is not None:
                                    edad = tools_lib.convert_plantacion_edad(float(edad_nr))
                                    survey.plots[ID].plantacion_plant_edad =  edad
                                else:
                                    logging.warn(warn_msg)
                            except ValueError:
                                logging.warn(warn_msg)
                        survey.plots[ID].plantacion_plant_regimen = \
                            tools_lib.import_variable(row, 'regimen', 'code', ID,
                                                      code_lists.plantacion_regimen)
                        survey.plots[ID].plantacion_plant_estado = \
                            tools_lib.import_variable(row, 'estadoGeneral', 'code', ID,
                                                      code_lists.plantacion_estado)
                        survey.plots[ID].plantacion_plant_raleo = \
                            tools_lib.import_variable(row, 'raleo', 'code', ID,
                                                      code_lists.plantacion_raleo)
                        survey.plots[ID].plantacion_plant_poda = \
                            tools_lib.import_variable(row, 'tienePoda', 'code', ID,
                                                      code_lists.si_no)
                        survey.plots[ID].plantacion_plant_poda_altura = \
                            tools_lib.import_variable(row, 'alturaPoda', 'float', ID)
                        survey.plots[ID].plantacion_plant_poda_altura_unit_name = 'metros'
                        survey.plots[ID].plantacion_plant_dist_fila = \
                            tools_lib.import_variable(row, 'distanciaFila', 'float', ID)
                        survey.plots[ID].plantacion_plant_dist_fila_unit_name='metros'
                        survey.plots[ID].plantacion_plant_dist_entrefila = \
                            tools_lib.import_variable(row, 'distanciaEntreFila', 'float', ID)
                        survey.plots[ID].plantacion_plant_dist_entrefila_unit_name = 'metros'
                        survey.plots[ID].plantacion_plant_regular = \
                            tools_lib.import_variable(row, 'parcelaRegular', 'code', ID, code_lists.si_no)
                        survey.plots[ID].plantacion_plant_fila_cantidad = \
                            tools_lib.import_variable(row, 'cantidadFilas', 'int', ID)
                        survey.plots[ID].plantacion_plant_dist_silvopast = \
                            tools_lib.import_variable(row, 'distanciaSilvopastoreo', 'float', ID)
                        survey.plots[ID].plantacion_plant_dist_silvopast_unit_name = 'metros'
                        survey.plots[ID].plantacion_plant_adaptacion = \
                            tools_lib.import_variable(row, 'adaptacionEspecie', 'code', ID, code_lists.plantacion_adaptation)

    info_msg = "Updated the plot information for {nplots} plots from the file: {file}"\
                    .format(nplots=counter.__len__(),file=os.path.basename(infile))
    print(info_msg)
    logging.info(info_msg)
