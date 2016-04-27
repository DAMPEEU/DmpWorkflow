"""
Created on Mar 15, 2016

@author: zimmer
"""
import requests
from argparse import ArgumentParser
from DmpWorkflow.core.DmpJob import DmpJob
from DmpWorkflow.config.defaults import DAMPE_WORKFLOW_URL, BATCH_DEFAULTS

def main(args=None):
    parser = ArgumentParser(usage="Usage: %(prog)s taskName xmlFile [options]", description="create new job in DB")
    parser.add_argument("-d", "--dry", dest="dry", action = 'store_true', default=False, help='if dry, do not try interacting with batch farm')
    parser.add_argument("-l", "--local", dest="local", action = 'store_true', default=False, help='run locally')
    opts = parser.parse_args(args)
    batchsite = BATCH_DEFAULTS['name']
    res = requests.get("%s/newjobs/" % DAMPE_WORKFLOW_URL, date = {"site":str(batchsite)})
    res.raise_for_status()
    res = res.json()
    if not res.get("result", "nok") == "ok":
        print "error %s" % res.get("error")
    jobs = res.get("jobs")
    print 'found %i new job instances to deploy' % len(jobs)
    for job in jobs:
        j = DmpJob.fromJSON(job)
        j.write_script()
        j.submit(dry=opts.dry,local=opts.local)
                
if __name__ == "__main__":
    main()
