'''
Created on Feb 9, 2017

@author: zimmer
@brief: core SLURM functionality (job submission & cancellation), optimized for Baobab @ UniGE
'''
from warnings import warn, simplefilter

simplefilter('always', DeprecationWarning)
from re import findall
from DmpWorkflow.config.defaults import DAMPE_WORKFLOW_URL, BATCH_DEFAULTS as defaults
from DmpWorkflow.hpc.batch import BATCH, BatchJob as HPCBatchJob
from DmpWorkflow.utils.shell import run
from collections import OrderedDict
from copy import deepcopy
from os.path import dirname, curdir, join as op_join
from os import chdir

# raise ImportError("CondorHT class not supported")
BATCH_ID_ENV = "SLURM_JOB_ID"


class BatchJob(HPCBatchJob):
    def submit(self, **kwargs):
        """ each class MUST implement its own submission command """
        pwd = curdir
        wd = dirname(self.logFile)
        chdir(wd)
        d = OrderedDict()
        #d['universe'] = 'vanilla'
        #d['executable'] = self.command
	d['job-name'] = self.name
	d['nodes'] = 1
	d['partition'] = defaults.get('queue')
	d['time'] = defaults.get("cputime")
	d['mem'] = defaults.get("memory")
        d['output'] = op_join(wd,"output.log")
        d['error'] = op_join(wd,"output.err")
        csi_file = open("submit.sh", "w")
	csi_file.write("#!/bin/bash\n")
        data = ["#SBATCH --%s=%s\n" % (k, v) for k, v in d.iteritems()]
        csi_file.write("".join(data))
	csi_file.write("export DAMPE_WORKFLOW_SERVER_URL=%s\n"%DAMPE_WORKFLOW_URL)
        csi_file.write("bash script\n")
        csi_file.close()
        output = self.__run__("sbatch submit.sh")
        chdir(pwd)
        return self.__regexId__(output)

    def __regexId__(self, _str):
        """
         this is the sample output:
         1 job(s) submitted to cluster 172831.
        """
        bk = -1
        res = findall(r"\d+", _str)
        if len(res):
            bk = int(res[-1])
        return bk

    def kill(self):
        cmd = "scancel %s" % (self.batchId)
        self.__run__(cmd)
        self.update("status", "Failed")


class BatchEngine(BATCH):
    kind = "slurm"
    name = defaults['extra']
    status_map = {"CA":"Cancelled","CD":"Completed",
                  "CF":"Configuring","CG":"Completing",
                  "F":"Failed","NF":"Failed",
                  "PD":"Pending", "PR":"Failed",
                  "R":"Running","S":"Pending",
                  "TO":"Failed"}

    def update(self):
        self.allJobs.update(self.aggregateStatii())

    def getCPUtime(self, jobId, key="cputime"):
        if not jobId in self.allJobs: return 0
        return self.allJobs[jobId].get("cputime","0:00")

    #def getMemory(self, jobId, key="MEM", unit='kB'):
    #    warn("not implemented", DeprecationWarning)
    #    jobId = 0.
   #     return jobId

    def getRunningJobs(self, pending=False):
        self.update()
        running = [j for j in self.allJobs if self.allJobs[j]['st'] == "R"]
        pending = [j for j in self.allJobs if self.allJobs[j]['st'] == "PD"]
        return running + pending if pending else running

    def aggregateStatii(self, command=None):
        checkUser = self.getUser()
        if command is None:
            command = '/bin/env squeue -u {username} "PD,R"'.format(username=checkUser)
        uL = iL = False
        output, error, rc = run(command.split(), useLogging=uL, interleaved=iL, suppressLevel=True)
        self.logging.debug("rc: %i", int(rc))
        if rc:
            raise Exception("error during execution: RC=%i" % int(rc))
        if error is not None:
            for e in error.split("\n"):
                self.logging.error(e)
        try:
            jobs = output.split("\n")[1:-1]
            keys = ['id', 'partition', 'name', 'user', 'st', 'cputime', 'nodes', 'reason']
            for job in jobs:
                thisDict = dict(zip(keys, job.split()))
                if "id" in thisDict:
                    self.allJobs[int(float(thisDict['id']))] = deepcopy(thisDict)
                thisDict = {}
        except Exception as error:
            print "error has occured:"
            print error
        return self.allJobs
