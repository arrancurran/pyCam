#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify
from flask_socketio import SocketIO
from pypylon import pylon
from PIL import Image
import cv2, threading, time, os, shutil, base64, subprocess

app = Flask(__name__)
socketio = SocketIO(app)

# Initialize the camera
camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
camera.Open()
camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

# Global variable to store the latest frame
latest_frame = None
capture_thread = None
stream_running = True
progress = 0

# 
# STREAMING
# 
# while stream_running is true, capture frames from the camera and emit them to the client
# 
def stream():
    global latest_frame, stream_running
    while stream_running and camera.IsGrabbing():
        grabResult = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if grabResult.GrabSucceeded():
            img = grabResult.Array
            # Reduce resolution for streaming
            img_resized = cv2.resize(img, (640, 480))
            ret, buffer = cv2.imencode('.jpg', img_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            latest_frame = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('frame', latest_frame)
        grabResult.Release()
        time.sleep(0.1)  # Adjust the sleep time to control the frame rate


# Start the frame capture thread
capture_thread = threading.Thread(target=stream)
capture_thread.daemon = True
capture_thread.start()

@app.route('/')
def index():
    # Get the current exposure time and push to the client
    exposure_time = camera.ExposureTime.GetValue()
    return render_template('index.html', exposure_time=exposure_time)

@app.route('/set_exposure', methods=['POST'])
def set_exposure():
    exposure_time = float(request.form['exposure_time'])
    camera.ExposureTime.SetValue(exposure_time)
    return redirect(url_for('index'))

def save(num_frames, timestep):
    global progress
    save_path = '/mnt/usb/captured_images'  # Change the save path to the USB disk
    os.makedirs(save_path, exist_ok=True)
    # Emit an event to show the progress div
    socketio.emit('show_progress')
    for i in range(num_frames):
        iteration_start_time = time.time()
        
        progress = int( (i + 1) / num_frames * 100)
        socketio.emit('progress', {'progress': progress})
        time.sleep(timestep)
        grabResult = camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if grabResult.GrabSucceeded():
            img = grabResult.Array
            img_pil = Image.fromarray(img)
            img_pil.save(os.path.join(save_path, f'image_{i+1}.tiff'))
            grabResult.Release()
        
        iteration_end_time = time.time()
        iteration_duration = iteration_end_time - iteration_start_time
        sleep_time = max(0, timestep - iteration_duration)
        time.sleep(sleep_time)
        
    zip_path = '/mnt/usb/captured_images.zip'  # Change the zip path to the USB disk
    shutil.make_archive('/mnt/usb/captured_images', 'zip', save_path)
    # Emit an event to hide the progress div
    socketio.emit('capture_complete')

@app.route('/start_acquisition', methods=['POST'])
def start_acquisition():
    num_frames = int(request.form['num_frames'])
    timestep = float(request.form['timestep'])
    
    capture_thread = threading.Thread(target=save, args=(num_frames, timestep))
    capture_thread.start()

    return redirect(url_for('index'))

@app.route('/download_images')
def download_images():
    return send_file('/mnt/usb/captured_images.zip', as_attachment=True)

@app.route('/umount_usb', methods=['POST'])
def umount_usb():
    try:
        result = subprocess.run(['sudo', 'umount', '/mnt/usb'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return jsonify({'status': 'success', 'message': result.stdout.decode('utf-8')})
    except subprocess.CalledProcessError as e:
        return jsonify({'status': 'error', 'message': e.stderr.decode('utf-8') + ' Try restarting the Raspberry Pi.'}), 500

if __name__ == '__main__':
    # socketio.run(app, host='0.0.0.0', port=5000)
    socketio.run(app, host='192.168.10.1', port=5000, allow_unsafe_werkzeug=True)
