
from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
from PIL import Image
import shutil, cv2, base64, os, time, threading

app = Flask(__name__)
socketio = SocketIO(app)

# Configuration setting to choose between 'pylon' and 'webcam'
CAMERA_TYPE = 'webcam'  # Change to 'webcam' to use the in-built webcam

class Camera:
    def __init__(self, camera_type):
        self.camera_type = camera_type
        if camera_type == 'pylon':
            from pypylon import pylon
            self.camera = pylon.InstantCamera(pylon.TlFactory.GetInstance().CreateFirstDevice())
            self.camera.Open()
        elif camera_type == 'webcam':
            self.camera = cv2.VideoCapture(0)
        else:
            raise ValueError("Unsupported camera type")

    def set_exposure(self, exposure_time):
        if self.camera_type == 'pylon':
            self.camera.ExposureTime.SetValue(exposure_time)
        elif self.camera_type == 'webcam':
            self.camera.set(cv2.CAP_PROP_EXPOSURE, exposure_time)

    def get_exposure(self):
        if self.camera_type == 'pylon':
            return self.camera.ExposureTime.GetValue()
        elif self.camera_type == 'webcam':
            return self.camera.get(cv2.CAP_PROP_EXPOSURE)

    def capture_image(self):
        if self.camera_type == 'pylon':
            grabResult = self.camera.RetrieveResult(5000, pylon.TimeoutHandling_ThrowException)
            if grabResult.GrabSucceeded():
                img = grabResult.Array
                grabResult.Release()
                return img
        elif self.camera_type == 'webcam':
            ret, frame = self.camera.read()
            if ret:
                return frame

camera = Camera(CAMERA_TYPE)

# Global variable to store the latest frame
latest_frame = None
capture_thread = None
capture_thread_running = True

def capture_frames():
    global latest_frame

    # Capture the first frame to get the original dimensions
    img = camera.capture_image()
    if img is not None:
        height, width = img.shape[:2]
        aspect_ratio = width / height

        # Determine new dimensions while maintaining aspect ratio
        desired_width = 640
        desired_height = 480
        if width > height:
            new_width = desired_width
            new_height = int(new_width / aspect_ratio)
        else:
            new_height = desired_height
            new_width = int(new_height * aspect_ratio)

    while capture_thread_running:
        img = camera.capture_image()
        if img is not None:
            # Resize the image using the pre-calculated dimensions
            img_resized = cv2.resize(img, (new_width, new_height))
            _, buffer = cv2.imencode('.jpg', img_resized, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            latest_frame = base64.b64encode(buffer).decode('utf-8')
            socketio.emit('frame', latest_frame)
        time.sleep(0.05)

# Ensure capture_thread is started somewhere in your code
capture_thread_running = True
capture_thread = threading.Thread(target=capture_frames)
capture_thread.daemon = True
capture_thread.start()

@app.route('/')
def index():
    exposure_time = camera.get_exposure()
    return render_template('index.html', exposure_time=exposure_time)

@app.route('/set_exposure', methods=['POST'])
def set_exposure():
    exposure_time = float(request.form['exposure_time'])
    camera.set_exposure(exposure_time)
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

    # Capture images
    for i in range(num_frames):
        img = camera.capture_image()
        if img is not None:
            img_pil = Image.fromarray(img)
            img_pil.save(os.path.join(save_path, f'image_{i+1}.tiff'))
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
    socketio.run(app, host='0.0.0.0', port=49152)