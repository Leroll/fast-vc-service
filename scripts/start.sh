# if server is already running, 
if pgrep -f "python fast_vc_service/app.py" > /dev/null; then
    echo "Application is already running."
    exit 0
fi

# start the applicatioan
nohup python fast_vc_service/app.py > nohup.log 2>&1 &
if [ $? -eq 0 ]; then
    echo "Application started successfully."
else
    echo "Failed to start the application."
fi