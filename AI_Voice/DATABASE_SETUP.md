# Database Setup

## Prerequisites

You need to install and run:
1. **Redis** - For session state management
2. **PostgreSQL** - For persistent call storage

## Installation

### macOS (using Homebrew)

```bash
# Install Redis
brew install redis

# Install PostgreSQL
brew install postgresql@15

# Start services
brew services start redis
brew services start postgresql@15
```

### Linux (Ubuntu/Debian)

```bash
# Install Redis
sudo apt-get update
sudo apt-get install redis-server

# Install PostgreSQL
sudo apt-get install postgresql postgresql-contrib

# Start services
sudo systemctl start redis-server
sudo systemctl start postgresql
```

### Docker (Alternative - Recommended for Development)

```bash
# Start Redis
docker run -d --name ai-voice-redis \
  -p 6379:6379 \
  redis:7-alpine

# Start PostgreSQL
docker run -d --name ai-voice-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=ai_voice \
  -p 5432:5432 \
  postgres:15-alpine
```

## PostgreSQL Database Setup

### Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE ai_voice;

# Exit
\q
```

### Using Docker

```bash
# Create database (if not created automatically)
docker exec -it ai-voice-postgres psql -U postgres -c "CREATE DATABASE ai_voice;"
```

## Verify Setup

### Check Redis

```bash
# Test connection
redis-cli ping
# Should return: PONG

# Check if running
redis-cli info server
```

### Check PostgreSQL

```bash
# Test connection
psql -U postgres -d ai_voice -c "SELECT version();"

# Or with Docker
docker exec -it ai-voice-postgres psql -U postgres -d ai_voice -c "SELECT version();"
```

## Configuration

Update your `.env` file:

```bash
# Redis
REDIS_URL=redis://localhost:6379/0

# PostgreSQL
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/ai_voice
```

## Database Schema

The application will automatically create the `intake_calls` table on startup with the following schema:

```sql
CREATE TABLE intake_calls (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255) UNIQUE NOT NULL,
    phone_number VARCHAR(50),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    duration_seconds INTEGER,
    conversation_history JSONB NOT NULL,
    extracted_fields JSONB,
    salesforce_lead_id VARCHAR(50),
    salesforce_push_status VARCHAR(20) DEFAULT 'pending',
    salesforce_push_error TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

## Troubleshooting

### Redis Connection Errors

```bash
# Check if Redis is running
brew services list | grep redis
# or
sudo systemctl status redis-server

# Restart Redis
brew services restart redis
# or
sudo systemctl restart redis-server
```

### PostgreSQL Connection Errors

```bash
# Check if PostgreSQL is running
brew services list | grep postgresql
# or
sudo systemctl status postgresql

# Check connection with psql
psql -U postgres -d ai_voice

# If authentication fails, you may need to update pg_hba.conf
# Location: /usr/local/var/postgresql@15/pg_hba.conf (macOS)
#           /etc/postgresql/15/main/pg_hba.conf (Linux)
```

### Port Conflicts

If you get "port already in use" errors:

```bash
# Check what's using the port
lsof -i :6379  # Redis
lsof -i :5432  # PostgreSQL

# Kill the process or change the port in .env
```

## Monitoring

### View Call Data

```bash
# Connect to PostgreSQL
psql -U postgres -d ai_voice

# View all calls
SELECT session_id, start_time, duration_seconds, salesforce_push_status 
FROM intake_calls 
ORDER BY start_time DESC 
LIMIT 10;

# View a specific call's conversation
SELECT conversation_history 
FROM intake_calls 
WHERE session_id = 'your-session-id';
```

### View Redis Data

```bash
# Connect to Redis
redis-cli

# List all session keys
KEYS session:*

# View a session
GET session:your-session-id

# Count active sessions
DBSIZE
```

## Backup & Maintenance

### PostgreSQL Backup

```bash
# Backup database
pg_dump -U postgres ai_voice > backup_$(date +%Y%m%d).sql

# Restore from backup
psql -U postgres ai_voice < backup_20241203.sql
```

### Redis Backup

```bash
# Redis automatically saves to disk (RDB)
# Backup file location: /usr/local/var/db/redis/dump.rdb

# Trigger manual save
redis-cli SAVE
```

## Production Considerations

For production deployment:

1. **Use managed services**:
   - AWS ElastiCache (Redis)
   - AWS RDS (PostgreSQL)
   - Or similar cloud providers

2. **Enable authentication**:
   - Set Redis password: `REDIS_PASSWORD=your-secure-password`
   - Use strong PostgreSQL passwords

3. **Enable SSL/TLS**:
   - Update connection URLs to use SSL

4. **Set up backups**:
   - Automated daily backups
   - Point-in-time recovery for PostgreSQL

5. **Monitor resources**:
   - Set up CloudWatch/Datadog monitoring
   - Configure alerts for connection errors
