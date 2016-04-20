'''
Created on Apr 20, 2016

@author: zimmer
@brief: prototype script that handles config parsing etc.

'''
import ConfigParser, os
from utils.shell import source_bash
myDefaults = {
              "DAMPE_SW_DIR":".",
              "ExternalsScript":"${DAMPE_SW_DIR}/setup/setup.sh",
              "use_debugger":True,
              "use_reloader":True,
              "task_types":"Generation,Digitization,Reconstruction,User,Other".split(","),
              "task_major_statii":"New,Running,Failed,Terminated,Done,Submitted,Suspended".split(",")
              }



cfg = ConfigParser.SafeConfigParser(defaults=myDefaults)
cfg.read(os.getenv("WorkflowConfig","config/dampe.cfg"))
os.environ["DAMPE_SW_DIR"]=cfg.get("site","DAMPE_SW_DIR")

print "seting up externals"
source_bash(cfg.get("site","ExternalsScript"))

WorkflowRoot = os.getenv("DWF_ROOT",os.getenv("DAMPE_SW_DIR"))
print "ROOT workflow: %s"%WorkflowRoot

pwd = os.getenv("PWD",".")
print "current path %s"%os.path.abspath(pwd)
os.chdir(WorkflowRoot)
# this one sources flask

print "seting up flask"
source_bash("setup.sh")
print "current path %s"%os.curdir

os.chdir(pwd)
print "current path (after everything else) %s"%os.curdir

## done with that.