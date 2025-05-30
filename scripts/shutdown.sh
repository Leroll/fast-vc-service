# shutdown the server
PIDS=$(pgrep -f "python app.py")
if [ -n "$PIDS" ]; then
    echo "Found processes: $PIDS"
    # Try graceful shutdown first
    kill -15 $PIDS
    echo "Attempting to stop the application gracefully..."
    sleep 5
    # Force kill if still running
    if pgrep -f "python app.py" > /dev/null; then
        echo "Application did not stop gracefully, forcing shutdown..."
        kill -9 $PIDS
    fi
    echo "Application stopped successfully."
else
    echo "No application processes found."
fi