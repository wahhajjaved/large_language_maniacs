from flask import Flask, render_template
import os
import jinja2
import crawler

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir))

app=Flask(__name__)

@app.route('/')
def home():
    length = len(crawler.df2)
    return render_template("index.html", data=crawler.df2, length=length)

@app.route('/sortPrice')
def price():
    length = len(crawler.df2)
    return render_template("index.html", data=crawler.sortByKey(crawler.dataToArray(crawler.df2,"Price"),4), length=length)

@app.route('/sortPercent')
def percent():
    length = len(crawler.df2)
    return render_template("index.html", data=crawler.sortByKey(crawler.dataToArray(crawler.df2,"Percent Off"),6), length=length)

@app.route('/sortMoneyOff')
def moneyOff():
    length = len(crawler.df2)
    return render_template("index.html", data=crawler.sortByKey(crawler.dataToArray(crawler.df2,"Money Off"),7), length=length)

@app.route('/sortOriginalPrice')
def originalPrice():
    length = len(crawler.df2)
    return render_template("index.html", data=crawler.sortByKey(crawler.dataToArray(crawler.df2,"Original Price"),5), length=length)


if __name__=="__main__":
    app.run(debug=True)
