"""
Created on Mar 15, 2016
@author: zimmer
@brief: base class for DAMPE Workflow (HPC/client side)
"""

import os.path as oPath
from subprocess import PIPE, Popen
from select import poll as spoll, POLLIN, POLLHUP
from ast import literal_eval
from os import environ, getenv
from jsonpickle import encode as Jencode, decode as Jdecode
from json import dumps
from time import ctime
from requests import post as Rpost
from importlib import import_module
from copy import deepcopy
from DmpWorkflow.config.defaults import FINAL_STATII, DAMPE_WORKFLOW_URL, DAMPE_WORKFLOW_ROOT, BATCH_DEFAULTS, DAMPE_BUILD, cfg
from DmpWorkflow.utils.tools import mkdir, touch, rm, safe_copy, parseJobXmlToDict, getSixDigits 
from DmpWorkflow.utils.tools import ResourceMonitor, sleep, random_string_generator
from DmpWorkflow.utils.shell import make_executable  # , source_bash
from requests.exceptions import HTTPError

RunningInBatchMode = False
if DAMPE_BUILD == "client": 
    HPC = import_module("DmpWorkflow.hpc.%s" % BATCH_DEFAULTS['system'])    
    b_id = getenv(HPC.BATCH_ID_ENV)
    if b_id is not None: RunningInBatchMode = True
    
    
PYTHONBIN = ""
ExtScript = cfg.get("site", "ExternalsScript")
NUMLINES_LOG = 20

# todo2: add cfg parsing variables.
class DmpJob(object):
    def __init__(self, job_id, body=None, **kwargs):
        self.monitoring_enabled = "True" # enable monitoring
        self.wd = oPath.abspath(".")
        self.title = None
        self.jobId = str(job_id)
        self.instanceId = None
        self.batchId = None
        self.InputFiles = []
        self.OutputFiles = []
        self.MetaData = []
        self.type = None
        self.release = None
        self.logfile = None
        self.execCommand = None
        self.executable = ""
        self.exec_wrapper = ""
        self.short_job = False
        self.script = None
        self.status = None
        self.error_log = ""
        self.batchdefaults = deepcopy(BATCH_DEFAULTS)
        self.__dict__.update(kwargs)
        self.extract_xml_metadata(body)
        self.isPilot = True if self.type == "Pilot" else False
        self.pilotReference = None
        self.monitoring_enabled = True if self.monitoring_enabled in ["True","true","TRUE","YES","Yes","yes"] else False 
        #self.__updateEnv__()
    def getJSONbody(self):
        """ returns the body of the instance as JSON object, can be returned in status query """
        dummy_dict = {"InputFiles": self.InputFiles, "OutputFiles": self.OutputFiles, "MetaData": self.MetaData}
        return dumps(dummy_dict)
    def setPilotReference(self,pilotRef):
        self.pilotReference = pilotRef
    def setAsPilot(self,val):
        self.isPilot = val
    def logError(self,err):
        error_line = "%s:ERROR: %s \n"%(ctime(),str(err))
        self.error_log += str(error_line)

    def registerDS(self, filename=None, overwrite=False):
        site = cfg.get("site", "name")
        if filename is None:
            files = [fi['target'] for fi in self.OutputFiles]
        else:
            files = [filename]
        for fi in files:
            tg = oPath.expandvars(fi)
            res = Rpost("%s/datacat/" % DAMPE_WORKFLOW_URL, data={"filename": tg, "site": site,
                                                                  "action": "register",
                                                                  "overwrite": str(overwrite)})
            res.raise_for_status()
            if not res.json().get("result", "nok") == "ok":
                raise Exception(res.json().get("error", "No error provided."))

    def getWorkDir(self):
        wdROOT = cfg.get("site", "workdir") 
        wd = oPath.join(wdROOT, str(self.title), str(self.type), self.getSixDigits(asPath=True))
        return wd

    def __updateEnv__(self):
        override_keys = ["BATCH_OVERRIDE_%s" % key.upper() for key in BATCH_DEFAULTS.keys()]
        for var in self.MetaData:
            if var['name'] in override_keys:
                bkey = var['name'].replace("BATCH_OVERRIDE_", "").lower()
                BATCH_DEFAULTS[bkey] = var['value']
            else:
                #print 'setting %s = %s'%(var['name'],var['value'])
                environ[var['name']] = var['value']
        for fil in self.InputFiles + self.OutputFiles:
            for key in ['source', 'target']:
                fil[key] = oPath.expandvars(fil[key])
        
        if self.title is not None:
            environ['DWF_TASKNAME'] = self.title
        if self.release is not None:
            environ['RELEASE_TAG'] = self.release
        environ['DWF_JOB_ID']      = str(self.jobId)
        environ['DWF_INSTANCE_ID'] = str(self.instanceId)
        self.short_job = literal_eval(getenv("DWF_SHORT_JOB","False"))
        # print 'BatchOverride keys', BATCH_DEFAULTS
        self.batchdefaults = BATCH_DEFAULTS
        if self.isPilot:
            environ["DWF_PILOT_REFERENCE"] = "%s.%s"%(str(self.jobId),str(self.instanceId))
        return

    def getBatchDefaults(self):
        self.__updateEnv__()
        return self.batchdefaults

    def getJobName(self):
        return "-".join([str(self.jobId), self.getSixDigits()])

    def extract_xml_metadata(self, xmldoc):
        """ given the structured job definition, read out and set variables """
        if xmldoc is None:
            return
        el = parseJobXmlToDict(xmldoc)
        self.setBodyFromDict(el)

    def setBodyFromDict(self, el):
        self.InputFiles += el['InputFiles']
        self.OutputFiles += el['OutputFiles']
        self.MetaData += el['MetaData']
        self.exec_wrapper = el['script']
        self.executable = el['executable']
        self.__dict__.update(el['atts'])

    def setInstanceParameters(self, instance_id, JobInstance_body):
        """ extract jobInstanceParameters to fully define job """
        body = JobInstance_body
        self.instanceId = instance_id  # aka stream
        keys = ['InputFiles', 'OutputFiles', 'MetaData']
        if not isinstance(body, dict):
            body = literal_eval(body)
        if isinstance(body, dict):
            for key in keys:
                if key in body and isinstance(body[key], list):
                    if len(body[key]):
                        self.__dict__[key] += body[key]
        else:
            raise Exception("Must be a string which can be converted into dictionary")
        
    def write_script(self, pythonbin=None, debug=False):
        """ based on meta-data should create job-executable """
        if pythonbin is None:
            pythonbin = "python"
        # print pythonbin
        self.wd = self.getWorkDir()
        if oPath.isdir(self.wd):
            rm(self.wd)
        mkdir(self.wd)
        
        safe_copy(oPath.join(DAMPE_WORKFLOW_ROOT, "scripts/dampe_execute_payload.py"),
                  oPath.join(self.wd, "script.py"), debug=debug)
        with open(oPath.join(self.wd, "job.json"), "wb") as json_file:
            json_file.write(self.exportToJSON())
        script_file = open(oPath.join(self.wd, "script"), "w")
        rel_path = self.getReleasePath()
        setup_script = self.getSetupScript()
        setup_script = setup_script.replace(rel_path, "")
        if setup_script.startswith("/"):
            setup_script = setup_script.replace("/", "")        
        cmds = ["#!/bin/bash", "echo \"batch wrapper executing on $(date)\"",
                "echo \"HOSTNAME: $(hostname)\"",
                "echo \"# CORES: $(grep -c processor /proc/cpuinfo)\"",
                "DAMPE_WD=${DAMPE_WORKFLOW_WORKDIR:-%s}"%self.wd,
                "source %s" % oPath.expandvars(ExtScript),
                "unset DMPSWSYS",
                "cd %s" % rel_path if not self.isPilot else "# pilot do nothing",
                "source %s" % setup_script if not self.isPilot else "# pilot, do nothing.", 
                "cd ${DAMPE_WD}",
                "%s script.py ${DAMPE_WD}/job.json" % pythonbin,
                "echo \"batch wrapper completed at $(date)\""]
        script_file.write("\n".join(cmds))
        script_file.close()
        make_executable(oPath.join(self.wd, "script"))
        self.execCommand = "%s/script" % self.wd
        return

    def getSetupScript(self):
        rpath = self.getReleasePath()
        return oPath.expandvars("%sbin/thisdmpsw.sh" % rpath)

    def getReleasePath(self):
        return oPath.expandvars("${DAMPE_SW_DIR}/releases/DmpSoftware-%s/" % self.release)

    # def sourceSetupScript(self):
    #    src = self.getSetupScript()
    #    source_bash(src)

    def createLogFile(self):
        # mkdir(oPath.join("%s/logs" % self.wd))
        self.logfile = oPath.join(self.wd, "output.log")
        if oPath.isfile(self.logfile):
            rm(self.logfile)
        touch(self.logfile)
    
    def account(self,majorStatus):
        if majorStatus in ["Done", "Failed", "Terminated"]:
            witness = open(oPath.join(self.wd, "%s" % majorStatus.upper()), 'w')
            witness.write(self.getJobName())
            witness.close()

    def updateStatus(self, majorStatus, minorStatus, **kwargs):
        """ passes status """
        self.status = majorStatus
        if self.short_job:
            if self.status == majorStatus: return
            if 'resources' in kwargs: del kwargs['resources']
        my_dict = {"t_id": self.jobId, "inst_id": self.instanceId, "major_status": majorStatus,
                   "minor_status": minorStatus}
        if not self.isPilot and self.pilotReference not in ["None","NONE",None]:            
            my_dict['pilotReference'] = self.pilotReference
        if 'resources' in kwargs:
            if kwargs['resources']:
                RM = kwargs['resources']
                if not isinstance(RM, ResourceMonitor):
                    raise Exception("resource must be of type resource monitor")
                my_dict['memory'] = RM.getMemory(unit='Mb')
                my_dict['cpu'] = RM.getCpuTime()
                del kwargs['resources']
        my_dict.update(kwargs)
        attempts = my_dict.get("attempts",3)
        tout  = my_dict.get("timeout",30.)
        if 'attempts' in my_dict: my_dict.pop("attempts")
        if 'timeout' in my_dict: my_dict.pop("timeout")
        if majorStatus in FINAL_STATII:
            # keep only NUMLINES of log file.
            theLog = self.error_log.splitlines()
            if len(theLog) > NUMLINES_LOG:
                self.error_log = "\n".join(theLog[-(NUMLINES_LOG-1):-1])
            my_dict['log']=self.error_log
        # print '*DEBUG* my_dict: %s'%str(my_dict)
        res = None
        counter = 0
        while (attempts >= counter) and (res is None):
            try:
                res = Rpost("%s/jobstatus/" % DAMPE_WORKFLOW_URL, data={"args": dumps(my_dict)}, timeout=tout)
                res.raise_for_status()
            except HTTPError as err:
                counter+=1
                slt = 60*counter
                print '%i/%i: could not complete request, sleeping %i seconds and retrying again'%(counter, attempts, slt)
                print err
                sleep(slt)
                res = None
        if res is None and counter == attempts:
            if majorStatus == "Running":
                # this is desaster recovery (to keep running jobs running)
                print 'keeping job running, ignoring this update'
            elif majorStatus in ["Done","Failed","Terminated"]:
                print 'status change to final, triggering exit'
                bj = HPC.BatchJob(batchId=self.batchId)
                self.account(majorStatus)
                bj.kill()
        else:
            if not res.json().get("result", "nok") == "ok":
                raise Exception(res.json().get("error", "ErrorMissing"))
            self.account(majorStatus)
        return
        # update_status(self.jobId, self.instanceId, majorStatus, minor_status=minorStatus, **kwargs)

    def getStatusBatch(self):
        """ interacts with the backend HPC stuff and returns the status of the job """
        # todo: make the whole thing batch-independent!
        batch = HPC.BatchEngine()
        ret = batch.status_map[batch.getJob(self.batchId, key="STAT")]
        return ret

    def submit(self, **kwargs):
        """ handles the submission part """
        # print "batchdefaults: ",BATCH_DEFAULTS
        dry = kwargs['dry'] if 'dry' in kwargs else False
        local = kwargs['local'] if 'local' in kwargs else False
        if not dry:
            self.createLogFile()

        bj = HPC.BatchJob(name=self.getJobName(), command=self.execCommand, logFile=self.logfile,
                          defaults=BATCH_DEFAULTS)
        if dry:
            print "DRY_COMMAND: %s" % self.execCommand
            return -1
        if local:
            if RunningInBatchMode: 
                self.batchId = bj.getBatchIdFromString(getenv(HPC.BATCH_ID_ENV,""))
            rc = self.__run_locally()
            if rc:
                raise Exception("payload failed with RC %i",rc)
        else:
            self.batchId = bj.submit(**kwargs)
        return self.batchId
    
    def __run_locally(self):    
        tsk = Popen(self.execCommand.split(),stdout=PIPE,stderr=PIPE)
        poll = spoll()
        poll.register(tsk.stdout,POLLIN | POLLHUP)
        poll.register(tsk.stderr,POLLIN | POLLHUP)
        pollc = 2
        events = poll.poll()
        while pollc > 0 and len(events) > 0:
            for event in events:
                (rfd,event) = event
                if event & POLLIN:
                    if rfd == tsk.stdout.fileno():
                        line = tsk.stdout.readline()
                        if len(line) > 0: print "INFO: {msg}".format(msg=line[:-1])
                    if rfd == tsk.stderr.fileno():
                        line = tsk.stderr.readline()
                        if len(line) > 0: print "ERROR: {msg}".format(msg=line[:-1])
            if event & POLLHUP:
                poll.unregister(rfd)
                pollc = pollc - 1
            if pollc > 0: events = poll.poll()
        rc = tsk.wait()
        return rc
        
    def kill(self, msg="ReceivedKillCommand", dry=False):
        """ handles the submission part """
        # print BATCH_DEFAULTS
        if not dry:
            self.createLogFile()
        bj = HPC.BatchJob(batchId=self.batchId)
        if dry:
            print "DRY_COMMAND: bkill %s" % self.batchId
            return -1
        else:
            bj.kill()
            self.updateStatus("Terminated", msg)

    def exportToJSON(self):
        """ return a pickler of itself as JSON format """
        return Jencode(self)

    def getSixDigits(self, asPath=False):
        return getSixDigits(self.instanceId, asPath=asPath)

    @classmethod
    def fromJSON(cls, jsonstr):
        kc = Jdecode(jsonstr)
        kc.__updateEnv__()
        return kc
