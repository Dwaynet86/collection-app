"""Development entry point: `python run.py`. Use gunicorn in production."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
