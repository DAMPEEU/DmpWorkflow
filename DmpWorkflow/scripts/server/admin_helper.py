'''
Created on Jun 21, 2017
@brief: originally, this code existed as part of workflow_admin.py 
@author: zimmer
@todo: add CLI interface rather than python (later)
'''

from DmpWorkflow.core.models import Job, JobInstance
from datetime import datetime, timedelta
from copy import deepcopy
print 'use Job, JobInstance objects for query, update_dict as standard dict for reset and addInstancesBulk to add streams; use exportJobXml to extract Xml task definition of job'

def assertJob(job):
    if not isinstance(job, Job):
        raise Exception("must be instace of DmpWorkflow.core.models.Job")

def addInstancesBulk(job,nInstances):
    """
       adds <nInstances> to job <job>
       this one is smarter & faster than job.addInstance(inst)
    """
    assertJob(job)
    if nInstances == 0:
        raise Exception("add more than 0 instances!")
    isPilot = True if job.type == "Pilot" else False
    site = job.execution_site
    dummy_dict = {"InputFiles": [], "OutputFiles": [], "MetaData": []}
    query = JobInstance.objects.filter(job=job).order_by("-instanceId")
    inst_id = 1
    if query.count():
        inst_id = query.first().instanceId
    print 'last ID: ',inst_id
    jInstance = JobInstance(body=str(dummy_dict), site = site, isPilot=isPilot)
    jInstance.job = job
    sH = {"status": jInstance.status, "update": jInstance.last_update, "minor_status": jInstance.minor_status}
    jInstance.status_history.append(sH)
    instances = []
    first = inst_id+1
    last  = inst_id+nInstances+1
    if last <= first: raise Exception("Must never happen")
    for i in xrange(first, last):
        jI = deepcopy(jInstance)
        jI.instanceId = i
        instances.append(jI)
    res = JobInstance.objects.insert(instances)
    print "added {added} instances to job {job}".format(job=job.title, added=len(instances))
    return

def exportJobXml(job):
    """
       returns Xml format of old job description
    """
    assertJob(job)
    body = job.body.read()
    job.body.seek(0)
    fo = open("{title}.xml".format(job.title),"w")
    fo.write(body)
    fo.close()
    print 'exported {title}.xml'.format(title=job.title)
    
update_dict = {
    "created_at"    : datetime.now(),
    "last_update"   : datetime.now(),
    "batchId"       : None,
    "Nevents"       : 0,
    "hostname"      : None,
    "status"        : "New",
    "minor_status"  : "AwaitingBatchSubmission",
    "status_history": [],
    "memory"        : [],
    "cpu"           : [],
    "log"           : ""
}