import configparser
import os
import socket

from flask import Flask
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


def load_config():
    config = configparser.ConfigParser()
    config_file_path = os.path.join(os.path.dirname(__file__), '..', 'config.ini')
    config_file_path = os.path.abspath(config_file_path)
    config.read(config_file_path)
    
    # Check the hostname to load the appropriate environment config
    if socket.gethostname() == 'raspberrypi':
        return config['prod']
    else:
        return config['dev']


#initilize the flask app
app = Flask(__name__)

# Load the correct configuration
env_config = load_config()

#set app config
app.config['SECRET_KEY'] = env_config['secret_key']
app.config['SQLALCHEMY_DATABASE_URI'] = env_config['db_uri']
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

#app.config['MYSQL_PORT'] = '3307'
db = SQLAlchemy(app)
migrate = Migrate(app, db) 

from myrecipes import routes
