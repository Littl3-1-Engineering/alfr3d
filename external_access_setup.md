# External Access Setup - Remaining Tasks

## What I've Implemented
✅ **Updated Kubernetes configs:**
- Changed `service-frontend` from LoadBalancer to NodePort (port 30080)
- Updated ingress host from `alfr3d.local` to `yourdomain.com`
- Created Nginx reverse proxy config (`nginx-alfr3d.conf`)

## What You Need to Do

### 1. **Start Your Kubernetes Cluster**
```bash
minikube start --driver=docker
minikube addons enable ingress
```

### 2. **Deploy Updated Configs**
```bash
kubectl apply -f k8s/
```

### 3. **Get Your Minikube IP**
```bash
minikube ip
# Note this IP - you'll need it for Nginx config
```

### 4. **Update Nginx Config**
Edit `nginx-alfr3d.conf`:
- Replace `yourdomain.com` with your actual domain
- Replace `localhost:30080` with `<minikube-ip>:30080`

### 5. **Install and Configure Nginx**
```bash
# Install Nginx (Ubuntu/Debian)
sudo apt update && sudo apt install nginx

# Copy config
sudo cp nginx-alfr3d.conf /etc/nginx/sites-available/alfr3d
sudo ln -s /etc/nginx/sites-available/alfr3d /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 6. **DNS Configuration**
- Point your domain's A record to your **public IP address**
- If you don't have a static IP, use dynamic DNS (No-IP, DuckDNS, etc.)

### 7. **Router Port Forwarding**
Forward these ports to your machine's internal IP:
- **Port 80** (HTTP) → Your machine IP
- **Port 443** (HTTPS) → Your machine IP (for SSL later)

### 8. **Test Access**
```bash
# Test locally
curl http://localhost

# Test from external network (mobile data)
curl http://yourdomain.com
```

### 9. **Optional: SSL Setup (Recommended)**
```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d yourdomain.com

# Uncomment HTTPS section in nginx-alfr3d.conf
# Reload Nginx
sudo systemctl reload nginx
```

## Troubleshooting
- **Firewall issues:** `sudo ufw allow 80` and `sudo ufw allow 443`
- **Nginx logs:** `sudo journalctl -u nginx`
- **Kubernetes logs:** `kubectl logs -f deployment/service-frontend`
- **Minikube service:** `minikube service service-frontend --url`

## Security Notes
- SSL is strongly recommended for external access
- Consider adding basic auth if your app doesn't have authentication
- Keep your system and Nginx updated

Once you complete these steps, your ALFR3D frontend will be accessible from outside your LAN at `http://yourdomain.com` (or `https://yourdomain.com` with SSL).
