from flask import Flask, request, render_template, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
import requests
import time

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///energy_trading.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)

class Listing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    units = db.Column(db.Float, nullable=False)
    price_per_unit = db.Column(db.Float, nullable=False)
    esp32_ip = db.Column(db.String(50), nullable=False)

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    active_time = db.Column(db.Float, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return "Username already exists!"
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        return "Invalid credentials!"
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/sell', methods=['GET', 'POST'])
def sell():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        units = float(request.form['units'])
        price_per_unit = float(request.form['price_per_unit'])
        esp32_ip = request.form['esp32_ip']
        user_id = session['user_id']
        listing = Listing(user_id=user_id, units=units, price_per_unit=price_per_unit, esp32_ip=esp32_ip)
        db.session.add(listing)
        db.session.commit()
        return redirect(url_for('dashboard'))
    return render_template('sell.html')

@app.route('/buy', methods=['GET', 'POST'])
def buy():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    listings = Listing.query.all()
    if request.method == 'POST':
        seller_id = int(request.form['seller_id'])
        buyer_id = session['user_id']
        seller = Listing.query.filter_by(id=seller_id).first()
        if not seller:
            return "Invalid seller!"
        session['seller_id'] = seller.id
        session['seller_ip'] = seller.esp32_ip
        session['price_per_unit'] = seller.price_per_unit
        session['buyer_ip'] = request.form['buyer_ip']
        return redirect(url_for('transfer'))
    return render_template('buy.html', listings=listings)

@app.route('/transfer', methods=['GET', 'POST'])
def transfer():
    if 'seller_id' not in session or 'buyer_ip' not in session:
        return redirect(url_for('buy'))
    if request.method == 'POST':
        action = request.form['action']
        if action == 'start':
            start_time = time.time()
            session['start_time'] = start_time
            requests.post(f"http://{session['seller_ip']}/start", json={"sendIp": session['seller_ip'], "receiveIp": session['buyer_ip'], "price": session['price_per_unit']})
            requests.post(f"http://{session['buyer_ip']}/start", json={"sendIp": session['seller_ip'], "receiveIp": session['buyer_ip'], "price": session['price_per_unit']})
        elif action == 'stop':
            stop_time = time.time()
            active_time = stop_time - session['start_time']
            active_time = round(active_time, 2)  # Round to 2 decimal places
            final_price = round(session['price_per_unit'] * active_time * 0.002778, 2)
            seller = Listing.query.filter_by(id=session['seller_id']).first()
            seller.units -= active_time * 0.002778
            if seller.units <= 0:
                db.session.delete(seller)
            transaction = Transaction(
                buyer_id=session['user_id'],
                seller_id=seller.user_id,
                active_time=active_time,
                total_price=final_price
            )
            db.session.add(transaction)
            db.session.commit()
            requests.post(f"http://{session['seller_ip']}/stop")
            requests.post(f"http://{session['buyer_ip']}/stop")
            return render_template('result.html', active_time=active_time, final_price=final_price)
    return render_template('transfer.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Database initialization
with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
