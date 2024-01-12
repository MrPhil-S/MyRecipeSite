from myrecipes import app

if __name__ == "__main__":
    #app.run(debug=True)
         app.run(host="0.0.0.0", port=8080, debug=True)
     #app.run()

#to start dubug in cmd:
#set FLASK_DEBUG=1
