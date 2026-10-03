"""python -m pipeline  -  serve the app on http://127.0.0.1:8000"""
import argparse
import os

import uvicorn

from .api import create_app

parser = argparse.ArgumentParser(prog="python -m pipeline", description=__doc__)
parser.add_argument("--db", default=os.environ.get("PIPELINE_DB", "pipeline.db"), help="SQLite file (default: pipeline.db)")
parser.add_argument("--port", type=int, default=8000)
args = parser.parse_args()

uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
