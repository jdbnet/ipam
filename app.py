from flask import Flask, session
from db import init_db, hash_password, get_db_connection
from routes import register_routes
import os
from dotenv import load_dotenv

os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'changeme')

app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST', 'localhost')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER', 'user')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD', 'password')
app.config['MYSQL_DATABASE'] = os.environ.get('MYSQL_DATABASE', 'ipam')

@app.context_processor
def inject_env_vars():
    version = os.environ.get('VERSION', 'unknown')
    
    # Import has_permission and is_feature_enabled from routes after routes are registered
    from routes import has_permission, is_feature_enabled
    
    return {
        'NAME': os.environ.get('NAME', 'JDB-NET'),
        'LOGO_PNG': os.environ.get('LOGO_PNG', 'https://assets.jdbnet.co.uk/logo/128x128.png'),
        'VERSION': version,
        'has_permission': has_permission,
        'is_feature_enabled': is_feature_enabled
    }

register_routes(app)
init_db(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
