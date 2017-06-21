'''
Created on Aug 10, 2016

@author: zimmer
@brief: core SLURM functionality (job submission & cancellation)
'''
from warnings import warn, simplefilter
simplefilter('always', DeprecationWarning)
from re import findall
from DmpWorkflow.config.defaults import BATCH_DEFAULTS as defaults 
from DmpWorkflow.hpc.batch import BATCH, BatchJob as HPCBatchJob
from DmpWorkflow.utils.shell import run
from copy import deepcopy
from os.path import dirname, curdir
from os import chdir
#raise ImportError("CondorHT class not supported")
BATCH_ID_ENV = "SLURM_JOB_ID"

class BatchJob(HPCBatchJob):
    error = None
    
    def submit(self, **kwargs):
        """ each class MUST implement its own submission command """
        pwd = curdir
        wd = dirname(self.logFile)
        chdir(wd)
        self.error = self.logFile.replace("log","err")
        cmd = "sbatch --error={error} --output={logFile} --mem={memory} --time={cputime} --job-name={name} {command}".format(**self.__dict__)        
        output = self.__run__(cmd)
        chdir(pwd)
        return self.__regexId__(output)
    
    def __regexId__(self,_str):
        """
         this is the sample output:
         Submitted batch job 106 
        """
        bk = -1
        res = findall(r"\d+", _str)
        if len(res):
            bk = int(res[-1])
        return bk
    
    def kill(self):
        cmd = "scancel %s"%(self.batchId)
        self.__run__(cmd)
        self.update("status", "Failed")

class BatchEngine(BATCH):
    kind = "slurm"
    name = defaults['extra']
    status_map = {"R": "Running", "PD": "Pending"}

    def update(self):
        self.allJobs.update(self.aggregateStatii())

    def getCPUtime(self, jobId, key="CPU_USED"):
        """ format is: 000:00:00.00 """
        warn("not implemented", DeprecationWarning)
        jobId = 0.
        return jobId

    def getMemory(self, jobId, key="MEM", unit='kB'):
        """ format is kb, i believe."""
        warn("not implemented", DeprecationWarning)
        jobId = 0.
        return jobId

    def getRunningJobs(self, pending=False):
        self.update()
        running = [j for j in self.allJobs if self.allJobs[j]['statecompact'] == "R"]
        pending = [j for j in self.allJobs if self.allJobs[j]['statecompact'] == "PD"]
        return running + pending if pending else running

    def aggregateStatii(self, command=None):
        if command is None:
            command = "squeue --Format=jobid,username,account,statecompact,starttime,timelimit,numcpus"
        uL = iL = False
        output, error, rc = run(command.split(), useLogging=uL, interleaved=iL, suppressLevel=True)
        self.logging.debug("rc: %i", int(rc))
        if rc:
            raise Exception("error during execution: RC=%i"%int(rc))
        if error is not None:
            for e in error.split("\n"):
                self.logging.error(e)
        try:
            jobs = output.split("\n")[4:-1]
            keys = ['jobid', 'username', 'account','statecompact','starttime', 'timelimit','numcpus']
            for job in jobs:
                thisDict = dict(zip(keys,job.split()))
                if "jobid" in thisDict:
                    self.allJobs[int(float(thisDict['id']))]=deepcopy(thisDict)
                thisDict = {}
        except Exception as error:
            print "error has occured:"
            print error
        return self.allJobs
