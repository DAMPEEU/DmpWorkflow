"""
Created on Mar 15, 2016

@author: zimmer
@todo: fix logging.
"""
#import logging
from requests import get, post 
from sys import exit as sys_exit
from json import dumps
from argparse import ArgumentParser
from DmpWorkflow.core.DmpJob import DmpJob
from DmpWorkflow.config.defaults import DAMPE_WORKFLOW_URL, BATCH_DEFAULTS
from DmpWorkflow.utils.tools import send_heartbeat
from importlib import import_module
HPC = import_module("DmpWorkflow.hpc.%s" % BATCH_DEFAULTS['system'])

# from DmpWorkflow.scripts.client.watchdog import __getRunningJobs

def main(args=None):
    parser = ArgumentParser(usage="Usage: %(prog)s taskName xmlFile [options]", description="create new job in DB")
    parser.add_argument("-d", "--dry", dest="dry", action='store_true', default=False,
                        help='if dry, do not try interacting with batch farm')
    parser.add_argument("-l", "--local", dest="local", action='store_true', default=False, help='run locally')
    parser.add_argument("-p", "--pythonbin", dest="python", default=None, type=str,
                        help='the python executable if non standard is chosen')
    parser.add_argument("--pilotReference", dest="pref", default=None, type=str,
                        help='pilot reference (instanceId) of pilot')
    parser.add_argument("--pilot",dest='pilot', action='store_true', default=False, help="run in pilot mode")
    parser.add_argument("-c", "--chunk", dest="chunk", default=100, type=int,
                        help='number of jobs to process per cycle')
    parser.add_argument("-m", "--maxJobs", dest="maxJobs", default=None, type=int,
                        help='number of jobs that can be in the system')
    parser.add_argument("-s", "--skipDBcheck", dest="skipDBcheck", action='store_true', default=False,
                        help='skip DB check for jobs')
    send_heartbeat("JobFetcher") # encapsulates the heartbeat update!
    opts = parser.parse_args(args)
    pilot = opts.pilot
    if pilot: 
        print "running in pilot mode - deploying pilots if there are jobs to run"
    # FIXME: fix logging
    #log = logging.getLogger("script")
    batchsite = BATCH_DEFAULTS['name']
    print 'workflow server url: {url}'.format(url=DAMPE_WORKFLOW_URL)
    if opts.maxJobs is not None:
        val = 0
        if opts.skipDBcheck:
            print 'skipping DB check, assume no jobs to be in the system'
        else:
            stats = 'Running,Submitted'
            res = get("%s/newjobs/" % DAMPE_WORKFLOW_URL,
                          data={"site": str(batchsite), "status_list": stats, "fastQuery":"True", "pilot":"True" if pilot else "False"})
            res.raise_for_status()
            res = res.json()
            if not res.get("result", "nok") == "ok":
                #log.error(res.get("error"))
                print 'ERROR: {error}'.format(error=res.get("error","n/a"))
            val += res.get("jobs")
        #log.info('found %i jobs running or pending', val)
        print 'INFO: {msg}'.format(msg='found %i jobs running or pending'%val)
        if val >= opts.maxJobs:
            #log.warning(
            #    "reached maximum number of jobs per site, not submitting anything, change this value by setting it to higher value")
            print 'WARNING: {msg}'.format(msg="reached maximum number of jobs per site, not submitting anything, change this value by setting it to higher value")
            sys_exit();
    d_dict = {"site": str(batchsite), "limit": opts.chunk}
    if pilot: 
        d_dict['pilot']='True'
    res = get("%s/newjobs/" % DAMPE_WORKFLOW_URL, data=d_dict)
    res.raise_for_status()
    res = res.json()
    if not res.get("result", "nok") == "ok":
        print 'ERROR: {error}'.format(error=res.get("error","n/a"))
        #log.error(res.get("error"))
    jobs = res.get("jobs")
    #log.info('found %i new job instances to deploy this cycle', len(jobs))
    print 'INFO: {msg}'.format(msg='found %i new job instances to deploy this cycle'%len(jobs))
    njobs = 0
    # replace old submission block with a bulk submit
    data = []
    pilotReference = "None"
    if opts.pref is not None: 
        pilotReference = opts.pref
    if opts.local:
        for job in jobs:
            j = DmpJob.fromJSON(job)
            if pilot: j.setAsPilot(True)
            if pilotReference != "None": j.setPilotReference(pilotReference)
            j.write_script(pythonbin=opts.python, debug=opts.dry)
            try:
                ret = j.submit(dry=opts.dry, local=True)
                j.updateStatus("Submitted", "WaitingForExecution", batchId=ret, cpu=0., memory=0., timeout=None, attempts=1)
                njobs += 1
            except Exception, e:
                #log.exception(e)
                print 'EXCEPTION: {exc}'.format(exc=e)
    else:
        for job in jobs:
            j = DmpJob.fromJSON(job)
            if pilot: j.setAsPilot(True)
            j.write_script(pythonbin=opts.python, debug=opts.dry)
            try:
                j.submit(dry=opts.dry)
                if not opts.dry:
                    data.append({"t_id":j.jobId, "instanceId":j.instanceId})
                    njobs += 1 
            except Exception, e:
                #log.exception(e)
                print 'EXCEPTION: {exc}'.format(exc=e)
        if njobs:
            # done submitting, now do bulk update
            res = post("%s/jobstatusBulk/" % DAMPE_WORKFLOW_URL, 
                       data={"data":dumps(data),"status":"Submitted","minor_status":"WaitingForExecution"})
            res.raise_for_status()
            res = res.json()
            if not res.get("result", "nok") == "ok":
                #log.error(res.get("error"))
                print 'ERROR: {error}'.format(error=res.get("error","n/a"))
                return
            #log.info("updated %i jobs", int(res.get("njobs",0)))
            print 'INFO: {msg}'.format(msg="updated %i jobs"%int(res.get("njobs",0)))
    #log.info("cycle completed, submitted %i new jobs", njobs)
    print "INFO: {msg}".format(msg = "cycle completed, submitted %i new jobs" % njobs)

if __name__ == "__main__":
    main()
