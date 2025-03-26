import bpy
import os
import pydicom as dicom
from collections import Counter
import tempfile
import shutil
import subprocess
import platform

def CorrigeTomoRawDef():

    context = bpy.context
    obj = context.object
    scn = context.scene

    os.chdir(scn.my_tool.path)

    if platform.system() == "Linux" or platform.system() == "Darwin":
        subprocess.call('for i in *; do gdcmconv -w -i $i -o $i; done', shell=True)
        print("Tomografia corrigida!!!")

class CorrigeTomoRaw(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "object.corrige_tomo_raw"
    bl_label = "CT-Scan fix raw"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
            CorrigeTomoRawDef()
            return {'FINISHED'}

bpy.utils.register_class(CorrigeTomoRaw)


def TomoRecRapidaDef():

    context = bpy.context
    obj = context.object
    scn = context.scene

    # Listar todos os arquivos

    ListaArquivosAbs = []


    #DiretorioDCM = '/home/linux3dcs/del/TOMOGRAFIAS_ESTUDOS/DAVI/000'

    for dirname, dirnames, filenames in os.walk(scn.my_tool.path):

        for filename in filenames:
            print(os.path.join(dirname, filename))
            ListaArquivosAbs.append(os.path.join(dirname, filename))

    #print(ListaArquivosAbs)

    ListaConvolutionKernel = []
    ListaSeriesNumber = []
    ListaArquivosDICOM = []
    #ListaInstanceCreationTime = []

    NaoEhDICOM = []

    # Pesquisa os arquivos
    for ArquivoAtual in ListaArquivosAbs:
        try:
            ds = dicom.dcmread(ArquivoAtual, force=True)

            ListaArquivosDICOM.append(ArquivoAtual)

            #ListaInstanceCreationTime.append(ds.InstanceCreationTime)
            try:
                ListaSeriesNumber.append(ds.SeriesNumber)
            except:
                print("Problem com o SeriesNumer")
                print("Series:", ArquivoAtual)

            try:
                ListaConvolutionKernel.append(ds.ConvolutionKernel)
            except:
                print("Problema com o ConvolutionKernel")
                print("ConvKernel:", ArquivoAtual)

        except:
           NaoEhDICOM.append(ArquivoAtual)
    #       print(ArquivoAtual, "Não é!")


    print("FINISHED!")

    #for i in NaoEhDICOM:
    #    print(i, "Não é DICOM!")

    #print(DiretorioDCM)
    #print(Counter(ListaInstanceCreationTime))
    print(Counter(ListaSeriesNumber))
    try:
        print(Counter(ListaConvolutionKernel))
    except:
        print("Problema ao imprimir o ConvKernel")

    SeriesValores = Counter(ListaSeriesNumber)

    print("SERIES")

    print(SeriesValores)

    listaSeries = []

    for i in SeriesValores:
        if i == "":
            i = "2312457886300"
        listaSeries.append([SeriesValores[i], int(i)])

    print("ORDEM ORIGINAL")
    print(listaSeries)

    # Calcula o número de arquivos por diretório
    print("SORT")
    listaFinal = sorted(listaSeries, reverse=True)
    print(sorted(listaSeries, reverse=True))

    print("Diretório com mais arquivos:", listaFinal[0][1])

    DiretorioFinal = listaFinal[0][1]


    # Copia os arquivos para diretório temporário

    tmpdirTomo = tempfile.mkdtemp()


    DCMNum = 0

    for ArquivoAtual in ListaArquivosDICOM:

        ds = dicom.dcmread(ArquivoAtual, force=True)


        try:
            if ds.SeriesNumber == DiretorioFinal:
                #print(ds.SeriesNumber )

                os.chdir(tmpdirTomo)

                shutil.copy(ArquivoAtual, "Copy-"+str(DCMNum))
                #print("Copiado de: ", ArquivoAtual, " Para: ", "Copy-"+str(DCMNum))
                DCMNum += 1
        except:
            print("Erro de leitura do SeriesNumber no:", ArquivoAtual)

    scn.my_tool.path = tmpdirTomo


    print("Arquivos DICOM copiados!")

    # Captura o 0018,1210 do primeiro arquivo

    ArquivoTopo = os.listdir(os.getcwd())[0]
    print("Arquivo topo:", ArquivoTopo)

    ds = dicom.dcmread(ArquivoTopo, force=True)

    try:
        ConvKernel = ds.ConvolutionKernel

        print("ConvolutionKernel:", ConvKernel)
    except:
        ConvKernel = ""
        print("Erro no ConvKernel!")

    try:
        Manufacturer = ds.Manufacturer

        print("Manufacturer", Manufacturer)
    except:
        Manufacturer = ""
        print("Erro no Manufacturer!")

    try:
        DimPixelsX = ds.Rows
        DimPixelsY = ds.Columns

        if DimPixelsX > 512 or DimPixelsY > 512:
            ReducaoTomo = "REDUZIR"
        else:
            ReducaoTomo = "NAO REDUZIR"

    except:
        ReducaoTomo = "Problema"
        print("Problema ao verificar as dimensões")

    # Reconstrói tomografia HELICOIDAL

    if not ConvKernel == "":
        print("Há ConvKernel!")

        if ConvKernel == "FC03" or ConvKernel =="FC04" or ConvKernel == "STANDARD" or ConvKernel == "H30s" or ConvKernel == "SOFT" or ConvKernel == "UB" or ConvKernel == "SA" or ConvKernel == "FC23" or ConvKernel == "FC08" or ConvKernel == ['Hr40f', '3'] or ConvKernel == "FC21" or ConvKernel =="A" or ConvKernel =="FC02" or ConvKernel =="B" or ConvKernel =="H23s" or ConvKernel =="H20s" or ConvKernel == "H31s" or ConvKernel == ['J30s', '3'] or ConvKernel == "H40s" or ConvKernel == "H31s" or ConvKernel == "B41s" or ConvKernel == "B70s" or ConvKernel == "H22s" or ConvKernel == ['J30f', '2'] or ConvKernel == "H20f":

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            bpy.context.scene.interesse_ossos = "200"
            bpy.context.scene.interesse_mole = "-300"
            bpy.context.scene.interesse_dentes = "1430"

            bpy.ops.object.gera_modelos_tomo()

        if ConvKernel == "BONE" or ConvKernel =="BONEPLUS" or ConvKernel =="FC30" or ConvKernel =="H70s" or ConvKernel =="D" or ConvKernel =="EA" or ConvKernel == ['Hr60f', '3'] or ConvKernel =="FC81" or ConvKernel =="YC" or ConvKernel =="H70h" or ConvKernel =="H60s" or ConvKernel == "H60f":

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            bpy.context.scene.interesse_ossos = "400"
            bpy.context.scene.interesse_mole = "-300"
            bpy.context.scene.interesse_dentes = "995"

            bpy.ops.object.gera_modelos_tomo()


    # Reconstrói tomografia CONE BEAM

    if ConvKernel == "" and not Manufacturer == "":
        print("Tentando pelo modelo...")

        if Manufacturer == "Imaging Sciences International":

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.context.scene.interesse_ossos = "358"
            bpy.context.scene.interesse_mole = "-629"
            bpy.context.scene.interesse_dentes = "962"


            bpy.ops.object.gera_modelos_tomo()


        if Manufacturer == "Xoran Technologies ®":

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.context.scene.interesse_ossos = "331"
            bpy.context.scene.interesse_mole = "-679"
            bpy.context.scene.interesse_dentes = "1052"

            bpy.ops.object.gera_modelos_tomo()


        if Manufacturer == "Planmeca":

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.context.scene.interesse_ossos = "330"
            bpy.context.scene.interesse_mole = "-548"
            bpy.context.scene.interesse_dentes = "756"

            bpy.ops.object.gera_modelos_tomo()


        if Manufacturer == "J.Morita.Mfg.Corp.":

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.context.scene.interesse_ossos = "245"
            bpy.context.scene.interesse_mole = "-315"
            bpy.context.scene.interesse_dentes = "585"

            bpy.ops.object.gera_modelos_tomo()


        if Manufacturer == "Carestream Health":

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.context.scene.interesse_ossos = "388"
            bpy.context.scene.interesse_mole = "-598"
            bpy.context.scene.interesse_dentes = "1013"

            bpy.ops.object.gera_modelos_tomo()


        if Manufacturer == "NewTom":

            bpy.ops.object.corrige_dicom()
            bpy.ops.object.corrige_tomo_raw()

            if ReducaoTomo == "REDUZIR":
                bpy.ops.object.reduz_dimensao_dicom()

            bpy.context.scene.interesse_ossos = "602"
            bpy.context.scene.interesse_mole = "-525"
            bpy.context.scene.interesse_dentes = "1061"

            bpy.ops.object.gera_modelos_tomo()

class TomoRecRapida(bpy.types.Operator):
    """Tooltip"""
    bl_idname = "object.gera_modelotomo_rec_rapida"
    bl_label = "CT-Scan fast auto reconstruction"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
            TomoRecRapidaDef()
            return {'FINISHED'}

bpy.utils.register_class(TomoRecRapida)
