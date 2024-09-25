#!/usr/bin/env python3
from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_socketio import SocketIO
from pypylon import pylon
from PIL import Image
import cv2, threading, time, os, shutil, base64
from threading import Lock

app = Flask(__name__)
socketio = SocketIO(app)

# Lock for camera access
camera_lock = Lock()

class CameraSingleton:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            with camera_lock:
                if cls._instance is None:
                    cls._instance = super(CameraSingleton, cls).__new__(cls)
                    cls._instance.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
                    cls._instance.camera.Open()
                    cls._instance.camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        return cls._instance

# Global variable to store the latest frame
latest_frame = None
capture_thread = None
capture_thread_running = True

def capture_frames():
    global latest_frame, capture_thread_running
    camera_instance = CameraSingleton().camera
    while capture_thread_running and camera_instance.IsGrabbing():
        grabResult = camera_instance.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if grabResult.GrabSucceeded():
            img = grabResult.Array
            # Resize the image to reduce resolution for streaming
            img_resized = cv2.resize(img, (640, 480))
            ret, buffer = cv2.imencode('.jpg', img_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            latest_frame = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('frame', latest_frame)
        grabResult.Release()
        time.sleep(0.1)  # Adjust the sleep time to control the frame rate

# Start the frame capture thread
capture_thread = threading.Thread(target=capture_frames)
capture_thread.daemon = True
capture_thread.start()

@app.route('/')
def index():
    camera_instance = CameraSingleton().camera
    # Get the current exposure time
    exposure_time = camera_instance.ExposureTime.GetValue()
    return render_template('index.html', exposure_time=exposure_time)

@app.route('/set_exposure', methods=['POST'])
def set_exposure():
    exposure_time = float(request.form['exposure_time'])
    camera_instance = CameraSingleton().camera
    camera_instance.ExposureTime.SetValue(exposure_time)
    return redirect(url_for('index'))

@app.route('/capture_images', methods=['POST'])
def capture_images():
    global capture_thread_running, capture_thread
    num_frames = int(request.form['num_frames'])
    timestep = float(request.form['timestep'])
    save_path = 'captured_images'
    os.makedirs(save_path, exist_ok=True)

    # Stop the capture thread
    capture_thread_running = False
    capture_thread.join()

    camera_instance = CameraSingleton().camera

    # Capture images
    for i in range(num_frames):
        grabResult = camera_instance.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
        if grabResult.GrabSucceeded():
            img = grabResult.Array
            img_pil = Image.fromarray(img)
            img_pil.save(os.path.join(save_path, f'image_{i+1}.tiff'))
            grabResult.Release()
        time.sleep(timestep)

    # Restart the capture thread
    capture_thread_running = True
    capture_thread = threading.Thread(target=capture_frames)
    capture_thread.daemon = True
    capture_thread.start()

    # Create a zip file of the captured images
    zip_path = 'captured_images.zip'
    shutil.make_archive('captured_images', 'zip', save_path)

    return redirect(url_for('index'))

@app.route('/download_images')
def download_images():
    return send_file('captured_images.zip', as_attachment=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)