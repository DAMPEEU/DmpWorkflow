'''
Created on Jan 30, 2018

@author: zimmer
@brief: SLURM submission @ PizDaint https://www.cscs.ch/computers/piz-daint/
'''
from warnings import warn, simplefilter

simplefilter('always', DeprecationWarning)
from re import findall
from DmpWorkflow.config.defaults import BATCH_DEFAULTS as defaults
from DmpWorkflow.config.defaults import DAMPE_WORKFLOW_URL
from DmpWorkflow.hpc.batch import BATCH, BatchJob as HPCBatchJob
from DmpWorkflow.utils.shell import run
from collections import OrderedDict
from copy import deepcopy
from os.path import dirname, curdir, join as op_join
from os import chdir

BATCH_ID_ENV = "SLURM_JOB_ID"

class BatchJob(HPCBatchJob):
    def submit(self, **kwargs):
        """ each class MUST implement its own submission command """
        pwd = curdir
        wd = dirname(self.logFile)
        chdir(wd)
        d = OrderedDict()
        self.logging.warn("!FIXME! ugly hard coded values for memory & cpu time")
        nCPU = int(defaults.get("numcores","8"))
        d['job-name'] = self.name
        d['nodes'] = 1
        d['time']  = "24:00:00"  #defaults.get("cputime","24:00:00")
        d['partition'] = defaults.get('queue',"normal")
        d['constraint'] = defaults.get('constraint','mc') # no use of gpu
        d['mem'] = "60GB"        #defaults.get("memory","4G")
        d['output'] = op_join(wd,"output.log")
        d['error'] = op_join(wd,"output.err")
        #d['ntasks-per-node']=nCPU
        d['image'] = defaults.get("image","zimmerst85/dampesw-cscs:latest")
        job_file = open("submit.sh", "w")
        job_file.write("#!/bin/bash\n")
        data = ["#SBATCH --%s=%s\n" % (k, v) for k, v in d.iteritems()]
        job_file.write("".join(data))
        # now add CSCS specific stuff
        job_file.write("module load daint-gpu\n")
        job_file.write("module load shifter-ng\n")
        job_file.write("export DAMPE_WORKFLOW_SERVER_URL=%s\n"%DAMPE_WORKFLOW_URL)
        job_file.write("export NTHREADS=%i\n"%nCPU)
        ### shifter_call = '\nsrun -C gpu shifter --image={image} --volume={wd}:/workdir bash -c "bash /workdir/script"\n'.format(image=d['image'],wd=wd)
        shifter_call = '\nsrun -C {constraint} shifter run --volume={wd}:/workdir {image} bash -c "bash /workdir/script"\n'.format(image=d['image'],wd=wd,constraint=d['constraint'])
        job_file.write(shifter_call)
        job_file.close()
        output = self.__run__("sbatch submit.sh")
        chdir(pwd)
        return self.__regexId__(output)

    def __regexId__(self, _str):
        """
         this is the sample output:
         Submitted batch job 15273
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
    kind = "slurm-cscs"
    name = "cscs"
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
