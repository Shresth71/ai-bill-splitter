import logging
import traceback
from flask import current_app
import re
import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import Flask, render_template, request
from qr_utils import generate_qr_base64

# Configure logging to see detailed errors
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask application
app = Flask(__name__)

# ===== Production Config =====
app.config.update(
    SECRET_KEY=os.environ.get('SECRET_KEY', 'dev-key-just-for-development'),
    UPLOAD_FOLDER='uploads',
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max upload
    SESSION_COOKIE_SECURE=False,  # Changed to False for development
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# ===== Fix Reverse Proxy Issues =====
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ===== Create Uploads Folder =====
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize application components - moved after imports
try:
    from bill_splitter import BillSplitter
    from chatbot_utils import GeminiExpenseChatbot
    chatbot = GeminiExpenseChatbot()
    bill_splitters = {}
except ImportError as e:
    logger.error(f"Error importing modules: {e}")
    # Create placeholder to prevent app crashing
    bill_splitters = {}
    chatbot = None

USERS_FILE = "users.json"

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r') as f:
                return json.load(f)
        else:
            logger.warning(f"Users file not found: {USERS_FILE}. Creating empty users dict.")
            # Create the file with an empty dictionary
            with open(USERS_FILE, 'w') as f:
                json.dump({}, f)
            return {}
    except Exception as e:
        logger.error(f"Error loading users: {str(e)}")
        return {}

def save_users(users):
    try:
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving users: {str(e)}")

# Load users at startup
users = load_users()

# ===== Route Definitions =====
@app.route("/payment_qr")
def payment_qr():
    try:
        # Simulate or get from bill data
        upi_id = "yourupi@upi"
        amount = 150
        name = "Bill Splitter"

        upi_url = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR"
        qr_img = generate_qr_base64(upi_url)
        return render_template("qr_display.html", qr_img=qr_img)
    except Exception as e:
        logger.error(f"Error in payment_qr: {str(e)}")
        flash("Failed to generate QR code", "danger")
        return redirect(url_for('home'))

@app.route('/')
def home():
    try:
        if 'username' not in session:
            return redirect(url_for('login'))
        
        user_groups = []
        for group_id, group_info in users.get(session['username'], {}).get('groups', {}).items():
            user_groups.append({
                'id': group_id,
                'name': group_info.get('name', 'Unnamed Group')
            })
        
        return render_template('home.html', groups=user_groups)
    except Exception as e:
        logger.error(f"Error in home route: {str(e)}")
        flash("An error occurred", "danger")
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    try:
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            if not username or not password:
                flash('Username and password are required', 'danger')
                return redirect(url_for('login'))
            
            if username in users and check_password_hash(users[username]['password'], password):
                session['username'] = username
                flash('Logged in successfully!', 'success')
                return redirect(url_for('home'))
            else:
                flash('Invalid credentials', 'danger')
        
        return render_template('login.html')
    except Exception as e:
        logger.error(f"Error in login route: {traceback.format_exc()}")
        flash("An error occurred during login", "danger")
        # If the error is related to the template, return a basic HTML response
        return """
        <html>
            <head>
                <title>Login - AI Bill Splitter</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 20px; }
                    .error { color: red; }
                    .container { max-width: 400px; margin: 0 auto; }
                    input { width: 100%; padding: 8px; margin: 8px 0; }
                    button { padding: 10px; background-color: #4CAF50; color: white; border: none; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>Login</h2>
                    <p class="error">Sorry, an error occurred. Please try again.</p>
                    <form method="post">
                        <div>
                            <label for="username">Username:</label>
                            <input type="text" id="username" name="username" required>
                        </div>
                        <div>
                            <label for="password">Password:</label>
                            <input type="password" id="password" name="password" required>
                        </div>
                        <button type="submit">Login</button>
                    </form>
                    <p>Don't have an account? <a href="/register">Register here</a></p>
                </div>
            </body>
        </html>
        """

@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            email = request.form['email']
            
            if username in users:
                flash('Username already exists', 'danger')
            else:
                users[username] = {
                    'password': generate_password_hash(password),
                    'email': email,
                    'groups': {}
                }
                save_users(users)
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
        
        return render_template('register.html')
    except Exception as e:
        logger.error(f"Error in register route: {str(e)}")
        flash("An error occurred during registration", "danger")
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/create_group', methods=['GET', 'POST'])
def create_group():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    try:
        if request.method == 'POST':
            group_name = request.form['group_name']
            group_id = f"group_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            storage_file = f"{group_id}.json"
            bill_splitters[group_id] = BillSplitter(storage_file=storage_file)
            bill_splitters[group_id].add_user(session['username'])
            
            if session['username'] not in users:
                users[session['username']] = {'groups': {}}
                
            users[session['username']]['groups'][group_id] = {
                'name': group_name,
                'role': 'admin'
            }
            save_users(users)
            
            flash(f'Group "{group_name}" created successfully!', 'success')
            return redirect(url_for('group_dashboard', group_id=group_id))
        
        return render_template('create_group.html')
    except Exception as e:
        logger.error(f"Error in create_group: {str(e)}")
        flash("Failed to create group", "danger")
        return redirect(url_for('home'))

@app.route('/group/<group_id>')
def group_dashboard(group_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    try:
        if group_id not in users.get(session['username'], {}).get('groups', {}):
            flash('You do not have access to this group', 'danger')
            return redirect(url_for('home'))
        
        if group_id not in bill_splitters:
            storage_file = f"{group_id}.json"
            bill_splitters[group_id] = BillSplitter(storage_file=storage_file)
        
        bs = bill_splitters[group_id]
        expense_summary = bs.get_expense_summary()
        settlements = bs.calculate_balances()
        user_info = bs.get_user_expenses(session['username'])
        
        if isinstance(user_info, str):
            user_info = None
        
        return render_template(
            'group_dashboard.html',
            group_id=group_id,
            group_name=users[session['username']]['groups'][group_id]['name'],
            expense_summary=expense_summary,
            settlements=settlements,
            user_info=user_info,
            expenses=bs.expenses,
            group_users=list(bs.users)
        )
    except Exception as e:
        logger.error(f"Error in group_dashboard: {str(e)}")
        flash("Failed to load group dashboard", "danger")
        return redirect(url_for('home'))

@app.route('/group/<group_id>/add_user', methods=['POST'])
def add_user_to_group(group_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    try:
        if group_id not in users.get(session['username'], {}).get('groups', {}) or \
           users[session['username']]['groups'][group_id]['role'] != 'admin':
            flash('You do not have admin access to this group', 'danger')
            return redirect(url_for('group_dashboard', group_id=group_id))
        
        username = request.form['username']
        
        if username not in users:
            flash(f'User "{username}" does not exist', 'danger')
            return redirect(url_for('group_dashboard', group_id=group_id))
        
        if group_id not in bill_splitters:
            storage_file = f"{group_id}.json"
            bill_splitters[group_id] = BillSplitter(storage_file=storage_file)
        
        bs = bill_splitters[group_id]
        message = bs.add_user(username)
        
        if 'groups' not in users[username]:
            users[username]['groups'] = {}
            
        users[username]['groups'][group_id] = {
            'name': users[session['username']]['groups'][group_id]['name'],
            'role': 'member'
        }
        save_users(users)
        
        flash(message, 'success')
        return redirect(url_for('group_dashboard', group_id=group_id))
    except Exception as e:
        logger.error(f"Error in add_user_to_group: {str(e)}")
        flash("Failed to add user", "danger")
        return redirect(url_for('group_dashboard', group_id=group_id))

@app.route('/group/<group_id>/add_expense', methods=['POST'])
def add_expense(group_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    try:
        if group_id not in users.get(session['username'], {}).get('groups', {}):
            flash('You do not have access to this group', 'danger')
            return redirect(url_for('home'))
        
        if group_id not in bill_splitters:
            storage_file = f"{group_id}.json"
            bill_splitters[group_id] = BillSplitter(storage_file=storage_file)
        
        bs = bill_splitters[group_id]
        paid_by = request.form['paid_by']
        amount = request.form['amount']
        description = request.form['description']
        category = request.form.get('category', '')
        participants = request.form.getlist('participants')
        
        message = bs.add_expense(paid_by, amount, description, participants)
        
        if category and message.startswith("Expense"):
            expense_id = len(bs.expenses) - 1  # Fixed to use the correct index
            bs.categorize_expense(expense_id, category)
        
        flash(message, 'success')
        return redirect(url_for('group_dashboard', group_id=group_id))
    except Exception as e:
        logger.error(f"Error in add_expense: {str(e)}")
        flash("Failed to add expense", "danger")
        return redirect(url_for('group_dashboard', group_id=group_id))

@app.route('/group/<group_id>/categorize_expense', methods=['POST'])
def categorize_expense(group_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    
    try:
        if group_id not in users.get(session['username'], {}).get('groups', {}):
            flash('You do not have access to this group', 'danger')
            return redirect(url_for('home'))
        
        if group_id not in bill_splitters:
            storage_file = f"{group_id}.json"
            bill_splitters[group_id] = BillSplitter(storage_file=storage_file)
        
        bs = bill_splitters[group_id]
        expense_id = int(request.form['expense_id'])
        category = request.form['category']
        
        message = bs.categorize_expense(expense_id, category)
        flash(message, 'success')
        return redirect(url_for('group_dashboard', group_id=group_id))
    except Exception as e:
        logger.error(f"Error in categorize_expense: {str(e)}")
        flash("Failed to categorize expense", "danger")
        return redirect(url_for('group_dashboard', group_id=group_id))

@app.route('/group/<group_id>/chatbot', methods=['POST'])
def process_chatbot_request(group_id):
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Please log in first"}), 401

    try:
        if group_id not in users.get(session['username'], {}).get('groups', {}):
            return jsonify({"status": "error", "message": "You don't have access to this group"}), 403

        message = request.json.get('message', '').strip()
        if not message:
            return jsonify({"status": "error", "message": "No message provided"}), 400

        if chatbot is None:
            return jsonify({"status": "error", "message": "Chatbot is not available"}), 500

        if group_id not in bill_splitters:
            storage_file = f"{group_id}.json"
            bill_splitters[group_id] = BillSplitter(storage_file=storage_file)

        bs = bill_splitters[group_id]
        parsed_data = chatbot.process_expense(message)

        if parsed_data["status"] == "error":
            return jsonify({
                "status": "error",
                "message": parsed_data["message"]
            }), 400

        # Ensure participants exist
        for participant in parsed_data["participants"]:
            if participant != session['username'] and participant not in bs.users:
                if participant in users:
                    bs.add_user(participant)
                    users[participant]['groups'][group_id] = {
                        'name': users[session['username']]['groups'][group_id]['name'],
                        'role': 'member'
                    }
                    save_users(users)
                else:
                    bs.add_user(participant)

        # Add expense
        expense_result = bs.add_expense(
            parsed_data["paid_by"],
            parsed_data["amount"],
            parsed_data["description"],
            parsed_data["participants"],
            parsed_data.get("date")
        )

        if not expense_result.startswith("Expense"):
            return jsonify({
                "status": "error",
                "message": f"Failed to add expense: {expense_result}"
            }), 400

        # Categorize if available
        if 'category' in parsed_data and parsed_data["category"] != "other":
            expense_id = len(bs.expenses) - 1
            bs.categorize_expense(expense_id, parsed_data["category"])

        new_expense = {
            "paid_by": parsed_data["paid_by"],
            "amount": parsed_data["amount"],
            "description": parsed_data["description"],
            "participants": parsed_data["participants"],
            "date": parsed_data.get("date", datetime.now().strftime("%Y-%m-%d")),
            "category": parsed_data.get("category", "other")
        }

        return jsonify({
            "status": "success",
            "message": f"Expense added: {parsed_data['description']} - ₹{parsed_data['amount']}",
            "data_type": "expense",
            "expense": new_expense
        })

    except Exception as e:
        logger.error(f"Error in process_chatbot_request: {traceback.format_exc()}")
        return jsonify({
            "status": "error",
            "message": f"An error occurred: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

@app.route('/group/<group_id>/chatbot/query', methods=['GET'])
def chatbot_query(group_id):
    if 'username' not in session:
        return jsonify({"status": "error", "message": "Please log in first"}), 401
    
    try:
        query_type = request.args.get('type', 'help')
        
        if query_type == 'help':
            if chatbot is None:
                return jsonify({
                    "status": "success", 
                    "message": "Chatbot help is currently unavailable.",
                    "data_type": "help"
                })
            return jsonify({
                "status": "success",
                "message": chatbot.responses['help'],
                "data_type": "help"
            })
        elif query_type == 'commands':
            commands = [
                {"name": "Add expense", "example": "I spent ₹500 on dinner with Alice"},
                {"name": "Check balance", "example": "What's my current balance?"},
                {"name": "Category summary", "example": "Show my expenses by category"},
                {"name": "Specific debt", "example": "How much does Alice owe me?"},
                {"name": "Categorize", "example": "Categorize expense 3 as food"},
                {"name": "Delete", "example": "Delete expense 2"}
            ]
            return jsonify({
                "status": "success",
                "data": commands,
                "data_type": "commands"
            })
            
        return jsonify({
            "status": "error",
            "message": "Unknown query type"
        }), 400
    except Exception as e:
        logger.error(f"Error in chatbot_query: {str(e)}")
        return jsonify({
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }), 500

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"500 error: {str(e)}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)