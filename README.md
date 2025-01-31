### Running

Running involves 3 parts

1. The server: `cd backend && uvicorn fast_api_test:app --reload`
2. Redis: `redis-server`
3. The front-end: `cd frontend && npm start`

This repo includes the following tmux script that will run all 3 of these for you: `./run-dev.sh`

This script assumes you already have your pipenv shell activated and that you have the following set in your .tmux.conf:
```
set -g base-index 1
setw -g pane-base-index 1
```
