import socket

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'testing - need to replace!'

if socket.gethostname() == 'raspberrypi':
    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://phil:pythonproj2@192.168.1.143/MyRecipes'
else:
#    app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://phil:pythonproj2@192.168.1.143/MyRecipes_DEV'
     app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://phil:password_4_PKS@192.168.1.143:3307/MyRecipes_DEV'


app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

#app.config['MYSQL_PORT'] = '3307'
db = SQLAlchemy(app)
migrate = Migrate(app, db) 

from myrecipes import routes
