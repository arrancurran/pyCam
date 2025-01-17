#!/bin/bash
# TODO: Setup variables for sys name, server address, user name and group name

# Update and upgrade the system
sudo apt-get update && sudo apt-get -y upgrade

# Install the following packages:
# - libhdf5-dev: Development files for the Hierarchical Data Format 5 (HDF5) library
# - nginx: A high-performance HTTP server and reverse proxy, as well as an IMAP/POP3 proxy server.
# - libgl1-mesa-glx: A free implementation of the OpenGL API, which provides graphics rendering capabilities.
sudo apt-get install -y libhdf5-dev nginx libgl1-mesa-glx python3-dev git acl

# Get the repo and create a virtual environment
cd ~/
git clone https://github.com/arrancurran/pyCam.git
python3 -m venv pyCam-venv
# Set up the virtual environment to activate on boot
echo "source ~/pyCam-venv/bin/activate" >> ~/.bashrc
source ~/.bashrc

# Install necessary Python packages into our pyCam-venv virtual environment
pip install pypylon flask flask-socketio opencv-python h5py Pillow

# Download and install the Pylon software
mkdir -p ~/Downloads && cd ~/Downloads
wget https://www2.baslerweb.com/media/downloads/software/pylon_software/pylon-7.5.0.15658-linux-aarch64_debs.tar.gz
tar -xzf pylon-7.5.0.15658-linux-aarch64_debs.tar.gz
sudo dpkg -i pylon_7.5.0.15658-deb0_arm64.deb
cd ~/ && rm -rf ~/Downloads
# TODO: Delete the tar.gz and deb files after installation

# Set environment variables for Pylon
export PYLON_ROOT=/opt/pylon
export GENICAM_ROOT_V3_1=$PYLON_ROOT/genicam
export GENICAM_CACHE=$HOME/.GenICam_XMLCache
export LD_LIBRARY_PATH=$PYLON_ROOT/lib:$LD_LIBRARY_PATH
export PYTHONPATH=$PYLON_ROOT/lib:$PYTHONPATH
export PATH=$PYLON_ROOT/bin:$PATH

source ~/.bashrc

# Configure Nginx
sudo mkdir -p /var/www/pyCam

# Create Nginx configuration file
sudo bash -c 'cat > /etc/nginx/sites-available/pyCam <<EOF
server {
    listen 80;
    server_name microscope-colloid.local;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }

    location /static {
        alias /home/pcsm-scope/pyCam/static;
    }
}
EOF'

# Enable the new site and restart Nginx
sudo ln -s /etc/nginx/sites-available/pyCam /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
sudo chown -R www-data:www-data /var/www/pyCam
sudo chmod -R 755 /var/www/pyCam

#  Enable the camera app to run at start/reboot by creating a service file

SERVICE_FILE_CONTENT="[Unit]
Description=pyCam
After=network.target

[Service]
ExecStart=/home/pcsm-scope/pyCam-venv/bin/python /home/pcsm-scope/pyCam/main.py
WorkingDirectory=/home/pcsm-scope/pyCam
StandardOutput=inherit
StandardError=inherit
Restart=always
User=pcsm-scope
Environment="PATH=/home/pcsm-scope/pyCam-venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[Install]
WantedBy=multi-user.target"

# Create a service file
echo "$SERVICE_FILE_CONTENT" | sudo tee /etc/systemd/system/pyCam.service > /dev/null

# Reload systemd to recognize the new service
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable pyCam.service

# Start the service immediately
sudo systemctl start pyCam.service

# TODO: Check the service is running
# Check the status of the service
# sudo systemctl status pyCam.service

# Setting up auto mount for external USB drive
# Create a directory to mount the USB drive
sudo mkdir -p /mnt/usb

# Add the USB drive to /etc/fstab for auto-mounting
# Replace 'UUID=your-uuid' with the actual UUID of your USB drive
echo "UUID=95EE-C4CA /mnt/usb vfat defaults,auto,users,rw,nofail,noatime,uid=pcsm-scope,gid=pcsm-scope 0 0" | sudo tee -a /etc/fstab

# Mount the USB drive
sudo mount -a

# Ensure the user running the script has write permissions
sudo chown -R pcsm-scope:pcsm-scope /mnt/usb
sudo chmod -R 775 /mnt/usb

#sudo blkid /dev/sda1
#UUID=95EE-C4CA /mnt/usb vfat defaults,auto,users,rw,nofail,noatime