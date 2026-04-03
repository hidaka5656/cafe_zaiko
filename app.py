from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/detail/<item_name>")
def detail(item_name):
    return render_template("detail.html", item_name=item_name)


@app.route("/alerts")
def alerts():
    return render_template("alerts.html")


if __name__ == "__main__":
    app.run(debug=True)
