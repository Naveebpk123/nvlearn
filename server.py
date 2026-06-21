from flask import Flask, render_template, request, redirect, url_for, flash

app=Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/notes')
def notes():
    return render_template('notes.html')

if __name__ == "__main__":
    app.run(debug=True)