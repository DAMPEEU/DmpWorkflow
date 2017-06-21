from DmpWorkflow.config.defaults import cfg
from DmpWorkflow import version
import flask_profiler
from socket import getfqdn
kind = cfg.get("global", "installation")

if kind == 'server':    
    
    from flask import Flask
    #!-- DEPRECATED --!
    #from flask.ext.mongoengine import MongoEngine
    from flask_mongoengine import MongoEngine
    app = Flask(__name__)
    app.config.update(LOGGER_NAME="core")
    app.config['MONGODB_DB'] = cfg.get("database", "name")
    app.config['MONGODB_USERNAME'] = cfg.get("database", "user")
    app.config['MONGODB_PASSWORD'] = cfg.get("database", "password")
    app.config['MONGODB_HOST'] = cfg.get("database", "host")
    app.config['MONGODB_PORT'] = int(cfg.get("database", "port"))
    # make connection numbers unbound
    app.config['MONGODB_MAXPOOLSIZE'] = None 
    # time out after 100ms
    app.config['MONGODB_WAITQUEUETIMEOUTMS'] = 100
    app.config["SECRET_KEY"] = "KeepThisS3cr3t"
    app.config["DEBUG"] = True if cfg.get("server","use_debugger") == 'true' else False
    app.config["flask_profiler"] = {
        "enabled": True if cfg.get("server","use_profiler") == 'true' else False,
        "storage": {
            "engine": "mongodb",
            "MONGO_URL": "mongodb://{user}:{password}@{host}:{port}/{db}".format(user=cfg.get("database","user"), 
                                                                                 password=cfg.get("database","password"),
                                                                                 host=cfg.get("database","host"), 
                                                                                 port=cfg.get("database","port"), 
                                                                                 db=cfg.get("database","name")),
            "DATABASE": cfg.get("database","name"),
            "COLLECTION_NAME": "profiler"
        },
        "basicAuth":{
            "enabled": True,
            "username": "admin",
            "password": "secret"
        }
    }
    db = MongoEngine(app)
    
    def register_blueprints(app):
        # Prevents circular imports
        from DmpWorkflow.core.views import jobs
        from DmpWorkflow.core.admin import admin
        app.register_blueprint(jobs)
        app.register_blueprint(admin)
    

    register_blueprints(app)
    
    if app.config['flask_profiler']['enabled']:
        app.logger.info("started flask profiler, recording to %s",app.config['flask_profiler']['storage']['MONGO_URL'])
        flask_profiler.init_app(app)

    
    def main():
        app.logger.info("started DmpWorkflow Server Version: %s on %s",version,getfqdn())
        app.run()
else:
    def main():
        pass

if __name__ == '__main__':
    if kind == 'server':
        main()
