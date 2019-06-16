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

# GET AND POST ?
@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""

    if request.method == "POST":
        return render_template("/")
    # User reached route via GET (as by clicking a link or via redirect)  
    else:
        # Fetch symbols of stocks and the shares owned by the User
        owned = db.execute("SELECT * FROM owned JOIN stocksymbols ON owned.symbolID = stocksymbols.id WHERE owned.userID = :userID ",
                            userID = session.get('user_id'))
        
        cash = db.execute("SELECT cash FROM users WHERE id = :id",
                                id = session.get('user_id'))
        
        # Grand total value (i.e, stocks' total value plus cash)                                
        total = cash[0]['cash']
        
        # Render template in such case ?
        if not owned:
            return render_template("index.html", owned=owned, cash=usd(cash[0]['cash']))
        
        # Assign current price to the stocks 
        for stock in owned:
            stockInfo = lookup(f"{stock['symbol']}")
            if not stockInfo:
                return apology("there's no stock with such symbol")
            stock['companyName'] = stockInfo['name']
            stock['latestPrice'] = stockInfo['price']
            
            total += stock['latestPrice']*stock['shares']
            
            # Show values in the USD format
            stock['usdLatestPrice'] = usd(stock['latestPrice'])
            stock['usdTotal'] = usd(stock['latestPrice']*stock['shares'])
        
        return render_template("index.html", owned=owned, cash=usd(cash[0]['cash']), total = usd(total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    
    if request.method == "POST":
       
        # Ensure username was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        # Ensure password was submitted
        elif not request.form.get("shares"):
            return apology("must provide a number of shares", 400)        
        
        # Ensure shares is a number
        try: 
            float(request.form.get("shares"))
        except ValueError:
            return apology("must provide a positive integer for shares input", 400)
        
        # Ensure shares is an integer
        if not (float(request.form.get("shares")).is_integer() and (float(request.form.get("shares")) > 0)):
            return apology("must provide a positive integer for shares input", 400)
            
        stockinfo = lookup(request.form.get("symbol"))
        userinfo = db.execute("SELECT * FROM users WHERE id = :id", id = session.get("user_id"))
        
        if not stockinfo:
            return apology("must provide a valid symbol")
            
        payment = stockinfo['price']*int(request.form.get("shares"))
        
         # Ensure the User has enough money
        if payment > userinfo[0]['cash']:
            return apology("not enough money on your account")
            
        # Add the symbol to stocksymbols table if it's not there yet
        symbolinfo = db.execute("SELECT * FROM stocksymbols WHERE symbol = :symbol",
                    symbol = request.form.get("symbol"))
                    
        if not symbolinfo:
            db.execute("INSERT INTO stocksymbols (symbol) VALUES(:symbol)",
                        symbol = request.form.get("symbol"))
            symbolinfo = db.execute("SELECT * FROM stocksymbols WHERE symbol = :symbol",
                                        symbol = request.form.get("symbol"))
        
        # Withdraw the payment from the User
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", 
                    cash = userinfo[0]['cash'] - payment, 
                    id = session.get("user_id"))
        
        # Add a new OR alter already existed owned set of stocks
        ownedinfo = db.execute( "SELECT * FROM owned WHERE userID = :userID AND symbolID = :symbolID",
                                userID = session.get('user_id'), 
                                symbolID = symbolinfo[0]['id'])
        
        if not ownedinfo: 
            db.execute("INSERT INTO owned (userID, symbolID, shares) VALUES(:userID, :symbolID, :shares)",
                        userID = session.get('user_id'),
                        symbolID = symbolinfo[0]['id'],
                        shares = request.form.get('shares'))
        else:
            db.execute("UPDATE owned SET shares = :shares WHERE userID = :userID AND symbolID = :symbolID",
                        shares = ownedinfo[0]['shares'] + int(request.form.get('shares')),
                        userID = session.get('user_id'), 
                        symbolID = symbolinfo[0]['id'])
        
        
        # Add a new transanction 
        db.execute( "INSERT INTO transactions (userID, symbolID, type, shares, price) VALUES(:userID, :symbolID, :type, :shares, :price)", 
                    userID = session.get("user_id"),
                    symbolID = symbolinfo[0]['id'],
                    type = 'p',
                    shares = int(request.form.get('shares')),
                    price = stockinfo['price'])
        
        # Redirect user to home page
        return redirect("/")
    
    # User reached route via GET (as by clicking a link or via redirect)                
    else:
        return render_template("buy.html")
    
    


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    if len(request.args.get("username")) < 1:
       return jsonify(False)
    
        
    names = db.execute("SELECT * FROM users WHERE username = :username",
                         username = request.args.get("username"))
    
    return jsonify(not names)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    
    transactions = db.execute("SELECT * FROM transactions JOIN stocksymbols ON transactions.symbolID = stocksymbols.id WHERE transactions.userID = :userID",
                                userID = session.get('user_id'))
    if not transactions:
        return apology("sorry, there're no transactions yet")
    
    for transaction in transactions:
        stockInfo = lookup(f"{transaction['symbol']}")
        transaction['companyName'] = stockInfo['name']
        transaction['usdPrice'] = usd(transaction['price'])
        transaction['usdTotal'] = usd(transaction['shares']*transaction['price'])
    
    
    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

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
        
        stockinfo = lookup(request.form.get("symbol"))
        if not stockinfo:
            return apology("sorry, there's no stock with such symbol")
            
        # Display the price in the USD format
        stockinfo['usdPrice'] = usd(stockinfo['price'])
        
        return render_template("quoted.html", stockinfo=stockinfo)
    
    # User reached route via GET (as by clicking a link or via redirect)    
    else: 
        return render_template("quote.html")
        
    return apology("TODO")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    
    # Forget any user_id
    session.clear()
    
    if request.method == "POST":
        
        # Ensure username was submitted 
        if not request.form.get("username"):
            return apology("must provide username", 400)
        
        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)
      
        # Ensure confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)
            
        # Ensure password matches confimation
        elif not request.form.get("password") == request.form.get("confirmation"):
            return apology("passwords must match", 400)
            
        # Ensure the provided username is unique 
        usernames = db.execute("SELECT * FROM users WHERE username = :username",
                                username = request.form.get("username"))
        
        if not len(usernames) == 0:
            return apology("username must be unique", 400)
        
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", 
                    username = request.form.get("username"),
                    hash = generate_password_hash(request.form.get("password")))
        
        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                            username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)
        
        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else: 
        return render_template("register.html")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    
    if request.method == "POST":
        
        # Ensure the User owns the stocks with such symbol
        # It has been already selected from owned ones 
        
        # Ensure request.from.get('shares') is a positive and not equal to 0
        if not float(request.form.get('shares')).is_integer and float(request.form.get('shares') > 0):
            return apology("shares must be a positive integer and not equalt to 0")
        
        # Ensure the User owns enough shares to sell
        currentShares = db.execute("SELECT shares FROM owned JOIN stocksymbols ON owned.symbolID = stocksymbols.id WHERE owned.userID = :userID AND stocksymbols.symbol = :symbol",
                                    userID = session.get('user_id'),
                                    symbol = request.form.get('symbol'))
                                    

        # List or one int ? 
        if currentShares[0]['shares'] < int(request.form.get('shares')):
            return apology("sorry, you don't have so many shares")
        
        # Look up the surrent price of the stocks
        stockInfo = lookup(f"{request.form.get('symbol')}")
        symbolID = db.execute("SELECT id FROM stocksymbols WHERE symbol = :symbol", symbol = request.form.get('symbol'))[0]['id']
        
        # Make changes in owned table
        if currentShares[0]['shares'] == int(request.form.get('shares')):
            # DELETE the stock from owned 
            db.execute("DELETE FROM owned WHERE userID = :userID AND symbolID = :symbolID",
                        userID = session.get('user_id'),
                        symbolID = symbolID)
        else:
            # UPDATE
            db.execute("UPDATE owned SET shares = shares - :soldShares WHERE owned.userID = :userID AND symbolID = :symbolID",
                        soldShares = int(request.form.get('shares')),
                        userID = session.get('user_id'),
                        symbolID = symbolID)
        
        
        # Transfer the money to the User
        db.execute("UPDATE users SET cash = cash + :profit WHERE id = :id",
                    profit = stockInfo['price']*int(request.form.get('shares')),
                    id = session.get('user_id'))
        
        # Add a new transanction 
        db.execute( "INSERT INTO transactions (userID, symbolID, type, shares, price) VALUES(:userID, :symbolID, :type, :shares, :price)", 
                    userID = session.get("user_id"),
                    symbolID = symbolID,
                    type = 's',
                    shares = int(request.form.get('shares')),
                    price = stockInfo['price'])        
        
        # Redirect user to home page
        return redirect("/")
    
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        
        owned = db.execute("SELECT * FROM owned JOIN stocksymbols ON owned.symbolID = stocksymbols.id WHERE owned.userID = :userID",
                            userID = session.get('user_id'))
                            
        return render_template("sell.html", owned=owned)
    

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)