.PHONY: run demo test check-js

run:
	python3 app.py

demo:
	python3 seed_demo.py
	python3 app.py --db demo.sqlite3

test:
	python3 -m unittest -v

check-js:
	node --check static/app.js
	node --check static/employee.js
