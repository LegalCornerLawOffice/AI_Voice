# Deployment Guide

## Railway Deployment (Easiest for Development)

### 1. Install Railway CLI
```bash
npm install -g @railway/cli
# or
brew install railway
```

### 2. Login and Initialize
```bash
railway login
cd AI_Voice
railway init
```

### 3. Add Redis
```bash
railway add --plugin redis
```

### 4. Set Environment Variables
```bash
railway variables set DEEPGRAM_API_KEY=your_key
railway variables set AWS_ACCESS_KEY_ID=your_key
railway variables set AWS_SECRET_ACCESS_KEY=your_secret
railway variables set AWS_REGION=us-east-1
railway variables set ENVIRONMENT=production
```

### 5. Deploy
```bash
railway up
```

Your app will be live at a Railway URL!

---

## AWS Deployment (Production)

### Infrastructure Setup

#### 1. VPC & Security Groups
```bash
# Create VPC
aws ec2 create-vpc --cidr-block 10.0.0.0/16

# Create subnet
aws ec2 create-subnet --vpc-id vpc-xxx --cidr-block 10.0.1.0/24

# Create security group
aws ec2 create-security-group --group-name ai-voice-sg --vpc-id vpc-xxx

# Allow HTTPS
aws ec2 authorize-security-group-ingress --group-id sg-xxx \
    --protocol tcp --port 443 --cidr 0.0.0.0/0

# Allow HTTP (for dev)
aws ec2 authorize-security-group-ingress --group-id sg-xxx \
    --protocol tcp --port 80 --cidr 0.0.0.0/0

# Allow SSH (for admin)
aws ec2 authorize-security-group-ingress --group-id sg-xxx \
    --protocol tcp --port 22 --cidr YOUR_IP/32
```

#### 2. Launch EC2 Instance
```bash
# t3.medium recommended (2 vCPU, 4GB RAM)
aws ec2 run-instances \
    --image-id ami-xxxxxxxxx \  # Ubuntu 22.04 LTS
    --instance-type t3.medium \
    --key-name your-key-pair \
    --security-group-ids sg-xxx \
    --subnet-id subnet-xxx \
    --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=ai-voice-server}]'
```

#### 3. Setup RDS PostgreSQL
```bash
aws rds create-db-instance \
    --db-instance-identifier ai-voice-db \
    --db-instance-class db.t3.small \
    --engine postgres \
    --master-username admin \
    --master-user-password YOUR_PASSWORD \
    --allocated-storage 20 \
    --vpc-security-group-ids sg-xxx \
    --db-subnet-group-name your-subnet-group \
    --backup-retention-period 7 \
    --storage-encrypted
```

#### 4. Setup ElastiCache Redis
```bash
aws elasticache create-cache-cluster \
    --cache-cluster-id ai-voice-redis \
    --cache-node-type cache.t3.micro \
    --engine redis \
    --num-cache-nodes 1 \
    --security-group-ids sg-xxx
```

### Application Deployment

#### 1. SSH into EC2
```bash
ssh -i your-key.pem ubuntu@ec2-xxx.compute.amazonaws.com
```

#### 2. Install Dependencies
```bash
sudo apt update
sudo apt install -y python3.10 python3-pip python3-venv nginx

# Clone or upload your code
git clone your-repo
cd AI_Voice

# Create virtual environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### 3. Configure Environment
```bash
# Create .env file
nano .env

# Add production values:
DEEPGRAM_API_KEY=xxx
AWS_ACCESS_KEY_ID=xxx
AWS_SECRET_ACCESS_KEY=xxx
AWS_REGION=us-east-1
DATABASE_URL=postgresql+asyncpg://admin:password@your-rds-endpoint:5432/ai_voice
REDIS_URL=redis://your-elasticache-endpoint:6379
ENVIRONMENT=production
HOST=0.0.0.0
PORT=8000
```

#### 4. Setup Systemd Service
```bash
sudo nano /etc/systemd/system/ai-voice.service
```

```ini
[Unit]
Description=AI Voice Intake System
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/AI_Voice
Environment="PATH=/home/ubuntu/AI_Voice/venv/bin"
ExecStart=/home/ubuntu/AI_Voice/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable ai-voice
sudo systemctl start ai-voice
sudo systemctl status ai-voice
```

#### 5. Configure Nginx
```bash
sudo nano /etc/nginx/sites-available/ai-voice
```

```nginx
upstream ai_voice {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://ai_voice;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/ai-voice /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

#### 6. Setup SSL with Let's Encrypt
```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Monitoring

#### CloudWatch Logs
```bash
# Install CloudWatch agent
wget https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
sudo dpkg -i amazon-cloudwatch-agent.deb

# Configure to send logs
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
    -a fetch-config \
    -m ec2 \
    -s -c file:/opt/aws/amazon-cloudwatch-agent/etc/config.json
```

#### Application Logs
```bash
# View logs
sudo journalctl -u ai-voice -f

# Application logs
tail -f /home/ubuntu/AI_Voice/logs/ai_voice.log
```

---

## Docker Deployment (Alternative)

### 1. Create Dockerfile
```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "main.py"]
```

### 2. Create docker-compose.yml
```yaml
version: '3.8'

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DEEPGRAM_API_KEY=${DEEPGRAM_API_KEY}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
      - AWS_REGION=${AWS_REGION}
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=${DATABASE_URL}
    depends_on:
      - redis
    restart: unless-stopped

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
```

### 3. Deploy
```bash
docker-compose up -d
```

---

## Health Checks

### Application Health
```bash
curl http://your-domain.com/health
```

Expected response:
```json
{
  "status": "healthy",
  "environment": "production",
  "version": "0.1.0"
}
```

### Monitoring Endpoints
- `/health` - Health check
- `/metrics` - Prometheus metrics (TODO)

---

## Backup & Recovery

### Database Backups
```bash
# Automated with RDS (7 day retention configured)
# Manual backup:
aws rds create-db-snapshot \
    --db-instance-identifier ai-voice-db \
    --db-snapshot-identifier ai-voice-backup-$(date +%Y%m%d)
```

### Redis Backups
```bash
# ElastiCache automatic backups configured
# Manual snapshot:
aws elasticache create-snapshot \
    --cache-cluster-id ai-voice-redis \
    --snapshot-name ai-voice-redis-backup-$(date +%Y%m%d)
```

---

## Scaling

### Horizontal Scaling (Multiple Servers)

#### 1. Create Application Load Balancer
```bash
aws elbv2 create-load-balancer \
    --name ai-voice-lb \
    --subnets subnet-xxx subnet-yyy \
    --security-groups sg-xxx
```

#### 2. Create Target Group
```bash
aws elbv2 create-target-group \
    --name ai-voice-targets \
    --protocol HTTP \
    --port 8000 \
    --vpc-id vpc-xxx
```

#### 3. Launch Auto Scaling Group
```bash
# Create launch template
aws ec2 create-launch-template \
    --launch-template-name ai-voice-template \
    --version-description "AI Voice v1" \
    --launch-template-data file://launch-template.json

# Create auto scaling group
aws autoscaling create-auto-scaling-group \
    --auto-scaling-group-name ai-voice-asg \
    --launch-template LaunchTemplateName=ai-voice-template \
    --min-size 2 \
    --max-size 10 \
    --desired-capacity 2 \
    --target-group-arns arn:aws:elasticloadbalancing:...
```

---

## Troubleshooting

### Check Service Status
```bash
sudo systemctl status ai-voice
```

### View Logs
```bash
# Application logs
sudo journalctl -u ai-voice -n 100 -f

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Test WebSocket
```bash
# Install wscat
npm install -g wscat

# Test WebSocket endpoint
wscat -c ws://your-domain.com/ws/call
```

### Database Connection
```bash
# Test PostgreSQL connection
psql -h your-rds-endpoint -U admin -d ai_voice
```

### Redis Connection
```bash
# Test Redis connection
redis-cli -h your-elasticache-endpoint ping
```

---

## Security Hardening

### SSL/TLS
- ✅ Force HTTPS with Nginx redirect
- ✅ Use Let's Encrypt for certificates
- ✅ Enable HSTS headers

### API Keys
- ✅ Store in environment variables
- ✅ Never commit to git
- ✅ Rotate regularly

### Network
- ✅ Security groups restrict access
- ✅ Private subnets for database/Redis
- ✅ VPC with network ACLs

### Application
- ✅ Input validation
- ✅ Rate limiting (TODO)
- ✅ CORS configuration
- ✅ Error handling without exposing internals

---

## HIPAA Compliance Checklist

- [ ] Sign AWS BAA
- [ ] Sign Deepgram BAA  
- [ ] Enable encryption at rest (RDS, ElastiCache)
- [ ] Enable encryption in transit (TLS everywhere)
- [ ] Configure access logging (CloudTrail)
- [ ] Set up audit logs (CloudWatch)
- [ ] Implement data retention policies
- [ ] Configure automatic backups
- [ ] Document security procedures
- [ ] Conduct security audit

---

## Cost Optimization

### Development
- Use AWS free tier where possible
- Use t3.micro for testing
- Use on-demand pricing

### Production
- Reserved instances for EC2 (40% savings)
- RDS reserved instances (40% savings)
- ElastiCache reserved nodes (40% savings)
- S3 lifecycle policies for old recordings

### Estimated Monthly Costs (Production)
- EC2 t3.medium (reserved): $20
- RDS db.t3.small (reserved): $15
- ElastiCache t3.micro (reserved): $10
- ALB: $20
- Data transfer: $20
- **Total Infrastructure: ~$85/month**

Add service costs:
- Deepgram: $390/month (750 hour-long calls)
- AWS Bedrock: $500/month
- **Total: ~$975/month**

---

## Next Steps After Deployment

1. **Test thoroughly** - Make 10+ test calls
2. **Monitor metrics** - Watch CPU, memory, errors
3. **Set up alerts** - CloudWatch alarms for errors
4. **Document procedures** - Runbooks for common issues
5. **Train team** - How to monitor and troubleshoot
6. **Plan scaling** - When to add more servers

---

Ready to deploy! 🚀
