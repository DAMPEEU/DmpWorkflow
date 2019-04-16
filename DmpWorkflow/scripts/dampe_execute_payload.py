"""
Created on Apr 19, 2016

@author: zimmer
@brief: payload script with integrated process handling
"""
from os.path import expandvars, abspath, dirname, join as oPjoin
from os import curdir, environ, listdir, chdir, getenv
from importlib import import_module
from socket import gethostname
from sys import exit as sys_exit, argv
from DmpWorkflow.config.defaults import EXEC_DIR_ROOT, BATCH_DEFAULTS, cfg
from DmpWorkflow.core.DmpJob import DmpJob, RunningInBatchMode
from DmpWorkflow.utils.tools import safe_copy, camelize, mkdir, rm, ProcessResourceMonitor, convertHHMMtoSec
from DmpWorkflow.utils.shell import run_cached
from multiprocessing import Process
from psutil import Process as ps_proc
from datetime import datetime
from re import findall
from time import ctime, sleep
from ast import literal_eval
#import atexit
if not RunningInBatchMode: EXEC_DIR_ROOT = "/tmp"
HPC = import_module("DmpWorkflow.hpc.%s" % BATCH_DEFAULTS['system'])

class PayloadExecutor(object):
    def __init__(self,inputfile,debug=False):
        self.pwd = curdir
        self.logThis("reading json input")
        self.job = DmpJob.fromJSON(open(inputfile,"r").read())
        if self.job.isPilot:
            self.logThis("PILOT MODE: waiting for new jobs to be run inside queue")
        self.debug = debug
        self.batchId = getenv(HPC.BATCH_ID_ENV, "-1")
        if "." in self.batchId:
            res = findall("\d+", self.batchId)
            if len(res):
                self.batchId = int(res[0])
        self.logThis('batchId : %s' % str(self.batchId))

    def logThis(self,msg, *args):
        val = msg % args
        print "%s: %s: %s" % (ctime(), gethostname(), val)
    
    def exit_app(self,rc,msg=None):
        print '*** RECEIVED EXIT TRIGGER ****'
        if msg is not None: print msg
        sys_exit(rc)

    #@atexit.register
    #def terminate(self):
    #    self.job.updateStatus("Terminated", "Receive SIGTERM")
    #    self.exit_app(128)
    
    def __prepare(self):
        try:
            self.job.updateStatus("Running", "PreparingInputData", hostname=gethostname(), batchId=self.batchId)
        except Exception as err:
            self.logThis("EXCEPTION: %s", err)
        # first, set all variables
        self.logThis("current environment settings")
        for key, value in sorted(environ.iteritems()):
            print "%s = %s"%(key,value)
        self.logThis("end of environment dump")
        # log.info("\n".join(["%s: %s"%(key,value) for key, value in sorted(environ.iteritems())]))
        for fi in self.job.InputFiles:
            src = expandvars(fi['source'])
            tg = expandvars(fi['target'])
            self.logThis("Staging %s --> %s",src,oPjoin(abspath(self.pwd),tg))
            try:
                safe_copy(src, tg, attempts=4, sleep='4s', checksum=True)
            except IOError, e:
                try:
                    self.job.updateStatus("Running" if self.debug else "Failed", camelize(e))
                except Exception as err:
                    self.logThis("EXCEPTION: %s", err)
                    self.job.logError(err)
                if not self.debug: return 4
        self.logThis("content of current working directory %s: %s", abspath(curdir), str(listdir(curdir)))
        self.logThis("successfully completed staging.")
        return 0
    
    def __runPayload(self):
        with open('payload', 'w') as foop:
            foop.write(self.job.exec_wrapper)
            foop.close()
        self.logThis("about to run payload")
        CMD = "%s payload" % self.job.executable
        self.logThis("CMD: %s", CMD)
        try:
            self.job.updateStatus("Running", "ExecutingApplication")
        except Exception as err:
            self.logThis("EXCEPTION: %s", err)
            self.job.logError(err)
        output, error, rc = run_cached(CMD.split(), cachedir=abspath(curdir))  # use caching to file!
        self.logThis('reading output from payload %s',output.name)
        print output.read()
        output.close()
        if rc:
            self.logThis("ERROR: Payload returned exit code %i, see below for more details.", rc)
            self.logThis("content of current working directory %s: %s", abspath(curdir), str(listdir(curdir)))
            self.logThis('reading error from payload %s',error.name)
            print error.read()
            error.seek(0)
            self.job.logError(error.read())
            error.close()
            try:
                self.job.updateStatus("Running" if self.debug else "Failed", "ApplicationExitCode%i" % rc)
            except Exception as err:
                self.logThis("EXCEPTION: %s", err)
            if not self.debug: return 5
        else:   
            self.logThis("successfully completed running application")
            self.logThis("content of current working directory %s: %s", abspath(curdir), str(listdir(curdir)))
            return 0

    def __postRun(self):
        try:
            self.job.updateStatus("Running", "PreparingOutputData")
        except Exception as err:
            self.logThis("error when updating job status to: PreparingOutputData")		# Log it but don't let it interrupt the run
            self.logThis("EXCEPTION: %s", err)
            sleep(300)		# Sleep for 5mn then try again
            try:
                self.job.updateStatus("Running", "PreparingOutputData")	
            except Exception as err:
                self.logThis("EXCEPTION: %s", err)
			
        for fi in self.job.OutputFiles:
            src = expandvars(fi['source'])
            tg = expandvars(fi['target'])
            self.logThis("Staging %s --> %s",oPjoin(abspath(self.pwd),src),tg)
            _dir = dirname(tg)
            try:
                self.logThis("creating output directory %s", _dir)
                try:
                    mkdir(_dir)
                except IOError as err:
                    self.logThis("error creating output directory, trying to recover, error follows: ",err)
                safe_copy(src, tg, attempts=4, sleep='4s', checksum=True)
                #self.job.registerDS(filename=tg, overwrite=True)
            except Exception, e:
                try:
                    self.job.updateStatus("Running" if self.debug else "Failed", camelize(e))
                except Exception as err:
                    self.job.logError(err)
                    self.logThis("EXCEPTION: %s", err)
                if not self.debug: return 6
                ## add registerDS
        self.logThis("successfully completed staging.")
        return 0
    
    def execute(self):
        environ["DWF_SIXDIGIT"] = self.job.getSixDigits()
        print 'EXEC_DIR_ROOT: %s' % EXEC_DIR_ROOT
        print 'instanceId : %s' % str(self.job.getSixDigits())
        my_exec_dir = oPjoin(EXEC_DIR_ROOT, self.job.getSixDigits(), "local" if not RunningInBatchMode else str(self.batchId))
        mkdir(my_exec_dir)
        chdir(my_exec_dir)
        self.logThis("execution directory %s", my_exec_dir)
        # DMPSWSYS = getenv("DMPSWSYS")
        # DAMPE_SW_DIR = getenv("DAMPE_SW_DIR",None)
        # if DAMPE_SW_DIR is None:
        #    raise Exception("must define $DAMPE_SW_DIR")
        # next, run the executable
        # if not DAMPE_SW_DIR in DMPSWSYS:
        #    log.info("trying to re-source setup script.")
        #    job.sourceSetupScript()
        rc = 0
        rc += self.__prepare()
        if rc: self.exit_app(rc,msg="Exiting after prepare step")
        rc += self.__runPayload()
        if rc: self.exit_app(rc,msg="Exiting after payload")
        rc += self.__postRun()
        if rc: self.exit_app(rc,msg="Exiting after post-run")
        # finally, compile output file.
        self.logThis("job complete, cleaning up working directory")
        chdir(self.pwd)
        rm(my_exec_dir)
        try:
            self.job.updateStatus("Done", "ApplicationComplete")
        except Exception as err:
            self.logThis("EXCEPTION: %s", err)


if __name__ == '__main__':
    killJob = False
    reason = None
    executor = PayloadExecutor(argv[1]) # will create an executor object
    defaults = executor.job.getBatchDefaults() # will return the default values
    max_cpu = float(convertHHMMtoSec(defaults['cputime']))
    # max_mem is typically in MB!
    for unit in ['mb','Mb','MB','Mbytes']:
        if unit in defaults['memory']:
            defaults['memory']=float(defaults['memory'].replace(unit,""))
    max_mem = float(defaults['memory'])
    if max_mem >= 1e6:
        # must be in kB!
        max_mem/=1024 
    nthreads=int(getenv("NTHREADS",1))
    if nthreads > 1:
        executor.logThis("Watchdog: detected %i threads to be requested, adjusting limits accordingly",nthreads)
        max_mem*=float(nthreads)
        max_cpu*=float(nthreads)    
    # get the max ratios
    try:
        executor.job.updateStatus("Running", "PreparingJob", hostname=gethostname(), body=executor.job.getJSONbody(),
                                  batchId=executor.batchId, cpu_max=max_cpu, mem_max=max_mem)
    except Exception as err:
        executor.logThis("EXCEPTION: %s", err)

    
    executor.logThis('Watchdog: maximum cpu: %s -- maximum memory: %s',str(max_cpu),str(max_mem))
    ratio_cpu_max = float(cfg.get("watchdog", "ratio_cpu"))
    ratio_mem_max = float(cfg.get("watchdog", "ratio_mem"))
    now = datetime.utcnow()
    proc = Process(target=executor.execute)
    proc.start()
    ps = ps_proc(proc.pid)
    prm = ProcessResourceMonitor(ps) #this monitor uses psutil for its information.
    while proc.is_alive():
        syst_cpu = prm.getCpuTime()
        memory = prm.getMemory()
        ## check time out conditions
        executor.logThis('Watchdog: current cpu: %s -- current memory: %s', str(syst_cpu),str(memory))
        if (syst_cpu / max_cpu >= ratio_cpu_max):
            killJob = True
            reason = "exceeding CPU time"
        if (memory/max_mem >= ratio_mem_max):
            killJob = True
            reason = "exceeding Memory"
        if killJob:
            executor.logThis("ProcessResources: %s"%str(prm))
            executor.job.updateStatus("Terminated",camelize(reason),resources=prm)
            executor.logThis('Watchdog: current cpu: %s -- current memory: %s', str(syst_cpu),str(memory))
            executor.logThis('Watchdog: CRITICAL: got termination directive, reason follows: %s',reason)
            proc.terminate()
            sleep(100.)                                                                                                                                
            sys_exit(128) # end with exitcode                                   
        else:
            ## terminate here for the various reasons.
            # output of memory is in kilobytes.
            if executor.job.monitoring_enabled:
                executor.logThis("ProcessResources: %s"%str(prm))
                try:
                    executor.job.updateStatus("Running",None,resources=prm)
                except Exception as err:
                    executor.logThis("EXCEPTION: %s", err)
            sleep(float(BATCH_DEFAULTS.get("sleeptime","300."))) # sleep for 5m
