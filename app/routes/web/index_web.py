from flask import Blueprint, render_template

index_web_bp = Blueprint("index_web", __name__)

@index_web_bp.route("/")
def home():
    return render_template("home.html")

@index_web_bp.route("/contacto")
def contacto():
    return render_template("contacto.html")

@index_web_bp.route("/acerca")
def acerca():
    return render_template("acerca.html")
