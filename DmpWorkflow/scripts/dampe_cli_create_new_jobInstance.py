"""
Created on Mar 30, 2016

@author: zimmer
@brief: prototype script to create a new job from the jobXml
"""
import os
import sys
from argparse import ArgumentParser

from werkzeug.exceptions import NotFound

from DmpWorkflow.core import db
from DmpWorkflow.core.models import Job, JobInstance, TYPES
from DmpWorkflow.utils.flask_helpers import parseJobXmlToDict

_TYPES = list(TYPES) + ["NONE"]

dummy_dict = {"InputFiles": [], "OutputFiles": [], "MetaData": []}


def main(args=None):
    usage = "Usage: %prog taskName xmlFile [options]"
    description = "create new instances for job in DB"
    parser = ArgumentParser(usage=usage, description=description)
    # parser.add_option("--instance", dest="inst",type=int, default = None,
    #                  help='use this to offset an instance')
    (opts, arguments) = parser.parse_args(args)
    # if len(sys.argv)!=3:
    #    print parser.print_help()
    #    raise Exception
    taskName = sys.argv[1]
    ninst = int(sys.argv[2])
    db.connect()
    jobs = Job.objects.filter(title=taskName)
    if len(jobs):
        job = jobs[0]
        os.environ['DWF_JOBNAME'] = job.title
        dout = parseJobXmlToDict(job.body)
        if 'type' in dout['atts']:
            job.type = dout['atts']['type']
        if 'release' in dout['atts']:
            job.release = dout['atts']['release']
        if ninst:
            for j in range(ninst):
                jI = JobInstance(body=str(dummy_dict))
                # if opts.inst and j == 0:
                #    job.addInstance(jI,inst=opts.inst)
                # else:
                job.addInstance(jI)
        # print len(job.jobInstances)
        job.update()
        print 'added %i new instances for job %s' % (ninst, taskName)
    else:
        raise NotFound('could not find job %s' % taskName)