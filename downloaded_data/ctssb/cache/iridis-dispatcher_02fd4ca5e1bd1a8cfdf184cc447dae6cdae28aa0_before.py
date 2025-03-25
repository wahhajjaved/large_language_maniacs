import sys
import string
import textwrap
import math
import numpy
import time
import random

def write_preamble(file,nodes,ppn,walltime):
   file.write(textwrap.dedent("""\
   #!/bin/bash
   #PBS -S /bin/bash
   # Script to run some jobs in parallel.

   # set default resource requirements for job (8 processors on 1 node for 1
   # minute). These can be overridden on the qsub command line.
   """))
   
   file.write("#PBS -l nodes="+repr(nodes)+":ppn="+repr(ppn)+"\n")
   file.write("#PBS -l walltime="+repr(walltime)+":00:00\n")

   file.write(textwrap.dedent("""\
   # Change to directory from which job was submitted.
   cd $PBS_O_WORKDIR

   """))


def getoptions(args):
   
   found = ""
   dict = {}
   for arg in args:
      if found != "":
         if arg[0] == "-":
            arg = arg.lstrip("-")
            if len(arg) > 0:
               dict[found] = ""
               found = arg
         else:
            dict[found] = arg
            found = ""
      else:
         if arg[0] == "-":
            arg = arg.lstrip("-")
            if len(arg) > 0:
               found = arg
   if found != "":
      dict[found] = ""
   
   print (dict,'\n')
   return dict

def uecadap(file, args):

   print("Creating job file for uec adaptive job.\n\nFound arguments:")
   
   #look for options like -startsnr, -stopsnr etc
   opt_dict = getoptions(args)
   
   die=0
   
   if ('snrs' not in opt_dict.keys()):   
      if ('startsnr' not in opt_dict.keys()):
         die=1
         print("Requires option -startsnr")     
      if ('stopsnr' not in opt_dict.keys()):
         die=1
         print("Requires option -stopsnr")      
      if ('stepsnr' not in opt_dict.keys()):
         die=1
         print("Requires option -stepsnr")
         
      startsnr = float(opt_dict['startsnr'])
      stopsnr = float(opt_dict['stopsnr'])
      stepsnr = float(opt_dict['stepsnr'])
      snrs = numpy.arange(startsnr, stopsnr+0.0002, stepsnr)
      
   else:
      snrs_s = opt_dict['snrs']
      snrs_s=snrs_s.split(",")
      snrs = [float(s) for s in snrs_s]
         
   print("List of SNRs:")
   print (snrs)
   print ("\n\n")
   
   if ('copies' not in opt_dict.keys()):
      copies = 1;
      print("Defaulting -copies to 1")
   else:
      copies = int(opt_dict['copies'])
      
   if ('wall' not in opt_dict.keys()):
      wall = 36;
      print("Defaulting -wall to 36")
   else:
      wall = opt_dict['wall'] 
      
   if ('n' not in opt_dict.keys()):
      name = time.strftime("%y%m%d-%H%M%S");
      print("Defaulting -n (name) to "+name)
   else:
      name = opt_dict['n'] 

   if ('bits' not in opt_dict.keys()):
      bits = 1000;
      print("Defaulting -bits to 1000")
   else:
      bits = float(opt_dict['bits'])  

   if ('type' not in opt_dict.keys()):
      type = "m2ms";
      print("Defaulting -type to m2ms")
   else:
      type = opt_dict['type']        
      
   if ('src' not in opt_dict.keys()):
      die=1
      print("Requires option -src")
      
   if ('res' not in opt_dict.keys()):
      die=1
      print("Requires option -res")
      
      
   if die>0:
      print("Quiting...")
      return
      

      
   #total nodes
   nodes = len(snrs)
   if nodes < 1 or copies < 1:
      print("Invalid combination of snr start/stop/step / copies")
      print("Quiting...")
      return
   
   nodes = nodes * copies
   
   mach = math.ceil(nodes/16)
   ppn = math.ceil(nodes/mach)
   
   #open file for writing
   f = open(file,'w')
   write_preamble(f,mach,ppn,wall)
   f.write("$SRC=\""+opt_dict['src']+"\"\n")
   f.write("$RES=\""+opt_dict['res']+"/"+name+"\"\n")
   f.write("mkdir $RES\n\n\n\n")
   
   uec_scaling = "-1"
   if type == "non":
      adap = "0"
   else:
      adap = "1"
      if type == "m1ms":
         uec_scaling = "-1"
      elif type == "m2ms":
         uec_scaling = "-2"
      else:
         print("Invalid -type option. Choose either non,m1ms,m2ms")
   
   for c in range(0, copies):
      for snr in snrs:
         f.write("matlab -nodisplay -nojvm -r \"cd $SRC; adaptive_uec_urc_d_ber( 'results_filename', '$RES/files"+type+"', 'int_len', '"+repr(bits)+"', 'max_type', 'max_star', 'start_snr', '"+repr(snr)+"', 'stop_snr', '"+repr(snr)+"', 'step_snr', '1', 'number_type', 'do', 'seed', '"+repr(random.randint(0,100000))+"', 'uec_exit_scaling', '"+uec_scaling+"', 'adaptive', '"+adap+"', 'channel', 'r')\"&\n")
      f.write("\n")
      
   f.write("\nwait\n")
   
   f.close()  
   
def uecadapref():

   print("creating job file for uec adaptive job reference code")


#main entry point
 
#test sys.argv[1] to see what type of job

try:

   options = { "uec-adaptive" : uecadap,
               "uec-adaptive-ref" : uecadapref,
             }
             
   options[sys.argv[2]](sys.argv[1],sys.argv[3:])

except:
   print("Usage: \n\n")
   print("\tcreate-job.py job_out run_type <specific options>\n\n")
   print("\trun_type options: \n\t\tuec-adaptive\tuec-adaptive-ref\n")
