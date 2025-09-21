from flask import Flask
from dotenv import load_dotenv
import os

load_dotenv()

def create_app():
    # Ensure Flask searches project-level templates/static
    pkg_dir = os.path.dirname(__file__)
    root_dir = os.path.dirname(pkg_dir)
    app = Flask(
        __name__,
        static_folder=os.path.join(root_dir, "static"),
        template_folder=os.path.join(root_dir, "templates"),
    )
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret"),
        COMFY_URL=os.environ.get("COMFY_URL", "http://127.0.0.1:8188"),
        UPLOAD_DIR=os.environ.get("UPLOAD_DIR", "uploads"),
        RESULTS_DIR=os.environ.get("RESULTS_DIR", "results"),
    )

    from .auth import auth_bp
    from . import jobs2
    jobs_bp = jobs2.jobs_bp
    from .pages import pages_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(jobs_bp, url_prefix="/api")
    app.register_blueprint(pages_bp)

    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(app.config["RESULTS_DIR"], exist_ok=True)
    # attach app to background worker after blueprints are ready
    try:
        jobs2.attach_app(app)
    except Exception:
        pass
    return app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
