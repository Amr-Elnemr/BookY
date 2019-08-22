import os, requests

from flask import Flask, session, render_template, request, redirect, url_for
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker
from flask_bcrypt import Bcrypt
from secret import gr_secret
import json

app = Flask(__name__)

# Check for environment variable
# if not os.getenv("DATABASE_URL"):
#     raise RuntimeError("DATABASE_URL is not set")
DATABASE_URL = "postgres://tjdejxqxhkqllq:ddda86aa7f090ee5e35936952bb8a3df06444dd4f26e0f004da3c79f34976c90@ec2-50-19-221-38.compute-1.amazonaws.com:5432/da1uqr99dooflc"

# Configure session to use filesystem
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
# engine = create_engine(os.getenv("DATABASE_URL"))
engine = create_engine(DATABASE_URL)
db = scoped_session(sessionmaker(bind=engine))

# Configure Password hashing
My_bcrypt = Bcrypt(app)


@app.route("/")
def index():
    if session.get("user") is None:
        return render_template("Registration.html")
    else:
        return redirect(url_for('home'))


@app.route("/Register", methods = ["GET","POST"])
def register():
    if (request.method == "GET"):
        return render_template("Registration.html")

    username = request.form.get("username")
    password1 = request.form.get("psw")
    password2 = request.form.get("psw-repeat")
    username_srch = db.execute("SELECT user_id FROM users WHERE name = :name", {"name":username}).fetchone()
    if(username_srch != None):
        existing_name = True
        return render_template("Registration.html", existing_name=existing_name)

    elif(password1 != password2):
        password_mismatch = True
        return render_template("Registration.html", password_mismatch=password_mismatch)

    else:
        pw_hash = My_bcrypt.generate_password_hash(password1).decode('utf-8')
        db.execute("INSERT INTO users (name, password) VALUES (:username, :password)", {"username":username, "password":pw_hash})
        db.commit()
        return f"<h2>Welcome! {username}. You have registered Successfully</h2><a href='http://127.0.0.1:5000/login'>Login</a>"

@app.route("/login")
def login():
    if session.get("user") is None:
        return render_template("Login.html")
    else:
        return redirect(url_for('home'))

@app.route('/Home', methods = ["GET", "POST"])
def home():
    no_results = False
    if (request.method == "GET"):
        if session.get("user") is None:
            return redirect(url_for('login'))
        else:
            return render_template("Home.html", no_results = no_results)

    if session.get("user") is not None:
        search_for = request.form.get("keyword").strip()
        search_by = request.form.get("search_criteria")
        srch_results = db.execute("SELECT * FROM books where lower("+search_by+") LIKE lower(concat('%',:search_for,'%'));", {"search_for": search_for}).fetchall()
        if (len(srch_results)==0):
            no_results = True
            return render_template("Home.html", no_results=no_results, search_for = search_for, search_by = search_by)
        results_found = True
        return render_template("Home.html", results_found = results_found, srch_results = srch_results, search_for = search_for, search_by = search_by)
    else:
        username = request.form.get("username")
        password = request.form.get("psw")
        user_srch = db.execute("SELECT * FROM users WHERE name = :name" , {"name": username}).fetchone()
        if (user_srch == None):
            no_user = True
            return render_template("Login.html", no_user = no_user)
        elif(My_bcrypt.check_password_hash(user_srch.password, password) == False):
            wrong_pw = True
            return render_template("Login.html", wrong_pw = wrong_pw)
        else:
            session['user'] = user_srch
            return render_template("Home.html")

@app.route("/Logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/Book/<string:isbn>")
def book(isbn):
    if session.get("user") is None:
        return redirect(url_for('login'))

    target_Book = db.execute("SELECT * from books where isbn = :isbn", {"isbn":isbn}).fetchone()
    if(target_Book == None):
        return "Book not found!!"
    Book=target_Book.title
    Author = target_Book.author
    Publication_year=target_Book.pub_yr
    ISBN=isbn
    #API(GoodReads):
    res = requests.get("https://www.goodreads.com/book/review_counts.json",params={"key": gr_secret, "isbns": isbn})
    gr_eating=res.json()['books'][0]['average_rating']
    NoOfRatings=res.json()['books'][0]['work_ratings_count']
    #BookY rating
    rev_permission = True
    tot_rate = 0
    booky_reviews = db.execute("SELECT users.user_id, users.name, reviews.rating, reviews.comment FROM users JOIN reviews ON users.user_id = reviews.user_id WHERE r_isbn = :r_isbn", {"r_isbn":isbn}).fetchall()
    if len(booky_reviews) == 0:
        booky_reviews = None;
        our_rate = "_ "
    else:
        for rev in booky_reviews:
            if rev.user_id == session['user'].user_id: rev_permission = False
            tot_rate+=int(rev.rating)
        our_rate = tot_rate/len(booky_reviews)  # calculated
    return render_template("Book.html",Book=Book, Author=Author, Publication_year=Publication_year,ISBN=ISBN, gr_eating=gr_eating, NoOfRatings=NoOfRatings, our_rate=our_rate, booky_reviews=booky_reviews, rev_permission=rev_permission)

@app.route("/RevBook/<string:isbn>", methods = ["POST"])
def revBook(isbn):
    if session.get("user") is None:
        return redirect(url_for('login'))

    user_id = session['user'].user_id
    rating = request.form.get('rating')
    comment = request.form.get('comment')
    db.execute("INSERT INTO reviews (r_isbn, user_id, rating, comment) VALUES (:r_isbn, :user_id, :rating, :comment)",{"r_isbn": isbn, "user_id": user_id, "rating": rating, "comment": comment})
    db.commit()

    return redirect(url_for('book', isbn=isbn))

@app.route("/api/<string:isbn>")
def myapi(isbn):
    mybk = db.execute("SELECT books.isbn, books.title, books.author, books.pub_yr, count(*) FROM books LEFT JOIN reviews ON books.isbn = reviews.r_isbn where isbn=:isbn GROUP BY books.isbn;", {"isbn":isbn}).fetchone()
    if(mybk == None):
        return "<h1>404</h1>"
    bkRatings = db.execute("SELECT rating from reviews where r_isbn=:isbn", {"isbn":isbn}).fetchall()
    if (len(bkRatings) != 0):
        sum = 0
        for r in bkRatings:
            sum+=int(r.rating)
        avgRat = sum/len(bkRatings)
        rev_count  = mybk.count
    else:
        avgRat=0
        rev_count=0

    myout = {"title": mybk.title, "author": mybk.author, "year": mybk.pub_yr, "isbn": mybk.isbn, "review_count": rev_count,"average_score": avgRat}
    return json.dumps(myout)