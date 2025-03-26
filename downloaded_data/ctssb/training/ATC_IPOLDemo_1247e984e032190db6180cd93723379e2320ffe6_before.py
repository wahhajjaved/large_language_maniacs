"""
Demonstration of paper:  Adaptive Tangential Cover for Noisy Digital Contours
demo editor: Bertrand Kerautret
"""

from lib import base_app, build, http, image, config
from lib.misc import app_expose, ctime
from lib.base_app import init_app

import cherrypy
from cherrypy import TimeoutError
import os.path
import shutil
import time

class app(base_app):
    """ template demo app """

    title = "Knot Detection from Accumulation Map by Polar Scan: Online Demonstration"
    xlink_article = 'http://www.ipol.im/'
    xlink_src = 'http://www.ipol.im/pub/pre/67/gjknd_1.1.tgz'
    dgtal_src = 'https://github.com/kerautret/DGtal.git'
    demo_src_filename  = 'gjknd_1.1.tgz'
    demo_src_dir = 'ATC_IPOLDemo'


    input_nb = 1 # number of input images
    input_max_pixels = 4096 * 4096 # max size (in pixels) of an input image
    input_max_weight = 1 * 4096 * 4096 # max size (in bytes) of an input file
    input_dtype = '3x8i' # input image expected data type
    input_ext = '.png'   # input image expected extension (ie file format)
    is_test = False       # switch to False for deployment
    commands = []
    list_commands = ""

    def __init__(self):
        """
        app setup
        """
        # setup the parent class
        base_dir = os.path.dirname(os.path.abspath(__file__))
        base_app.__init__(self, base_dir)

        # select the base_app steps to expose
        # index() is generic
        app_expose(base_app.index)
        app_expose(base_app.input_select)
        app_expose(base_app.input_upload)
        # params() is modified from the template
        app_expose(base_app.params)
        # run() and result() must be defined here




    


    def build(self):
        """
        program build/update
        """
        # store common file path in variables
        # tgz_file = self.dl_dir + self.demo_src_filename
        # prog_names = ["dll_decomposition", "dll_sequence", "testBoundaries", \
        # 			  "testDecomposition", "testOtsu"]
        # prog_bin_files = []

        # for f in prog_names:
        #     prog_bin_files.append(self.bin_dir+ f)

        # log_file = self.base_dir + "build.log"
        # # get the latest source archive
        # print ("Starting download \n")
        # build.download(self.xlink_src, tgz_file)
        # print ("download ended... \n")
        # # test if the dest file is missing, or too old
        # if (os.path.isfile(prog_bin_files[0])
        #     and ctime(tgz_file) < ctime(prog_bin_files[0])):
        #     cherrypy.log("not rebuild needed",
        #                  context='BUILD', traceback=False)
        # else:
        #     # extract the archive
        #     build.extract(tgz_file, self.src_dir)
        #     # build the program
        #     build.run("cd %s; git clone %s" %(self.src_dir) %("https://github.com/kerautret/DGtal.git"))
        #     build.run("cd %s ; mkdir build; cmake .. -DCMAKE_BUILD_TYPE=Release; make -j 4" %(self.src_dir + "DGtal"))
            
        #     #build.run("mkdir %s;  " %(self.src_dir+"gjknd_1.1/build"), \
        #    #            						 stdout=log_file)
        #    # build.run("cd %s; cmake .. ; make -j 4" %(self.src_dir + \
        #     #							"gjknd_1.1/build"),stdout=log_file)

        #     # save into bin dir
        #     if os.path.isdir(self.bin_dir):
        #         shutil.rmtree(self.bin_dir)
        #     os.mkdir(self.bin_dir)
        #     for i in range(0, len(prog_bin_files)) :
        #         shutil.copy(self.src_dir + os.path.join("gjknd_1.1/build/src", \
        #         			prog_names[i]), prog_bin_files[i])

        #     # cleanup the source dir
        #     shutil.rmtree(self.src_dir)

        return




   



    @cherrypy.expose
    @init_app
    def wait(self, **kwargs):
        """
        params handling and run redirection
        """

        # save and validate the parameters
        try:
            self.cfg['param']['m'] = kwargs['m']
            self.cfg['param']['tmin'] = kwargs['tmin']
            self.cfg['param']['tmax'] = kwargs['tmax']
            self.cfg['param']['autothreshold'] =  kwargs['thresholdtype'] == 'True'

            self.cfg.save()
        except ValueError:
            return self.error(errcode='badparams',
                              errmsg="The parameters must be numeric.")

        http.refresh(self.base_url + 'run?key=%s' % self.key)
        return self.tmpl_out("wait.html")

    @cherrypy.expose
    @init_app
    def run(self):
        """
        algo execution
        """
        self.list_commands = ""


        try:
            self.run_algo(self)
        except TimeoutError:
            return self.error(errcode='timeout')
        except RuntimeError:
            return self.error(errcode='runtime',
                              errmsg="Something went wrong with the program.")
        except ValueError:
            return self.error(errcode='badparams',
                              errmsg="The parameters given produce no contours,\
                              		  please change them.")

        http.redir_303(self.base_url + 'result?key=%s' % self.key)

        # # archive
        # if self.cfg['meta']['original']:
        #     ar = self.make_archive()
        #     ar.add_file("input_0.png", "original.png", info="uploaded")
        #     ar.add_file("output.txt", info="output.txt")
        #     ar.add_file("commands.txt", info="commands.txt")
        #     ar.add_file(typeprimitive+"_out_input_0.png", info="output")
        #     ar.add_info({"type primitive": typeprimitive})
        #     ar.add_info({"use black background": b})

        #     ar.save()

        return self.tmpl_out("run.html")






    def run_algo(self, params):
        """
        the core algo runner
        could also be called by a batch processor
        this one needs no parameter
        """

        ##  -------
        ## process 1: transform input file
        ## ---------
        command_args = ['convert.sh', 'input_0.png', 'inputNG.pgm' ]
        self.runCommand(command_args)

        ##  -------
        ## process 2: extract contour files
        ## ---------
        f = open(self.work_dir+"inputPolygon.txt", "w")
        fInfo = open(self.work_dir+"algoLog.txt", "w")
        command_args = ['img2freeman']+\
                       ['--minSize', str(self.cfg['param']['m'])]+\
                       [ '-i', 'inputNG.pgm']
                       
        if not self.cfg['param']['autothreshold']:
            command_args += ['-M', str(self.cfg['param']['tmax'])]+ \
           					['-m', str(self.cfg['param']['tmin'])]

        cmd = self.runCommand(command_args, f, fInfo, \
                              comp = ' > inputPolygon.txt')

        if os.path.getsize(self.work_dir+"inputPolygon.txt") == 0:
            raise ValueError
        fInfo.close()
        fInfo = open(self.work_dir+"algoLog.txt", "r")

        #Recover otsu max value from output
        if self.cfg['param']['autothreshold']:
            lines = fInfo.readlines()
            line_cases = lines[0].replace(")", " ").split()
            self.cfg['param']['tmax'] = int(line_cases[17])

        singleContour = open(self.work_dir+"singleContour.fc", 'w')
        f = open(self.work_dir+"inputPolygon.txt", "r")
        line = f.read()
        singleContour.write(line+"\n")
        singleContour.close()
        
        f = open(self.work_dir+"inputPolygon.sdp", "w")
        fInfo = open(self.work_dir+"algoLog.txt", "a")
        command_args = ['freeman2sdp']+\
                       ['-f', 'singleContour.fc']
                       
        
        cmd = self.runCommand(command_args, f, fInfo, \
                              comp = ' > inputPolygon.sdp')

        f.close()



        ##  -------
        ## process 3: apply algorithm
        ## ---------
        inputWidth = image(self.work_dir + 'input_0.png').size[0]
        inputHeight = image(self.work_dir + 'input_0.png').size[1]
        command_args = ['testCircleDecomposition'] + \
                       [ '-i', 'inputPolygon.sdp', '-d', self.src_dir + os.path.join('ImaGene-forIPOL')] + \
                       ['-e']
        f = open(self.work_dir+"algoLog.txt", "a")
        cmd = self.runCommand(command_args, none, f)
       


        ## ---------
        ## process 4: converting to output result
        ## ---------
        command_args = ['convert.sh', '-background', '#FFFFFF', '-flatten', \
                        'output.eps', 'output.png']
        self.runCommand(command_args)

        ## ----
        ## Final step: save command line
        ## ----
        f = open(self.work_dir+"commands.txt", "w")
        f.write(self.list_commands)
        f.close()
        return


    @cherrypy.expose
    @init_app
    def result(self, public=None):
        """
        display the algo results
        """
        return self.tmpl_out("result.html",
                             height=image(self.work_dir
                                          + 'resu.png').size[1])


    @cherrypy.expose
    @init_app
    def result(self, public=None):
        """
        display the algo results
        """
        resultHeight = image(self.work_dir + 'input_0.png').size[1]
        imageHeightResized = min (600, resultHeight)
        resultHeight = max(300, resultHeight)
        return self.tmpl_out("result.html", height=resultHeight, \
        					 heightImageDisplay=imageHeightResized)


    def runCommand(self, command, stdOut=None, stdErr=None, comp=None):
        """
        Run command and update the attribute list_commands
        """
        p = self.run_proc(command, stderr=stdErr, stdout=stdOut, \
        				  env={'LD_LIBRARY_PATH' : self.bin_dir})
        self.wait_proc(p, timeout=self.timeout)
        index = 0
        # transform convert.sh in it classic prog command (equivalent)
        for arg in command:
            if arg == "convert.sh" :
                command[index] = "convert"
            index = index + 1
        command_to_save = ' '.join(['"' + arg + '"' if ' ' in arg else arg
                 for arg in command ])
        if comp is not None:
            command_to_save += comp
        self.list_commands +=  command_to_save + '\n'
        return command_to_save

    def make_archive(self):
        """
        create an archive bucket HACK!
        This overloaded verion of the empty_app function
        first deletes the entry and its directory so that the 
        new one is correcly stored.
        """
        # First delete the key from the archive if it exist
        from lib import archive
        archive.index_delete(self.archive_index, self.key)
        entrydir = self.archive_dir + archive.key2url(self.key)
        if os.path.isdir(entrydir):
            shutil.rmtree(entrydir)

        # Then insert the new data
        ar = archive.bucket(path=self.archive_dir,
                            cwd=self.work_dir,
                            key=self.key)
        ar.cfg['meta']['public'] = self.cfg['meta']['public']

        def hook_index():
            """
            create an archive bucket
            """
            return archive.index_add(self.archive_index,
                                     bucket=ar,
                                     path=self.archive_dir)
        ar.hook['post-save'] = hook_index
        return ar
