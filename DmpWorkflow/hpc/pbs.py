"""
Created on Mar 23, 2016

@author: zimmer
"""
from re import findall
from DmpWorkflow.hpc.batch import BATCH, BatchJob as HPCBatchJob
from DmpWorkflow.utils.shell import run
from subprocess import PIPE, Popen
from importlib import import_module

xml2dict = import_module("xmltodict")
# LSF-specific stuff

# raise ImportError("SGE class not supported")
BATCH_ID_ENV = "PBS_JOBID"


class BatchJob(HPCBatchJob):
    def submit(self, **kwargs):
        """ each class MUST implement its own submission command """
        extra = "%s" % self.extra if isinstance(self.extra, str) else ""
        if self.queue is not None:
            extra += "-q %s" % self.queue
        mem = " -l ".join(["%s=%s" % (k, v) for k, v in {key: int(float(self.memory))
                                                         for key in ['mem', 'vmem', 'pvmem', 'pmem']}.iteritems()])
        cmd = "qsub -m n -r n -o %s -j oe -V -l cput=%s -l %s %s %s" % (self.logFile,
                                                                        self.cputime,
                                                                        mem,
                                                                        extra,
                                                                        self.command)
        # UGLY, needs to be checked against my "run" method.
        tsk = Popen(cmd.split(),stdout=PIPE, stderr=PIPE)
        rc = tsk.wait()
        output = tsk.stdout.read()
        error  = tsk.stderr.read()
        if rc:
            raise Exception("error during submission, RC=%i, error msg follows \n %s"%(rc,error))
        #output = self.__run__(cmd)
        return self.__regexId__(output)

    def __regexId__(self, _str):
        """ returns the batch Id using some regular expression, sge specific """
        # default: 
        bk = -1
        res = findall(r"\d+", _str)
        if len(res):
            bk = int(res[0])
        return bk

    def kill(self):
        """ likewise, it should implement its own batch-specific removal command """
        cmd = "qdel %s" % self.batchId
        self.__run__(cmd)
        self.update("status", "Failed")


class BatchEngine(BATCH):
    kind = "pbs"
    status_map = {"r": "Running", "qw": "Submitted", "s": "Suspended",
                  "c": "Suspended", "t": "Terminated", "e": "Failed"}

    def update(self):
        self.allJobs.update(self.aggregateStatii())

    def getCPUtime(self, jobId, key="CPU_USED"):
        """ format is: 000:00:00.00 """
        if jobId not in self.allJobs:
            return 0.
        cpu_str = self.allJobs[jobId][key]
        hr, _min, secs = cpu_str.split(":")
        totalSecs = float(secs) + 60 * float(_min) + 3600 * float(hr)
        return totalSecs

    def getMemory(self, jobId, key="MEM", unit='kB'):
        """ format is kb, i believe."""
        if jobId not in self.allJobs:
            return 0.
        mem_str = self.allJobs[jobId][key]
        mem = float(mem_str)
        if unit in ['MB', 'GB']:
            mem /= 1024.
            if unit == 'GB':
                mem /= 1024.
        return mem

    def getRunningJobs(self, pending=False):
        self.update()
        running = [j for j in self.allJobs if self.allJobs[j]['STAT'] == "r"]
        pending = [j for j in self.allJobs if self.allJobs[j]['STAT'] == "qw"]
        return running + pending if pending else running

    def __parseOutputAsXml__(self, xmloutput, filterUser):
        """ returns job dictionary """
        jobs = {}
        output = xml2dict.parse(xmloutput)
        data = output.get("Data", "None")
        if "None":
            self.logging.error("could not get data content from qstat, check SGE")
        sge_jobs = data.get("Job", "None")
        if sge_jobs == "None":
            sge_jobs = []
        if len(sge_jobs):
            for j in sge_jobs:
                usr = j.get("Job_Owner", "None")
                if "@" in usr:
                    usr = usr.rsplit("@")[0]
                if filterUser is not None:
                    if not usr == filterUser: continue
                stat = j.get("job_state", "U").lower()  # unknown
                if stat.lower() not in self.status_map.keys():
                    stat = 'u'
                cpu = None
                mem = None
                res = j.get("resources_used", "None")
                if res != "None":
                    mem = float(res.get("mem", "0kb").rsplit("kb")[0])
                    cpu = res.get("cput", "00:00:00.000")
                this_job = {"USER": usr, "MEM": mem, "CPU_USED": cpu, "JOB_NAME": "None-None",
                            "STAT": stat, "EXEC_HOST": j.get("exec_host")}
                jobs[j.get("Job_Id", "None").split(".")[0]] = this_job
        return jobs

    def aggregateStatii(self, asDict=True, command=None):
        checkUser = self.getUser()
        if command is None:
            command = "qstat"
        uL = iL = True
        if asDict:
            uL = iL = False
            command += " -x -e"
        output, error, rc = run(command.split(), useLogging=uL, interleaved=iL, suppressLevel=True)
        self.logging.debug("rc: %i", int(rc))
        if rc:
            raise Exception("error during execution")
        if error is not None:
            for e in error.split("\n"):
                self.logging.error(e)
        if not asDict:
            return output
        else:
            return self.__parseOutputAsXml__(output, checkUser)
