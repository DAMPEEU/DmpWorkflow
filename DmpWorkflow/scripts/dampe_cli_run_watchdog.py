"""
Created on Mar 15, 2016

@author: zimmer
@brief: watchdog that kills the job if needed.
"""
import requests
import importlib
import json
import copy
from argparse import ArgumentParser
from DmpWorkflow.config.defaults import DAMPE_WORKFLOW_URL, BATCH_DEFAULTS, FINAL_STATII, AppLogger, cfg
from DmpWorkflow.utils.tools import getSixDigits
HPC = importlib.import_module("DmpWorkflow.hpc.%s"%BATCH_DEFAULTS['system'])

def main(args=None):
    usage = "Usage: %(prog)s [options]"
    description = "run watchdog"
    parser = ArgumentParser(usage=usage, description=description)
    parser.add_argument("--site", dest="site", type=str, default=None, help='name of site', required=False)
    opts = parser.parse_args(args)
    log = AppLogger("watchdog")
    batchEngine = HPC.BatchEngine()
    batchEngine.update()
    batchsite = BATCH_DEFAULTS['name'] if opts.site is None else opts.site
    res = requests.get("%s/watchdog/" % DAMPE_WORKFLOW_URL, data = {"site":str(batchsite)})
    res.raise_for_status()
    res = res.json()
    if not res.get("result", "nok") == "ok":
        log.error(res.get("error"))
    jobs = res.get("jobs")

    ratio_cpu_max = cfg.get("watchdog","ratio_cpu")
    ratio_mem_max = cfg.get("watchdog","ratio_mem")
    
    site_defaults = BATCH_DEFAULTS    
    for j in jobs:
        job_defaults = copy.deepcopy(site_defaults)
        meta = j['meta']
        for key in ['cputime','memory']:
            for var in meta: 
                if var['name']=="BATCH_OVERRIDE_%s"%key.upper(): 
                    site_defaults[key]=var['value']
        bj = HPC.BatchJob(name="%s-%s"%(j['t_id'],getSixDigits(j['inst_id'])),
                          batchId = j['batchId'],defaults=job_defaults)
        current_cpu = float(j['cpu'])
        current_mem = float(j['memory'])
        max_cpu = bj.getCPU()
        max_mem = bj.getMemory(unit='MB')
        ratio_cpu = current_cpu/max_cpu
        ratio_mem = current_mem/max_mem
        if (ratio_cpu >= ratio_cpu_max) or (ratio_mem >= ratio_mem_max):
            log.info('%s cpu %1.1f mem %1.1f',bj.batchId,ratio_cpu, ratio_mem)
            log.info('Watchdog identified job %s to exceed its resources, terminating', bj.batchId)            
    print 'found %i jobs with requirements'%len(jobs)
    log.info("completed cycle")
if __name__ == '__main__':
    main()
