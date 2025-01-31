tmux new-session -s artist_explorer -d
tmux split-window -h
tmux split-window -v
tmux resize-pane -t 1 -x 80%
tmux send-keys -t 1 'cd backend && uvicorn fast_api_test:app --reload' C-m
tmux send-keys -t 2 'cd frontend && npm start' C-m
tmux send-keys -t 3 'redis-server' C-m
tmux attach-session -t artist_explorer

tmux bind-key -t artist_explorer K \
    send-keys C-c \; \
    send-keys -t 1 C-c \; \
    send-keys -t 2 C-c \; \
    send-keys -t 3 C-c \; \
    run-shell "pkill redis-server" \; \
    run-shell "pkill uvicorn" \; \
    run-shell "pkill node" \; \
    kill-session
