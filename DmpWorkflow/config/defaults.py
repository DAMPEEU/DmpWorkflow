"""
Created on Apr 20, 2016

@author: zimmer
@brief: prototype script that handles config parsing etc.

"""
from ConfigParser import SafeConfigParser
from os import environ, getenv
from random import choice
from os.path import dirname, abspath, join as oPjoin
#import sys
from DmpWorkflow import version as DAMPE_VERSION
#from DmpWorkflow.utils.tools import exceptionHandler

DAMPE_WORKFLOW_ROOT = dirname(dirname(abspath(__file__)))

__myDefaults = {
    "DAMPE_SW_DIR": ".",
    "installation": "server",
    "setup": "Production",
    "ExternalsScript": "${DAMPE_SW_DIR}/setup/setup.sh",
    "use_debugger": "true",
    "use_reloader": "true",
    "use_profiler": "false",
    "workdir": ".",
    "url": "",
    "traceback": "true",
    "task_types": "Generation,Digitization,Reconstruction,User,Other".split(","),
    "task_major_statii": "New,Running,Failed,Terminated,Done,Submitted,Suspended".split(","),
    "HPCsystem": "lsf",
    "HPCrequirements": "",
    "HPCextra": "",
    "HPCqueue": "",
    "HPCname": "default",
    "HPCcputime": "24:00",
    "HPCmemory": "1000.",
    "HPCusername": "dampeprod",
    "HPCclustername" : "None",
    "EXEC_DIR_ROOT": "/tmp",
    "ratio_mem": "1.0",
    "ratio_cpu": "1.0",
    "logfile": "/tmp/flask.log",
    "loglevel": "INFO"
}

cfg = SafeConfigParser(defaults=__myDefaults)

cfg.read(oPjoin(DAMPE_WORKFLOW_ROOT, "config/settings.cfg"))

assert cfg.get("global", "installation") in ['server', 'client'], "installation must be server or client!"
DAMPE_BUILD =  cfg.get("global","installation")
environ["DAMPE_BUILD"] = DAMPE_BUILD
environ["DAMPE_SW_DIR"] = cfg.get("site", "DAMPE_SW_DIR")
environ["DAMPE_WORKFLOW_ROOT"] = DAMPE_WORKFLOW_ROOT

# environ["DAMPE_URL"] = cfg.get("server","url")
# print "setting up externals"
# source_bash(cfg.get("site", "ExternalsScript"))

dbg = cfg.getboolean("global", "traceback")
#sys.excepthook = exceptionHandler

DAMPE_WORKFLOW_URL = getenv("DAMPE_WORKFLOW_SERVER_URL",cfg.get("server", "url"))

# for clients: support multiple servers.
if DAMPE_BUILD == "client" and "," in DAMPE_WORKFLOW_URL:
    DAMPE_WORKFLOW_URL = choice(DAMPE_WORKFLOW_URL.split(",")) 
    # some cleanup in syntax to get rid of extra whitespaces.
    while " " in DAMPE_WORKFLOW_URL:
        DAMPE_WORKFLOW_URL = DAMPE_WORKFLOW_URL.replace(" ","")

DAMPE_WORKFLOW_DIR = cfg.get("site", "workdir")
EXEC_DIR_ROOT = cfg.get("site", "EXEC_DIR_ROOT")
environ["DWF_SW_VERSION"] = DAMPE_VERSION
if DAMPE_BUILD == "client":
    environ["BATCH_SYSTEM"] = cfg.get("site", "HPCsystem")
    environ["BATCH_REQUIREMENTS"] = cfg.get("site", "HPCrequirements")
    environ["BATCH_EXTRA"] = cfg.get("site", "HPCextra")
    environ["BATCH_QUEUE"] = cfg.get("site", "HPCqueue")
    environ["BATCH_NAME"]  = cfg.get("site", "HPCname")
environ["EXEC_DIR_ROOT"] = EXEC_DIR_ROOT

BATCH_DEFAULTS = {key: getenv("BATCH_%s" % key.upper()) for key in ['system', 'requirements', 'extra', 'queue','name']}
BATCH_DEFAULTS['image'] = cfg.get("site","HPCimage")
BATCH_DEFAULTS['numcores']=cfg.get("site","HPCnumcores")
BATCH_DEFAULTS['memory'] = cfg.get("site", "HPCmemory")
BATCH_DEFAULTS['cputime'] = cfg.get("site", "HPCcputime")
BATCH_DEFAULTS['name'] = cfg.get("site", "name")

# JobDB specifics
MAJOR_STATII = tuple(
    [unicode(t) for t in cfg.get("JobDB", "task_major_statii").split(",")] + ["Unknown"])  # adding unknown
FINAL_STATII = tuple([unicode(t) for t in cfg.get("JobDB", "task_final_statii").split(",")])
TYPES = tuple([unicode(t) for t in cfg.get("JobDB", "task_types").split(",")]+['Pilot'])
SITES = tuple([unicode(t) for t in cfg.get("JobDB", "batch_sites").split(",")])

# verify that the site configuration is okay.
if DAMPE_BUILD == "client":
    assert BATCH_DEFAULTS['name'] in cfg.get("JobDB", "batch_sites"), "Batch site %s not in DB" % BATCH_DEFAULTS['name']
    assert BATCH_DEFAULTS['system'] in ["lsf", "sge", "pbs", "condor","slurm","slurm-cscs"], "HPCSystem %s not supported." % BATCH_DEFAULTS["system"]

DAMPE_LOGFILE = cfg.get("global", "logfile")
DAMPE_LOGLEVEL= cfg.get("global", "loglevel")