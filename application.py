import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")
    #API Key --> export API_KEY=pk_5bf843bbe3514ecbbdece5359e65b87d


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Populate variables
    userinfo = db.execute("SELECT * FROM users WHERE id = :user_id;", user_id=session["user_id"])
    userstocks = db.execute("SELECT * FROM stocks WHERE username = :name;", name=userinfo[0]["username"])

    # Add latest stock data
    for row in userstocks:
        tempdata = lookup(row["stock"])
        row["companyname"] = tempdata["name"]
        row["price"] = usd(tempdata["price"])
        row["total"] = float(tempdata["price"]) * float(row["shares"])
        row["totalusd"] = usd(row["total"])

    # Calculate total amount of money
    totalmoney = userinfo[0]["cash"]

    for row in userstocks:
        totalmoney = float(totalmoney) + float(row["total"])

    # Render template with updated information
    return render_template("index.html", cash = usd(userinfo[0]["cash"]), stocks = userstocks, total = usd(totalmoney))

@app.route("/cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to your account"""
    if request.method == "POST":

        # Check for valid input
        if not request.form.get("cash"):
            apology("You must provide an amount")
        if int(request.form.get("cash")) < 1:
            apology("You must provide a valid amount of money")

        # Retrieve user information
        userinfo = db.execute("SELECT * FROM users WHERE id = :user_id;", user_id=session["user_id"])

        # Populate variables
        current_cash = float(userinfo[0]["cash"])
        add_amount = float(request.form.get("cash"))
        newamount = current_cash + add_amount

        # Update database
        db.execute("UPDATE users SET cash = :cash WHERE username = :username;", cash = newamount, username = userinfo[0]["username"])

        # Redirect
        return redirect("/")
    else:
        return render_template("cash.html")

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Check that a symbol has been provided
        if not request.form.get("symbol"):
            return apology("You must provide a stock symbol", 403)

        # Check that a number of shares has been provided
        if not request.form.get("shares"):
            return apology("You must provide a valid number of shares", 403)
        if int(request.form.get("shares")) < 1:
            return apology("You must provide a valid number of shares", 403)

        # Check that the symbol matches an existing stock
        if lookup(request.form.get("symbol")) == None:
            return apology("The symbol you provided does not exist.", 403)

        # Populate variables
        userinfo = db.execute("SELECT * FROM users WHERE id = :user_id;", user_id=session["user_id"])
        stockinfo = lookup(request.form.get("symbol"))
        sharesvalue = float(stockinfo["price"]) * float(request.form.get("shares"))
        cashvalue = userinfo[0]["cash"]

        # Chech if there is enough money to buy all the shares
        if sharesvalue > cashvalue:
           return apology("Not enough cash available to complete the purchase", 403)
        else:
            # Check if user owns stock of that company
            sharescheck = db.execute("SELECT shares FROM stocks WHERE stock = :stock AND username = :username;", stock = stockinfo["symbol"], username = userinfo[0]["username"])

            # If the user owns no stock of that company, add new registry
            if len(sharescheck) != 1:
                db.execute("INSERT INTO stocks (stock, username, shares) VALUES (:stock, :username, :shares);", stock = stockinfo["symbol"], username = userinfo[0]["username"], shares = request.form.get("shares"))
                newcashvalue = userinfo[0]["cash"] - sharesvalue
                db.execute("UPDATE users SET cash = :cash WHERE username = :username", cash = newcashvalue, username = userinfo[0]["username"])
                db.execute("INSERT INTO history (username, stock, price, shares) VALUES (:username, :stock, :price, :shares)", username = userinfo[0]["username"], stock = stockinfo["symbol"], price = stockinfo["price"], shares = request.form.get("shares"))
                return redirect("/")

            # Else update current registry
            else:
                currentshares = db.execute("SELECT shares FROM stocks WHERE username = :username AND stock = :stock;", stock = stockinfo["symbol"], username = userinfo[0]["username"])
                totalshares = int(request.form.get("shares")) + int(currentshares[0]["shares"])
                db.execute("UPDATE stocks SET shares = :shares WHERE username = :username AND stock = :stock;", stock = stockinfo["symbol"], username = userinfo[0]["username"], shares = str(totalshares))
                db.execute("INSERT INTO history (username, stock, price, shares) VALUES (:username, :stock, :price, :shares)", username = userinfo[0]["username"], stock = stockinfo["symbol"], price = stockinfo["price"], shares = request.form.get("shares"))
                newcashvalue = userinfo[0]["cash"] - sharesvalue
                db.execute("UPDATE users SET cash = :cash WHERE username = :username", cash = newcashvalue, username = userinfo[0]["username"])
                return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Populate variables
    userinfo = db.execute("SELECT * FROM users WHERE id = :user_id;", user_id=session["user_id"])
    userhistory = db.execute("SELECT * FROM history WHERE username = :name;", name=userinfo[0]["username"])

    # Get prices in USD
    for row in userhistory:
        row["usd"] = usd(row["price"])

    # Render template
    return render_template("history.html", history = userhistory)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("You must provide a username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("You must provide a password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("Invalid username and / or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("must provide a stock symbol", 403)
        stocksymbol = request.form.get("symbol")
        if lookup(stocksymbol) == None:
            return apology("Invalid symbol", 403)
        else:
            stockdata = lookup(stocksymbol)
            return render_template("quoted.html", company=stockdata["name"], price=usd(stockdata["price"]), symbol=stockdata["symbol"])
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("You must provide a username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("You must provide a password", 403)

        # Ensure confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("You must confirm password", 403)

        #Populate variables
        username = request.form.get("username")
        userpassword = request.form.get("password")
        userpasswordconfirm = request.form.get("confirmation")
        hash = generate_password_hash(userpassword)

        # Ensure password and confirmation are the same
        if userpassword != userpasswordconfirm:
            return apology("Passwords do not match", 403)

        # Extract data from database
        namecheck = db.execute("SELECT * FROM users WHERE username = :name;", name = username)

        # Check if username is already in use
        if len(namecheck) != 0:
            return apology("Username is already in use", 404)
        else:
            registeruser = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash);", username=username, hash=hash)
            return redirect("/")

    else:
        return render_template("register.html")

@app.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change password"""
    if request.method == "POST":

        # Retrieve user information
        userinfo = db.execute("SELECT * FROM users WHERE id = :user_id;", user_id=session["user_id"])

        # Check for current password
        if not request.form.get("password"):
            return apology("Must provide current password", 403)

        # Hash provided password and check if it matches one on record (security check)
        storedhash = userinfo[0]["hash"]
        passwordhash = request.form.get("password")

        if not check_password_hash(storedhash, passwordhash):
            return apology("Incorrect password", 403)

        # Check that fields arent empty
        if not request.form.get("newpassword"):
            return apology("Must provide a new passwword", 403)
        if not request.form.get("confirmation"):
            return apology("Must confirm new password", 403)
        if request.form.get("newpassword") != request.form.get("confirmation"):
            return apology("Confirmation does not match new password", 403)

        # Hash new password
        usernewpassword = request.form.get("newpassword")
        hash = generate_password_hash(usernewpassword)

        # Update database
        db.execute("UPDATE users SET hash = :hash WHERE username = :username;", username = userinfo[0]["username"], hash = hash)

        return redirect("/")

    else:
        return render_template("password.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Check that fields arent empty
        if not request.form.get("symbol"):
            return apology("must provide symbol", 403)
        if not request.form.get("shares"):
            return apology("must provide a number of shares", 403)

        # Retrieve data from database
        userinfo = db.execute("SELECT * FROM users WHERE id = :user_id;", user_id=session["user_id"])
        stockcheck = db.execute("SELECT stock, shares FROM stocks WHERE stock = :stock AND username = :username;", stock = request.form.get("symbol"), username = userinfo[0]["username"])

        # Verify that user owns shares of the stock they want to sell
        if len(stockcheck) != 1:
            return apology("You do not own any shares of this particular stock", 403)

        # Populate variables
        totalshares = int(stockcheck[0]["shares"])
        sharestosell = int(request.form.get("shares"))

        # Verify that user owns enough shares
        if totalshares < sharestosell:
            return apology("The number of shares you own is smaller than the number of shares you want to sell", 403)
        else:
            totalshares = totalshares - sharestosell

        # Check current stock data
        stockinfo = lookup(request.form.get("symbol"))

        # Multiply stock value by shares to be sold
        sharesvalue = stockinfo["price"] * float(request.form.get("shares"))

        # Update cash value
        newcashvalue = int(userinfo[0]["cash"]) + int(sharesvalue)

        # Update Database with new number of shares
        db.execute("UPDATE stocks SET shares = :shares WHERE username = :username AND stock = :stock;", stock = stockinfo["symbol"], username=userinfo[0]["username"], shares = str(totalshares))

        #Update history
        db.execute("INSERT INTO history (username, stock, price, shares) VALUES (:username, :stock, :price, :shares)", username = userinfo[0]["username"], stock = stockinfo["symbol"], price = stockinfo["price"], shares = (-1) * int(request.form.get("shares")))

        # Update cash value
        db.execute("UPDATE users SET cash = :cash WHERE username = :username", cash = newcashvalue, username=userinfo[0]["username"])

        # Back to Home
        return redirect("/")
    else:
        return render_template("sell.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
