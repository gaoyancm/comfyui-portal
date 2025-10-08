from flask import Blueprint, render_template, redirect, url_for, session

from .jobs2 import _list_workflows_impl

pages_bp = Blueprint("pages", __name__)

@pages_bp.get("/")
def home():
    if "user" not in session:
        return redirect(url_for("pages.login_page"))
    workflows = _list_workflows_impl()
    default_workflow = workflows[0]["workflow"] if workflows else ""
    return render_template("main.html", workflows=workflows, default_workflow=default_workflow)


@pages_bp.get("/login")
def login_page():
    return render_template("login.html")


@pages_bp.get("/logout_page")
def logout_page():
    session.clear()
    return render_template("logout.html")


@pages_bp.get("/history")
def history_page():
    if "user" not in session:
        return redirect(url_for("pages.login_page"))
    return render_template("history.html")
