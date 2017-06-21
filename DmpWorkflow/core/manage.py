# Set the path
from os.path import abspath, join as oPjoin, dirname
from sys import path as sys_path

sys_path.append(abspath(oPjoin(dirname(__file__), '..')))
from flask_script import Manager, Server, Shell
import DmpWorkflow.core.models as DmpWorkflowModels
from DmpWorkflow.core import app, db
from DmpWorkflow.config.defaults import cfg


def _make_context():
    return dict(app=app, db=db, models=DmpWorkflowModels)


manager = Manager(app)
# Turn on debugger by default and reloader
manager.add_command("runserver", Server(use_debugger=cfg.getboolean("server", "use_debugger"),
                                        use_reloader=cfg.getboolean("server", "use_reloader"),
                                        host=cfg.get("server", "host"))
                    )

manager.add_command("shell", Shell(make_context=_make_context))


def main():
    manager.run()


if __name__ == "__main__":
    main()
