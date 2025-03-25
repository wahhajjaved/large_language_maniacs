# -*- coding: utf-8 -*-
import time
import os
import logging
import zlib

from importlib import machinery, import_module
from binascii import unhexlify


from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.Qt import qApp
from PyQt5.QtCore import Qt, QSignalMapper

import pineboolib

from pineboolib import decorators, pnqt3ui
from pineboolib.pnconnection import PNConnection
from pineboolib.utils import filedir, one, Struct, XMLStruct, clearXPM, parseTable, _path, coalesce_path, _dir

from pineboolib.fllegacy.FLUtil import FLUtil
from pineboolib.fllegacy.FLSettings import FLSettings
from pineboolib.fllegacy.FLTranslator import FLTranslator
from pineboolib.fllegacy.FLAccessControlLists import FLAccessControlLists
from pineboolib.plugins.kugar.pnkugarplugins import PNKugarPlugins

import sys
"""
Almacena los datos del serividor de la BD principal
"""


class DBServer(XMLStruct):
    host = "127.0.0.1"
    port = "5432"


"""
Almacena los datos de autenticación de la BD principal
"""


class DBAuth(XMLStruct):
    username = "postgres"
    password = None


"""
Esta es la clase principal del projecto. Se puede acceder a esta con pineboolib.project desde cualquier parte del projecto
"""


class Project(object):
    logger = logging.getLogger("main.Project")
    conn = None  # Almacena la conexión principal a la base de datos
    debugLevel = 100

    #_initModules = None
    main_window = None
    acl_ = None
    _DGI = None
    deleteCache = None
    path = None
    kugarPluging = None
    _splash = None
    """
    Constructor
    """

    def __init__(self, DGI):
        self._DGI = DGI
        self.tree = None
        self.root = None
        self.dbserver = None
        self.dbauth = None
        self.dbname = None
        self.apppath = None
        self.tmpdir = None
        self.parser = None
        self.version = 0.5
        self.main_form_name = "eneboo" if not self._DGI.mobilePlatform() else "mobile"
        pineboolib.project = self
        self.deleteCache = False
        self.parseProject = False

        self.translator_ = []
        self.actions = {}
        self.tables = {}
        self.files = {}
        self.cur = None
        self.kugarPlugin = PNKugarPlugins()

        if not self._DGI.localDesktop():
            self._DGI.extraProjectInit()

    """
    Destructor
    """

    """
    Especifica el nivel de debug de la aplicación
    @param q Número con el nimvel espeficicado
    """

    def setDebugLevel(self, q):
        Project.debugLevel = q
        pnqt3ui.Options.DEBUG_LEVEL = q

    """
    Para especificar si usa fllarge unificado o multiple (Eneboo/Abanq)
    @return True (Tabla única), False (Múltiples tablas)
    """

    def singleFLLarge(self):
        ret = FLUtil().sqlSelect("flsettings", "valor", "flkey='FLLargeMode'")
        if ret == "True":
            return False

        return True

    """
    Retorna si hay o no acls cargados
    @return Objeto acl_
    """

    def acl(self):
        return self.acl_

    """
    Especifica los datos para luego conectarse a la BD.
    @param dbname. Nombre de la BD.
    @param host. Nombre del equipo anfitrión de la BD.
    @param port. Puerto a usar para conectarse a la BD.
    @param passwd. Contraseña de la BD.
    @param driveralias. Alias del pluging a usar en la conexión
    """

    def load_db(self, dbname, host, port, user, passwd, driveralias):
        self.dbserver = DBServer()
        self.dbserver.host = host
        self.dbserver.port = port
        self.dbserver.type = driveralias
        self.dbauth = DBAuth()
        self.dbauth.username = user
        self.dbauth.password = passwd
        self.dbname = dbname
        self.apppath = filedir("..")
        self.tmpdir = filedir("../tempdata")

        self.actions = {}
        self.tables = {}

    """
    def load(self, filename):
        self.parser = etree.elementTree.XMLParser(html=0, encoding="UTF-8")
        self.tree = etree.ElementTree.parse(filename, self.parser)
        self.root = self.tree.getroot()
        self.dbserver = DBServer(one(self.root.find("database-server")))
        self.dbauth = DBAuth(one(self.root.find("database-credentials")))
        self.dbname = one(self.root.find("database-name").text)
        self.apppath = one(self.root.find("application-path").text)
        self.tmpdir = filedir("../tempdata")
        if not getattr(self.dbserver, "host", None):
            self.dbserver.host = None

        if not getattr(self.dbserver, "port", None):
            self.dbserver.port = None

        if not getattr(self.dbserver, "type", None):
            self.dbserver.type = None

        if not self.dbauth:
            self.dbauth.username = None
            self.dbauth.password = None

        self.actions = {}
        self.tables = {}
        pineboolib.project = self
    """

    """
    Arranca el projecto. Conecta a la BD y carga los datos
    """

    def run(self):

        if not self.conn:
            self.conn = PNConnection(self.dbname, self.dbserver.host, self.dbserver.port,
                                     self.dbauth.username, self.dbauth.password, self.dbserver.type)

        if self.conn.conn is False:
            return False

        # TODO: Refactorizar esta función en otras más sencillas
        # Preparar temporal

        if self.deleteCache and not not os.path.exists(_dir("cache/%s" % self.conn.DBName())):
            if self._splash:
                self._splash.showMessage("Borrando caché ...", QtCore.Qt.AlignLeft, QtCore.Qt.white)
            self.logger.debug("DEVELOP: DeleteCache Activado\nBorrando %s", _dir(
                "cache/%s" % self.conn.DBName()))
            for root, dirs, files in os.walk(_dir("cache/%s" % self.conn.DBName()), topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            # borrando de share
            # for root, dirs, files in os.walk(_dir("../share/pineboo"), topdown=False):
            #    for name in files:
            #        if name.endswith("qs.py") or name.endswith("qs.py.debug") or name.endswith("qs.xml"):
            #            os.remove(os.path.join(root, name))

        if not os.path.exists(_dir("cache")):
            os.makedirs(_dir("cache"))

        # Conectar:

        # Se verifica que existen estas tablas
        for table in ("flareas", "flmodules", "flfiles", "flgroups", "fllarge", "flserial", "flusers", "flvar", "flmetadata"):
            self.conn.manager().createSystemTable(table)

        util = FLUtil()
        util.writeSettingEntry(u"DBA/lastDB", self.conn.DBName())
        self.cur = self.conn.cursor()
        self.areas = {}
        self.cur.execute(
            """ SELECT idarea, descripcion FROM flareas WHERE 1 = 1""")
        for idarea, descripcion in self.cur:
            self.areas[idarea] = Struct(idarea=idarea, descripcion=descripcion)

        self.areas["sys"] = Struct(idarea="sys", descripcion="Area de Sistema")

        # Obtener módulos activos
        self.cur.execute(""" SELECT idarea, idmodulo, descripcion, icono FROM flmodules WHERE bloqueo = %s """ %
                         self.conn.driver().formatValue("bool", "True", False))
        self.modules = {}
        for idarea, idmodulo, descripcion, icono in self.cur:
            icono = clearXPM(icono)
            self.modules[idmodulo] = Module(
                idarea, idmodulo, descripcion, icono)

        file_object = open(filedir("..", "share", "pineboo", "sys.xpm"), "r")
        icono = file_object.read()
        file_object.close()
        icono = clearXPM(icono)

        self.modules["sys"] = Module("sys", "sys", "Administración", icono)

        # Descargar proyecto . . .

        self.cur.execute(
            """ SELECT idmodulo, nombre, sha FROM flfiles WHERE NOT sha = '' ORDER BY idmodulo, nombre """)
        size_ = len(self.cur.fetchall())

        self.cur.execute(
            """ SELECT idmodulo, nombre, sha FROM flfiles WHERE NOT sha = '' ORDER BY idmodulo, nombre """)
        f1 = open(_dir("project.txt"), "w")
        self.files = {}
        if self._DGI.useDesktop() and self._DGI.localDesktop():
            tiempo_ini = time.time()
        if not os.path.exists(_dir("cache")):
            raise AssertionError
        p = 0
        pos_qs = 1
        for idmodulo, nombre, sha in self.cur:
            p = p + 1
            if idmodulo not in self.modules:
                continue  # I
            fileobj = File(idmodulo, nombre, sha)
            if nombre in self.files:
                self.logger.warn(
                    "run: file %s already loaded, overwritting..." % nombre)
            self.files[nombre] = fileobj
            self.modules[idmodulo].add_project_file(fileobj)
            f1.write(fileobj.filekey + "\n")
            if os.path.exists(_dir("cache", fileobj.filekey)):
                continue
            fileobjdir = os.path.dirname(_dir("cache", fileobj.filekey))
            if not os.path.exists(fileobjdir):
                os.makedirs(fileobjdir)

            cur2 = self.conn.cursor()
            sql = "SELECT contenido FROM flfiles WHERE idmodulo = %s AND nombre = %s AND sha = %s" % (self.conn.driver().formatValue(
                "string", idmodulo, False), self.conn.driver().formatValue("string", nombre, False), self.conn.driver().formatValue("string", sha, False))
            cur2.execute(sql)
            qs_count = 0
            for (contenido,) in cur2:

                encode_ = "ISO-8859-15"
                if str(nombre).endswith(".kut") or str(nombre).endswith(".ts"):
                    encode_ = "utf-8"

                if not os.path.exists(_dir("cache", fileobj.filekey)):
                    settings = FLSettings()
                    if settings.readBoolEntry("application/isDebuggerMode", False):
                        if self._splash:
                            self._splash.showMessage("Volcando a caché %s..." %
                                                     nombre, QtCore.Qt.AlignLeft, QtCore.Qt.white)

                    f2 = open(_dir("cache", fileobj.filekey), "wb")

                    txt = contenido.encode(encode_, "replace")

                    f2.write(txt)

                    f2.close()

            if self.parseProject and nombre.endswith(".qs") and settings.readBoolEntry("application/isDebuggerMode", False):
                # if self._splash:
                #    self._splash.showMessage("Convirtiendo %s ( %d/ ??) ..." %
                #                             (nombre, pos_qs), QtCore.Qt.AlignLeft, QtCore.Qt.white)
                self.parseScript(_dir("cache", fileobj.filekey), "(%d de %d)" % (p, size_))

                pos_qs += 1

        if self._DGI.useDesktop() and self._DGI.localDesktop():
            tiempo_fin = time.time()
            self.logger.info("Descarga del proyecto completo a disco duro: %.3fs", (tiempo_fin - tiempo_ini))

        # Cargar el núcleo común del proyecto
        idmodulo = 'sys'
        for root, dirs, files in os.walk(filedir("..", "share", "pineboo")):
            for nombre in files:
                if root.find("modulos") == -1:
                    fileobj = File(idmodulo, nombre, basedir=root)
                    self.files[nombre] = fileobj
                    self.modules[idmodulo].add_project_file(fileobj)
                    if self.parseProject and nombre.endswith(".qs"):
                        self.parseScript(_dir(root, nombre))

        if self._splash:
            self._splash.showMessage("Cargando traducciones ...", QtCore.Qt.AlignLeft, QtCore.Qt.white)

        from pineboolib.pncontrolsfactory import aqApp
        aqApp.loadTranslations()
        self.acl_ = FLAccessControlLists()
        self.acl_.init_()

    """
    LLama a una función del projecto.
    @param function. Nombre de la función a llamar.
    @param aList. Array con los argumentos.
    @param objectContext. Contexto en el que se ejecuta la función.
    @param showException. Boolean que especifica si se muestra los errores.
    @return Boolean con el resultado.
    """

    def call(self, function, aList, object_context=None, showException=True):
        # FIXME: No deberíamos usar este método. En Python hay formas mejores
        # de hacer esto.
        self.logger.trace("JS.CALL: fn:%s args:%s ctx:%s",
                          function, aList, object_context, stack_info=True)

        # Tipicamente flfactalma.iface.beforeCommit_articulos()
        if function[-2:] == "()":
            function = function[:-2]

        aFunction = function.split(".")

        if not object_context:
            if not aFunction[0] in self.actions:
                if len(aFunction) > 1:
                    if showException:
                        self.logger.error("No existe la acción %s en el módulo %s", aFunction[1], aFunction[0])
                else:
                    if showException:
                        self.logger.error("No existe la acción %s", aFunction[0])
                return False

            funAction = self.actions[aFunction[0]]
            if aFunction[1] == "iface" or len(aFunction) == 2:
                mW = funAction.load()
                if len(aFunction) == 2:
                    object_context = None
                    if hasattr(mW, "iface"):
                        if hasattr(mW.iface, aFunction[1]):
                            object_context = mW.iface

                    if not object_context:
                        object_context = mW

                else:
                    object_context = mW.iface

            elif aFunction[1] == "widget":
                fR = None
                funAction.load_script(aFunction[0], fR)
                object_context = fR.iface
            else:
                return False

            if not object_context:
                if showException:
                    self.logger.error(
                        "No existe el script para la acción %s en el módulo %s", aFunction[0], aFunction[0])
                return False

        if len(aFunction) == 1:  # Si no hay puntos en la llamada a functión
            function_name = aFunction[0]

        elif len(aFunction) > 2:  # si existe self.iface por ejemplo
            function_name = aFunction[2]
        else:
            function_name = aFunction[1]  # si no exite self.iiface

        fn = getattr(object_context, function_name, None)

        if fn is None:
            if showException:
                self.logger.error(
                    "No existe la función %s en %s", function_name, aFunction[0])
            return True  # FIXME: Esto devuelve true? debería ser false, pero igual se usa por el motor para detectar propiedades

        try:
            if aList:
                return fn(*aList)
            else:
                return fn()
        except Exception:
            if showException:
                self.logger.exception("js.call: error al llamar %s de %s", function, object_context)

        return None

    #@decorators.NotImplementedWarn
    # def initToolBox(self):
    #    pass
    """
    Convierte un script .qs a .py lo deja al lado
    @param scriptname, Nombre del script a convertir
    """

    def parseScript(self, scriptname, txt_=""):

        # Intentar convertirlo a Python primero con flscriptparser2
        if not os.path.isfile(scriptname):
            raise IOError
        python_script_path = (
            scriptname + ".xml.py").replace(".qs.xml.py", ".qs.py")
        if not os.path.isfile(python_script_path) or pineboolib.no_python_cache:
            settings = FLSettings()
            if settings.readBoolEntry("application/isDebuggerMode", False):
                from pineboolib.fllegacy.FLUtil import FLUtil
                util = FLUtil()
                file_name = scriptname.split("\\") if util.getOS() == "WIN32" else scriptname.split("/")

                file_name = file_name[len(file_name) - 2]

                msg = "Convirtiendo a Python . . . %s.qs %s" % (file_name, txt_)
                if settings.readBoolEntry("ebcomportamiento/SLConsola", False):
                    self.logger.info(msg)

                if self._splash:
                    self._splash.showMessage(msg, QtCore.Qt.AlignLeft, QtCore.Qt.white)

                else:
                    if settings.readBoolEntry("ebcomportamiento/SLInterface", False):
                        from pineboolib.pncontrolsfactory import aqApp
                        aqApp.popupWarn(msg)

            from pineboolib.flparser import postparse
            try:
                postparse.pythonify(scriptname)
            except Exception as e:
                self.logger.warn("El fichero %s no se ha podido convertir: %s", scriptname, e)

    """
    Lanza los test
    @param name, Nombre del test específico. Si no se especifica se lanzan todos los tests disponibles
    @return Texto con la valoración de los test aplicados
    """

    def test(self, name=None):
        dirlist = os.listdir(filedir("../pineboolib/plugins/test"))
        testDict = {}
        for f in dirlist:
            if not f[0:2] == "__":
                f = f[:f.find(".py")]
                mod_ = importlib.import_module(
                    "pineboolib.plugins.test.%s" % f)
                test_ = getattr(mod_, f)
                testDict[f] = test_

        maxValue = 0
        value = 0
        result = None
        resultValue = 0
        if name:
            try:
                t = testDict[name]()
                maxValue = t.maxValue()
                value = t.run()
            except Exception:
                result = False
        else:

            for test in testDict.keys():
                print("test", test)
                t = testDict[test]()
                maxValue = maxValue + t.maxValue
                v = t.run()
                print("result", test, v, "/", t.maxValue)
                value = value + v

        if result is None and maxValue > 0:
            resultValue = value

        result = "%s/%s" % (resultValue, maxValue)

        return result

    """
    Retorna la carpeta temporal predefinida de pineboo
    @return ruta a la carpeta temporal
    """

    def getTempDir(self):
        return self.tmpdir


"""
Esta clase almacena la información de los módulos cargados
"""


class Module(object):
    """
    Constructor
    @param areaid. Identificador de area.
    @param name. Nombre del módulo
    @param description. Descripción del módulo
    @param icon. Icono del módulo
    """

    def __init__(self, areaid, name, description, icon):
        self.areaid = areaid
        self.name = name
        self.description = description  # En python2 era .decode(UTF-8)
        self.icon = icon
        self.files = {}
        self.tables = {}
        self.loaded = False
        self.path = pineboolib.project.path
        self.logger = logging.getLogger("main.Module")

    """
    Añade ficheros al array que controla que ficehros tengo.
    @param fileobj. Objeto File con información del fichero
    """

    def add_project_file(self, fileobj):
        self.files[fileobj.filename] = fileobj

    """
    Carga las acciones pertenecientes a este módulo
    @return Boolean. True si ok, False si hay problemas
    """

    def load(self):
        pathxml = _path("%s.xml" % self.name)
        pathui = _path("%s.ui" % self.name)
        if pathxml is None:
            self.logger.error("módulo %s: fichero XML no existe", self.name)
            return False
        if pathui is None:
            self.logger.error("módulo %s: fichero UI no existe", self.name)
            return False
        if pineboolib.project._DGI.useDesktop() and pineboolib.project._DGI.localDesktop():
            tiempo_1 = time.time()
        try:
            self.actions = ModuleActions(self, pathxml, self.name)
            self.actions.load()
            if pineboolib.project._DGI.useDesktop():
                self.mainform = MainForm(self, pathui)
                self.mainform.load()
        except Exception as e:
            self.logger.exception("Al cargar módulo %s:", self.name)
            return False

        # TODO: Load Main Script:
        self.mainscript = None
        # /-----------------------
        if pineboolib.project._DGI.useDesktop() and pineboolib.project._DGI.localDesktop():
            tiempo_2 = time.time()

        for tablefile in self.files:
            if not tablefile.endswith(".mtd"):
                continue
            name, ext = os.path.splitext(tablefile)
            try:
                contenido = str(open(_path(tablefile),
                                     "rb").read(), "ISO-8859-15")
            except UnicodeDecodeError as e:
                self.logger.error(
                    "Error al leer el fichero %s %s", tablefile, e)
                continue
            tableObj = parseTable(name, contenido)
            if tableObj is None:
                self.logger.warn(
                    "No se pudo procesar. Se ignora tabla %s/%s ", self.name, name)
                continue
            self.tables[name] = tableObj
            pineboolib.project.tables[name] = tableObj

        if pineboolib.project._DGI.useDesktop() and pineboolib.project._DGI.localDesktop():
            tiempo_3 = time.time()
            if tiempo_3 - tiempo_1 > 0.2:
                self.logger.debug("Carga del módulo %s : %.3fs ,  %.3fs",
                                  self.name, tiempo_2 - tiempo_1, tiempo_3 - tiempo_2)

        self.loaded = True
        return True


"""
Clase que gestiona cada uno de los ficheros de un módulo
"""


class File(object):
    """
    Constructor
    @param module. Identificador del módulo propietario
    @param filename. Nombre del fichero
    @param sha. Código sha1 del contenido del fichero
    @param basedir. Ruta al fichero en cache
    """

    def __init__(self, module, filename, sha=None, basedir=None):
        self.module = module
        self.filename = filename
        self.sha = sha
        if filename.endswith(".qs.py"):
            self.ext = ".qs.py"
            self.name = os.path.splitext(os.path.splitext(filename)[0])[0]
        else:
            self.name, self.ext = os.path.splitext(filename)

        db_name = pineboolib.project.conn.DBName()

        if self.sha:
            self.filekey = "%s/%s/file%s/%s/%s%s" % (
                db_name, module, self.ext, self.name, sha, self.ext)
        else:
            self.filekey = filename
        self.basedir = basedir

    """
    Devuelve la ruta absoluta del fichero
    @return Ruta absoluta del fichero
    """

    def path(self):
        if self.basedir:
            # Probablemente porque es local . . .
            return _dir(self.basedir, self.filename)
        else:
            # Probablemente es remoto (DB) y es una caché . . .
            return _dir("cache", *(self.filekey.split("/")))


"""
Clase encargada de gestionar los diferentes módulos de inteligencia lógica del projecto
"""


class DelayedObjectProxyLoader(object):

    """
    Constructor
    """

    def __init__(self, obj, *args, **kwargs):
        self._name = "unnamed-loader"
        if "name" in kwargs:
            self._name = kwargs["name"]
            del kwargs["name"]
        self._obj = obj
        self._args = args
        self._kwargs = kwargs
        self.loaded_obj = None
        self.logger = logging.getLogger("main.DelayedObjectProxyLoader")

    """
    Carga un objeto nuevo
    @return objeto nuevo o si ya existe , cacheado
    """

    def __load(self):
        if not self.loaded_obj:
            self.logger.debug(
                "DelayedObjectProxyLoader: loading %s %s( *%s **%s)",
                self._name, self._obj, self._args, self._kwargs)
            self.loaded_obj = self._obj(*self._args, **self._kwargs)
        return self.loaded_obj

    """
    Retorna una función buscada
    @param name. Nombre del la función buscada
    @return el objecto del XMLAction afectado
    """

    def __getattr__(self, name):  # Solo se lanza si no existe la propiedad.
        obj = self.__load()
        if obj:
            return getattr(obj, name)
        else:
            return None


"""
Genera un arbol con las acciones de los diferentes módulos
@param name. Nombre del la función buscada
@return el objecto del XMLAction afectado
"""


class ModuleActions(object):
    """
    Constructor
    @param module. Identificador del módulo
    @param path. Ruta del módulo
    @param modulename. Nombre del módulo
    """

    def __init__(self, module, path, modulename):
        self.mod = module
        self.path = path
        self.moduleName = modulename
        self.logger = logging.getLogger("main.ModuleActions")
        if not self.path:
            self.logger.error(
                "El módulo no tiene un path válido %s", self.moduleName)

    """
    Carga las actions del módulo en el projecto
    """

    def load(self):
        # Ojo: Almacena un arbol con los módulos cargados
        from pineboolib import qsa as qsa_dict_modules

        self.tree = pineboolib.utils.load2xml(self.path)
        self.root = self.tree.getroot()

        action = XMLAction()
        action.mod = self
        action.name = self.mod.name
        action.alias = self.mod.name
        # action.form = self.mod.name
        action.form = None
        action.table = None
        action.scriptform = self.mod.name
        pineboolib.project.actions[action.name] = action
        if hasattr(qsa_dict_modules, action.name):
            self.logger.debug(
                "No se sobreescribe variable de entorno %s", action.name)
        else:
            setattr(qsa_dict_modules, action.name, DelayedObjectProxyLoader(
                action.load, name="QSA.Module.%s" % action.name))

        for xmlaction in self.root:
            action = XMLAction(xmlaction)
            action.mod = self
            try:
                name = action.name
            except AttributeError:
                name = "unnamed"
            pineboolib.project.actions[name] = action
            if name != "unnamed":
                if hasattr(qsa_dict_modules, "form" + name):
                    self.logger.debug(
                        "No se sobreescribe variable de entorno %s", "form" + name)
                else:
                    delayed_action = DelayedObjectProxyLoader(
                        action.load,
                        name="QSA.Module.%s.Action.form%s" % (self.mod.name, name))
                    setattr(qsa_dict_modules, "form" + name, delayed_action)

                if hasattr(qsa_dict_modules, "formRecord" + name):
                    self.logger.debug(
                        "No se sobreescribe variable de entorno %s", "formRecord" + name)
                else:
                    setattr(qsa_dict_modules, "formRecord" + name, DelayedObjectProxyLoader(
                        action.formRecordWidget, name="QSA.Module.%s.Action.formRecord%s" % (self.mod.name, name)))

    """
    Busca si es propietario de una action
    """

    def __contains__(self, k):
        return k in pineboolib.project.actions

    """
    Recoge una action determinada
    @param name. Nombre de la action
    @return Retorna el XMLAction de la action dada
    """

    def __getitem__(self, name):
        return pineboolib.project.actions[name]

    """
    Añade una action a propiedad del módulo
    @param name. Nombre de la action
    @param action_. Action a añadir a la propiedad del módulo
    """

    def __setitem__(self, name, action_):
        raise NotImplementedError("Actions are not writable!")
        #pineboolib.project.actions[name] = action_


"""
Continene la información del mainForm de cada módulo
"""


class MainForm(object):
    logger = logging.getLogger("main.MainForm")

    """
    Constructor
    @param module. Módulo al que pertenece el mainForm
    @param path. Ruta del módulo
    """

    def __init__(self, module, path):
        self.mod = module
        self.path = path
        assert path

    """
    Carga los actions del mainForm del módulo
    """

    def load(self):
        self.tree = pineboolib.utils.load2xml(self.path)
        self.root = self.tree.getroot()
        self.actions = {}
        self.pixmaps = {}
        if pineboolib.project._DGI.useDesktop():
            for image in self.root.findall("images//image[@name]"):
                name = image.get("name")
                xmldata = image.find("data")
                img_format = xmldata.get("format")
                data = unhexlify(xmldata.text.strip())
                if img_format == "XPM.GZ":
                    data = zlib.decompress(data, 15)
                    img_format = "XPM"

                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(data, img_format)
                icon = QtGui.QIcon(pixmap)
                self.pixmaps[name] = icon

        for xmlaction in self.root.findall("actions//action"):
            action = XMLMainFormAction(xmlaction)
            action.mainform = self
            action.mod = self.mod
            iconSet = getattr(action, "iconSet", None)
            action.icon = None
            if iconSet in self.pixmaps.keys():
                try:
                    action.icon = self.pixmaps[iconSet]
                except Exception as e:
                    if pineboolib.project._DGI.useDesktop():
                        self.logger.exception(
                            "main.Mainform: Error al intentar decodificar icono de accion. No existe.")
            else:
                action.iconSet = None

            self.actions[action.name] = action
            if not pineboolib.project._DGI.localDesktop():
                pineboolib.project._DGI.mainForm().mainWindow.loadAction(action)

            # Asignamos slot a action
            for slots in self.root.findall("connections//connection"):
                slot = XMLStruct(slots)
                if slot._v("sender") == action.name:
                    action.slot = slot._v("slot")
                    action.slot = action.slot.replace('(', '')
                    action.slot = action.slot.replace(')', '')
                if not pineboolib.project._DGI.localDesktop():
                    pineboolib.project._DGI.mainForm().mainWindow.loadConnection(action)

        self.toolbar = []
        sett_ = FLSettings()
        if not sett_.readBoolEntry("ebcomportamiento/ActionsMenuRed", False):
            for toolbar_action in self.root.findall("toolbars//action"):
                self.toolbar.append(toolbar_action.get("name"))
                if not pineboolib.project._DGI.localDesktop():
                    pineboolib.project._DGI.mainForm().mainWindow.loadToolBarsAction(
                        toolbar_action.get("name"))
        else:
            # FIXME: cargar solo las actions de los menus
            sett_.writeEntry("ebcomportamiento/ActionsMenuRed", False)


"""
Contiene Información de cada action del mainForm
"""


class XMLMainFormAction(XMLStruct):
    name = "unnamed"
    text = ""
    mainform = None
    mod = None
    prj = None
    slot = None
    logger = logging.getLogger("main.XMLMainFormAction")

    """
    Lanza la action
    """

    def run(self):
        self.logger.debug("Running: %s %s %s", self.name, self.text, self.slot)
        try:
            action = self.mod.actions[self.name]
            getattr(action, self.slot, "unknownSlot")()
        finally:
            self.logger.debug(
                "END of Running: %s %s %s",
                self.name, self.text, self.slot)


"""
Contiene información de las actions especificadas en el .xml del módulo
"""


class XMLAction(XMLStruct):
    logger = logging.getLogger("main.XMLAction")

    """
    Constructor
    """

    def __init__(self, *args, **kwargs):
        super(XMLAction, self).__init__(*args, **kwargs)
        self.form = self._v("form")
        self.name = self._v("name")
        self.script = self._v("script")
        self.table = self._v("table")
        self.mainform = self._v("mainform")
        self.mainscript = self._v("mainscript")
        self.formrecord = self._v("formrecord")
        self.mainform_widget = None
        self.formrecord_widget = None
        self._loaded = False
        self._record_loaded = False

    """
    Carga FLFormRecordDB por defecto
    @param cursor. Asigna un cursor al FLFormRecord
    @return widget con form inicializado
    """

    def loadRecord(self, cursor):
        if not getattr(self, "formrecord", None):
            self.logger.warn(
                "Record action %s is not defined. Canceled !", self.name)
            return None
        self.logger.debug("Loading record action %s . . . ", self.name)
        fRWidget = pineboolib.project.conn.managerModules().createFormRecord(self, None, cursor, None)
        if not fRWidget.loaded:
            return None
        self.formrecord_widget = fRWidget
        self.formrecord_widget.setWindowModality(Qt.ApplicationModal)
        self._record_loaded = True
        if self.formrecord_widget:
            self.logger.debug(
                "End of record action load %s (iface:%s ; widget:%s)",
                self.name, self.formrecord_widget.iface, self.formrecord_widget.widget)

        # self.initModule(self.name)

        return self.formrecord_widget

    def load(self):
        self._loaded = False
        if self.mainform_widget:
            self._loaded = getattr(self.mainform_widget, "_loaded", False)

        if self._loaded:
            return self.mainform_widget
        self.logger.debug("Loading action %s . . . ", self.name)
        w = pineboolib.project.main_window.w_
        if not self._loaded:
            if pineboolib.project._DGI.useDesktop():
                self.mainform_widget = pineboolib.project.conn.managerModules().createForm(self, None, w, None)
            else:
                from pineboolib.utils import Struct
                self.mainform_widget = Struct()
                self.mainform_widget.action = self
                self.load_script(getattr(self, "scriptform", None), self.mainform_widget)

            self._loaded = True
            self.logger.debug(
                "End of action load %s (iface:%s ; widget:%s)",
                self.name, getattr(self.mainform_widget, "iface", None), getattr(self.mainform_widget, "widget", None))

        return self.mainform_widget
    """
    Abre el FLFormDB por defecto
    """

    def openDefaultForm(self):
        self.logger.debug("Opening default form for Action %s", self.name)
        w = pineboolib.project.main_window
        # self.initModule(self.name)
        self.mainform_widget = pineboolib.project.conn.managerModules().createForm(self,
                                                                                   None, w, None)
        w.addFormTab(self)

    """
    Llama a la función main de una action
    """

    def execMainScript(self, name):
        a = pineboolib.project.conn.manager().action(name)
        if not a:
            self.logger.warn("No existe la acción %s", name)
            return
        pineboolib.project.call("%s.main" % a.name(), [], None, True)

    """
    Retorna el widget del formrecord
    """

    def formRecord(self):
        return self.formrecord
    """
    Retorna el widget del formRecord. Esto es necesario porque a veces no hay un FLformRecordDB inicialidado todavía
    @return wigdet del formRecord.
    """

    def formRecordWidget(self):
        scriptName = getattr(self, "scriptformrecord", None)
        # Si no existe self.form_widget, lo carga con load_script. NUNCA con loadRecord.
        # Así cuando se haga un loadRecord de verdad (desde
        # openDefaultFormRecord, este se cargara con su cursor de verdad
        if not self.formrecord_widget:
            self.load_script(scriptName, None)

            self.formrecord_widget = self.script.form
            # self.initModule(self.name)

        return self.formrecord_widget

    """
    Abre el FLFormRecordDB por defecto
    @param cursor. Cursor a usar por el FLFormRecordDB
    """

    def openDefaultFormRecord(self, cursor):
        self.logger.info("Opening default formRecord for Action %s", self.name)
        w = self.loadRecord(cursor)
        # w.init()
        if w:
            if pineboolib.project._DGI.localDesktop():
                w.show()

    """
    Ejecuta el script por defecto
    """

    def execDefaultScript(self):
        self.logger.debug("Executing default script for Action %s", self.name)
        self.scriptform = getattr(self, "scriptform", None)
        self.load_script(self.scriptform, None)

        self.mainform_widget = self.script.form
        # self.initModule(self.name)
        if self.mainform_widget.iface:
            self.mainform_widget.iface.main()
        else:
            self.mainform_widget.main()

    """
    Convierte un script qsa en .py y lo carga
    @param scriptname. Nombre del script a convertir
    @param parent. Objecto al que carga el script, si no se especifica es a self.script
    """

    def load_script(self, scriptname, parent=None):
        if scriptname:
            scriptname = scriptname.replace(".qs", "")
        if scriptname:
            self.logger.info("Cargando script %s de %s accion %s",
                             scriptname, parent, self.name)

        parent_ = parent
        if parent is None:
            parent = self
            action_ = self
        else:
            action_ = parent._action

        # Si ya esta cargado se reusa...
        # if getattr(self, "script", None) and parent_:
        #    if getattr(self.script, "form", None):
        #        parent.script = self.script
        #        parent.widget = self.script.form
        #    else:
        #        if getattr(self.script.form, "iface", None):
        #            parent.iface = self.script.form.iface
        #        return

            # import aqui para evitar dependencia ciclica
        from pineboolib.utils import convertFLAction
        if not isinstance(action_, XMLAction):
            action_ = convertFLAction(action_)

        python_script_path = None
        # primero default, luego sobreescribimos
        from pineboolib import emptyscript
        parent.script = emptyscript

        if scriptname is None:
            parent.script.form = parent.script.FormInternalObj(
                action=action_, project=pineboolib.project, parent=parent)
            parent.widget = parent.script.form
            parent.iface = parent.widget.iface
            return

        script_path_qs = _path(scriptname + ".qs", False)
        script_path_py = coalesce_path(
            scriptname + ".py", scriptname + ".qs.py", None)

        overload_pyfile = os.path.join(
            pineboolib.project.tmpdir, "overloadpy", scriptname + ".py")
        if os.path.isfile(overload_pyfile):
            self.logger.warn(
                "Cargando %s desde overload en lugar de la base de datos!!", scriptname)
            try:
                parent.script = machinery.SourceFileLoader(
                    scriptname, overload_pyfile).load_module()
            except Exception as e:
                self.logger.exception(
                    "ERROR al cargar script OVERLOADPY para la accion %s:", action_.name)

        elif script_path_py:
            script_path = script_path_py
            self.logger.info("Loading script PY %s . . . ", scriptname)
            if not os.path.isfile(script_path):
                raise IOError
            try:
                self.logger.info(
                    "Cargando %s : %s ", scriptname,
                    script_path.replace(pineboolib.project.tmpdir, "tempdata"))
                parent.script = machinery.SourceFileLoader(
                    scriptname, script_path).load_module()
            except Exception as e:
                self.logger.exception(
                    "ERROR al cargar script PY para la accion %s:", action_.name)

        elif script_path_qs:
            script_path = script_path_qs
            pineboolib.project.parseScript(script_path)
            self.logger.info("Loading script QS %s . . . ", scriptname)
            python_script_path = (
                script_path + ".xml.py").replace(".qs.xml.py", ".qs.py")
            try:
                self.logger.info(
                    "Cargando %s : %s ", scriptname,
                    python_script_path.replace(pineboolib.project.tmpdir, "tempdata"))
                parent.script = machinery.SourceFileLoader(
                    scriptname, python_script_path).load_module()
            except Exception as e:
                self.logger.exception(
                    "ERROR al cargar script QS para la accion %s:", action_.name)

        parent.script.form = parent.script.FormInternalObj(
            action_, pineboolib.project, parent_)
        if parent_:
            parent.widget = parent.script.form
            if getattr(parent.widget, "iface", None):
                parent.iface = parent.widget.iface

        return

    def unknownSlot(self):
        self.logger.error("Executing unknown script for Action %s", self.name)
        # Aquí debería arrancar el script

    """
    Inicializa el módulo del form en caso de que no se inicializara ya
    """

    # def initModule(self, name):

    #    moduleName = pineboolib.project.actions[name].mod.moduleName
    #    if moduleName in (None, "sys"):
    #        return
    #    if moduleName not in pineboolib.project._initModules:
    #        pineboolib.project._initModules.append(moduleName)
    #        pineboolib.project.call("%s.iface.init()" % moduleName, [], None, False)
    #        return
