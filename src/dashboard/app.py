"""Flask entry point. Run locally:  python -m src.dashboard.app
On the Pi:  python -m src.dashboard.app --host=0.0.0.0
"""
import argparse

from flask import Flask

from src.dashboard.routes import bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = "health-agent-local"  # flash messages only; home-network app
    app.register_blueprint(bp)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    create_app().run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
