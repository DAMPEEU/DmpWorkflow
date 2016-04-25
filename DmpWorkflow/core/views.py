import copy
import json
import logging
from flask import Blueprint, request, redirect, render_template, url_for
from flask.ext.mongoengine.wtf import model_form
from flask.views import MethodView

from DmpWorkflow.core import app
from DmpWorkflow.core.DmpJob import DmpJob
from DmpWorkflow.core.models import Job, JobInstance
from DmpWorkflow.utils.db_helpers import update_status
from DmpWorkflow.utils.tools import parseJobXmlToDict

jobs = Blueprint('jobs', __name__, template_folder='templates')

logger = app.logger


class ListView(MethodView):
    def get(self):
        jobs = Job.objects.all()
        return render_template('jobs/list.html', jobs=jobs)


class DetailView(MethodView):
    form = model_form(JobInstance, exclude=['created_at', 'status_history'])

    def get_context(self, slug):
        job = Job.objects.get_or_404(slug=slug)
        form = self.form(request.form)

        context = {
            "job": job,
            "form": form
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)
        return render_template('jobs/detail.html', **context)

    def post(self, slug):
        context = self.get_context(slug)
        form = context.get('form')

        if form.validate():
            jobInstance = JobInstance()
            form.populate_obj(jobInstance)

            job = context.get('job')
            job.addInstance(jobInstance)
            job.save()

            return redirect(url_for('jobs.detail', slug=slug))

        return render_template('jobs/detail.html', **context)


class JobView(MethodView):
    def get(self):
        return "Nothing to display"

    def post(self):
        try:
            taskname = request.form.get("taskname",None)
            jobdesc = request.files.get("file",None)
            t_type = request.form.get("t_type",None)
            n_instances = int(request.form.get("n_instances","0"))
            if taskname is None:
                logger.exception("task name must be defined.")
                raise Exception("task name must be defined")
            job = Job(title=taskname, type=t_type)
            job.body.put(jobdesc, content_type="application/xml")
            job.save()
            dout = parseJobXmlToDict(job.body.read())
            if 'type' in dout['atts']:
                job.type = dout['atts']['type']
            if 'release' in dout['atts']:
                job.release = dout['atts']['release']
            if t_type is not None: job.type = t_type
            dummy_dict = {"InputFiles": [], "OutputFiles": [], "MetaData": []}
            if n_instances:
                for j in range(n_instances):
                    jI = JobInstance(body=str(dummy_dict))
                    job.addInstance(jI)
            # print len(job.jobInstances)
            job.update()
            return json.dumps({"result": "ok", "jobID": str(job.id)})
        except Exception as err:
            logger.info("request dict: %s"%str(request.form))
            logger.exception(err)
            return json.dumps({"result": "nok", "jobID": "None", "error":str(err)})

class JobInstanceView(MethodView):
    def get(self):
        return 'Nothing yet'

    def post(self):
        taskName = request.form.get("taskname",None)
        ninst = int(request.form.get("n_instances","0"))
        jobs = Job.objects.filter(title=taskName)
        if len(jobs):
            logger.debug("Found job")
            job = jobs[0]
            dout = parseJobXmlToDict(job.body.read())
            if 'type' in dout['atts']:
                job.type = unicode(dout['atts']['type'])
            if 'release' in dout['atts']:
                job.release = dout['atts']['release']
            dummy_dict = {"InputFiles": [], "OutputFiles": [], "MetaData": []}
            if ninst:
                for j in range(ninst):
                    jI = JobInstance(body=str(dummy_dict))
                    # if opts.inst and j == 0:
                    #    job.addInstance(jI,inst=opts.inst)
                    # else:
                    job.addInstance(jI)
            # print len(job.jobInstances)
            job.update()
            return json.dumps({"result": "ok"})
        else:
            logger.error("Cannot find job")
            return json.dumps({"result": "nok", "error": 'Could not find job %s' % taskName})


class RefreshJobAlive(MethodView):
    def post(self):
        try:
            taskid = request.form.get("taskid",None)
            instance_id = request.form.get("instanceid",None)
            hostname = request.form.get("hostname","")
            status = request.form.get("status","None")
            my_job = Job.objects.filter(id=taskid)
            jInstance = my_job.getInstance(instance_id)
            jInstance.set("hostname", hostname)
            oldStatus = jInstance.status
            if status != oldStatus:
                jInstance.setStatus(status)
            my_job.update()
            return json.dumps({"result": "ok"})
        except Exception as err:
            logger.exception(err)
            return json.dumps({"result": "nok", "error": "server error"})


class SetJobStatus(MethodView):
    def post(self):
        arguments = request.form.get('args',None)
        try:
            update_status(arguments['t_id'], arguments["inst_id"], arguments['major_status'], **arguments)
        except Exception as err:
            logger.exception(err)
            return json.dumps({"result": "nok", "error": str(err)})
        return json.dumps({"result": "ok"})


class NewJobs(MethodView):
    def get(self):
        newJobInstances = []
        allJobs = Job.objects.all()
        logger.info("allJobs = %s"%str(allJobs))
        for job in allJobs:
            newJobs = JobInstance.objects.filter(job=job, status=u"New")
            logger.info("newJobs: %s"%str(newJobs))
            if len(newJobs):
                logger.info("found %i new instances for job %s"%(len(newJobs),str(job.title)))
                dJob = DmpJob(job.id, job.body.read())
                for j in newJobs:
                    dInstance = copy.deepcopy(dJob)
                    dInstance.setInstanceParameters(j.instanceId, j.body)
                    newJobInstances.append(dInstance.exportToJSON())
        return json.dumps({"jobs": newJobInstances})

# Register the urls
jobs.add_url_rule('/', view_func=ListView.as_view('list'))
jobs.add_url_rule('/<slug>/', view_func=DetailView.as_view('detail'))
jobs.add_url_rule("/job/", view_func=JobView.as_view('jobs'), methods=["GET", "POST"])
jobs.add_url_rule("/jobInstances/", view_func=JobInstanceView.as_view('jobinstances'), methods=["GET", "POST"])
jobs.add_url_rule("/jobalive/", view_func=RefreshJobAlive.as_view('jobalive'), methods=["POST"])
jobs.add_url_rule("/jobstatus/", view_func=SetJobStatus.as_view('jobstatus'), methods=["POST"])
jobs.add_url_rule("/newjobs/", view_func=NewJobs.as_view('newjobs'), methods=["GET"])
