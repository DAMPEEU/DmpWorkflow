"""
Created on Mar 10, 2016
@author: zimmer
"""
import logging
from flask import Blueprint, request, redirect, render_template, url_for, send_file
from flask.views import MethodView
from datetime import datetime, timedelta
#!-- DEPRECATED --!
#from flask.ext.mongoengine.wtf import model_form
from flask_mongoengine.wtf import model_form
from DmpWorkflow.core.auth import requires_auth
from DmpWorkflow.core.models import Job, JobInstance
from StringIO import StringIO

admin = Blueprint('admin', __name__, template_folder='templates')
logger = logging.getLogger("core")


class List(MethodView):
    decorators = [requires_auth]
    cls = Job

    def get(self):
        days_since=int(request.args.get("days_since",30))
        hours_since=int(request.args.get("horus_since",0))
        new_date = datetime.now() - timedelta(days = days_since, hours = hours_since)
        jobs = JobInstance.objects.filter(last_update__gte=new_date).distinct("job")
        return render_template('admin/list.html', jobs=jobs)

class Remove(MethodView):
    decorators = [requires_auth]
    confirm = True

    def get(self, slug=None):
        if slug:
            job = Job.objects.get_or_404(slug=slug)
            job.delete()
            logger.info("removing job %s", slug)
        return redirect(url_for('admin.index'))


class Export(MethodView):
    decorators = [requires_auth]

    def get(self, slug=None):
        if slug is None:
            raise Exception("must be called with slug")
        job = Job.objects.get_or_404(slug=slug)
        body = job.body.read()
        job.body.seek(0)
        outfile = StringIO()
        outfile.write(body)
        outfile.seek(0)
        logger.info("exporting body %s", slug)
        return send_file(outfile, attachment_filename="%s.xml" % job.title, as_attachment=True)


class Detail(MethodView):
    decorators = [requires_auth]

    def get_context(self, slug=None):
        form_cls = model_form(Job, exclude=('created_at', 'jobInstances'))

        if slug:
            job = Job.objects.get_or_404(slug=slug)
            if request.method == 'POST':
                form = form_cls(request.form, inital=job.getData())
                logger.info("POST request from form")
            else:
                form = form_cls(obj=job)
                logger.info("other request")
        else:
            job = Job()
            form = form_cls(request.form)

        context = {
            "job": job,
            "form": form,
            "create": slug is None
        }
        return context

    def get(self, slug):
        context = self.get_context(slug)
        return render_template('admin/detail.html', **context)

    def post(self, slug):
        context = self.get_context(slug)
        form = context.get('form')
        logger.info(form.slug.data)
        if form.validate():
            job = context.get('job')
            form.populate_obj(job)
            job.save()

            return redirect(url_for('admin.index'))
        return render_template('admin/detail.html', **context)


# Register the urls
admin.add_url_rule('/admin/', view_func=List.as_view('index'))
admin.add_url_rule('/admin/create/', defaults={'slug': None}, view_func=Detail.as_view('create'))
# admin.add_url_rule('/admin/edit/<slug>/', view_func=Detail.as_view('edit'))
admin.add_url_rule('/admin/export/<slug>/', view_func=Export.as_view('export'))
admin.add_url_rule('/admin/remove/<slug>/', view_func=Remove.as_view('remove'))