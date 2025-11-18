"""
PostgreSQL database management for registration and authentication.
Enhanced version with email integration and full PostgreSQL support.
"""

import hashlib
import secrets
import smtplib
import psycopg2
import psycopg2.extras
import os
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PostgreSQLDatabase:
    def __init__(self):
        """Initialize PostgreSQL connection with environment variables."""
        self.connection_params = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'port': os.getenv('DB_PORT', '5432'),
            'database': os.getenv('DB_NAME', 'trading_bot'),
            'user': os.getenv('DB_USER', 'trading_user'),
            'password': os.getenv('DB_PASSWORD', 'trading_password')
        }
        
        self.smtp_config = {
            'server': os.getenv('SMTP_SERVER', ''),
            'port': int(os.getenv('SMTP_PORT', '587')),
            'username': os.getenv('SMTP_USERNAME', ''),
            'password': os.getenv('SMTP_PASSWORD', ''),
            'from_name': os.getenv('SMTP_FROM_NAME', 'Trading Panel'),
            'from_email': os.getenv('SMTP_FROM_EMAIL', 'noreply@tradingpanel.com')
        }
        
        self._init_database()
    
    def _get_connection(self):
        """Get database connection."""
        try:
            conn = psycopg2.connect(**self.connection_params)
            return conn
        except psycopg2.Error as e:
            logger.error(f"Database connection failed: {e}")
            raise
    
    def _init_database(self):
        """Initialize database schema."""
        create_users_table = """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(64) NOT NULL,
            salt VARCHAR(32) NOT NULL,
            first_name VARCHAR(100),
            last_name VARCHAR(100),
            account_type VARCHAR(20) DEFAULT 'free',
            is_active BOOLEAN DEFAULT true,
            email_verified BOOLEAN DEFAULT false,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            oauth_provider VARCHAR(20),
            oauth_id VARCHAR(100),
            settings JSONB DEFAULT '{}',
            email_verification_token VARCHAR(64),
            password_reset_token VARCHAR(64),
            password_reset_expires TIMESTAMP
        );
        """
        
        create_user_sessions_table = """
        CREATE TABLE IF NOT EXISTS user_sessions (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            session_token VARCHAR(64) UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ip_address INET,
            user_agent TEXT
        );
        """
        
        create_audit_log_table = """
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(50) NOT NULL,
            details JSONB,
            ip_address INET,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_users_table)
                    cur.execute(create_user_sessions_table)
                    cur.execute(create_audit_log_table)
                    
                    # Create indexes for better performance
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(session_token);")
                    cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON user_sessions(expires_at);")
                    
                conn.commit()
                logger.info("Database schema initialized successfully")
                
        except psycopg2.Error as e:
            logger.error(f"Database initialization failed: {e}")
            raise
    
    def _send_welcome_email(self, email: str, username: str, first_name: str = '', verification_token: str = None) -> bool:
        """Send welcome email with optional verification."""
        try:
            if not all([self.smtp_config['server'], self.smtp_config['username'], self.smtp_config['password']]):
                logger.info("SMTP not configured - skipping email")
                return False
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.smtp_config['from_name']} <{self.smtp_config['from_email']}>"
            msg['To'] = email
            msg['Subject'] = '🎉 Witaj w Trading Panel!'
            
            name = first_name if first_name else username
            
            # Plain text version
            text_body = f"""
Cześć {name}!

Dziękujemy za rejestrację w Trading Panel! 🎉

Twoje konto zostało pomyślnie utworzone:
• Nazwa użytkownika: {username}
• Email: {email}
• Data rejestracji: {datetime.now().strftime('%d.%m.%Y %H:%M')}

"""
            
            # HTML version
            html_body = f"""
            <html>
              <body style="font-family: Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); margin: 0; padding: 20px;">
                <div style="max-width: 600px; margin: 0 auto; background: white; border-radius: 10px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.1);">
                  
                  <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center;">
                    <h1 style="margin: 0; font-size: 28px;">🎉 Witaj w Trading Panel!</h1>
                  </div>
                  
                  <div style="padding: 30px;">
                    <h2 style="color: #333; margin-top: 0;">Cześć {name}!</h2>
                    
                    <p style="color: #666; font-size: 16px; line-height: 1.6;">
                      Dziękujemy za rejestrację w Trading Panel! Twoje konto zostało pomyślnie utworzone.
                    </p>
                    
                    <div style="background: #f8f9fa; border-radius: 8px; padding: 20px; margin: 20px 0;">
                      <h3 style="color: #333; margin-top: 0;">Szczegóły konta:</h3>
                      <ul style="color: #666; margin: 0;">
                        <li><strong>Nazwa użytkownika:</strong> {username}</li>
                        <li><strong>Email:</strong> {email}</li>
                        <li><strong>Data rejestracji:</strong> {datetime.now().strftime('%d.%m.%Y %H:%M')}</li>
                      </ul>
                    </div>
"""
            
            if verification_token:
                verification_url = f"http://185.70.196.214/verify-email?token={verification_token}"
                text_body += f"\nPotwierdź swój email klikając: {verification_url}\n"
                html_body += f"""
                    <div style="text-align: center; margin: 30px 0;">
                      <a href="{verification_url}" 
                         style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                                color: white; 
                                padding: 12px 30px; 
                                text-decoration: none; 
                                border-radius: 6px; 
                                font-weight: bold;
                                display: inline-block;">
                        Potwierdź Email
                      </a>
                    </div>
"""
            
            text_body += """
Możesz teraz zalogować się i rozpocząć handel:
http://185.70.196.214/login

Zespół Trading Panel
"""
            
            html_body += f"""
                    <div style="text-align: center; margin: 30px 0;">
                      <a href="http://185.70.196.214/login" 
                         style="background: #28a745; 
                                color: white; 
                                padding: 12px 30px; 
                                text-decoration: none; 
                                border-radius: 6px; 
                                font-weight: bold;
                                display: inline-block;">
                        Zaloguj się
                      </a>
                    </div>
                    
                    <hr style="border: none; border-top: 1px solid #eee; margin: 30px 0;">
                    
                    <p style="color: #999; font-size: 14px; text-align: center; margin: 0;">
                      Trading Panel - Profesjonalny system handlowy<br>
                      <a href="http://185.70.196.214" style="color: #667eea;">185.70.196.214</a>
                    </p>
                    
                  </div>
                </div>
              </body>
            </html>
            """
            
            # Attach parts
            msg.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            # Send email
            with smtplib.SMTP(self.smtp_config['server'], self.smtp_config['port']) as server:
                server.starttls()
                server.login(self.smtp_config['username'], self.smtp_config['password'])
                server.send_message(msg)
            
            logger.info(f"Welcome email sent to {email}")
            return True
            
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            return False
    
    def _hash_password(self, password: str, salt: str = None) -> tuple:
        """Hash password with salt."""
        if salt is None:
            salt = secrets.token_hex(16)
        
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return password_hash, salt
    
    def _log_action(self, user_id: int, action: str, details: dict, ip_address: str = None, user_agent: str = None):
        """Log user action for audit purposes."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO audit_log (user_id, action, details, ip_address, user_agent)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (user_id, action, json.dumps(details), ip_address, user_agent))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
    
    def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM users WHERE username = %s", (username.lower(),))
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking user existence: {e}")
            return False
    
    def email_exists(self, email: str) -> bool:
        """Check if email is already registered."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM users WHERE email = %s", (email.lower(),))
                    return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking email existence: {e}")
            return False
    
    def register_user(self, username: str, password: str, email: str, 
                     first_name: str = '', last_name: str = '', account_type: str = 'free',
                     oauth_provider: str = None, oauth_id: str = None,
                     ip_address: str = None, user_agent: str = None) -> Dict[str, Any]:
        """Register a new user."""
        try:
            # Validate input
            if not username or not email:
                return {'success': False, 'error': 'Missing required fields'}
            
            if len(username) < 3:
                return {'success': False, 'error': 'Username must be at least 3 characters'}
            
            # For OAuth users, skip password validation
            if not oauth_provider and len(password) < 8:
                return {'success': False, 'error': 'Password must be at least 8 characters'}
            
            if '@' not in email or '.' not in email:
                return {'success': False, 'error': 'Invalid email address'}
            
            # Check if user already exists
            if self.user_exists(username):
                return {'success': False, 'error': 'Username already exists'}
            
            if self.email_exists(email):
                return {'success': False, 'error': 'Email already registered'}
            
            # Hash password (if not OAuth)
            if oauth_provider:
                password_hash, salt = '', ''
            else:
                password_hash, salt = self._hash_password(password)
            
            # Generate email verification token
            verification_token = secrets.token_urlsafe(32)
            
            # Insert user into database
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (
                            username, email, password_hash, salt, first_name, last_name,
                            account_type, oauth_provider, oauth_id, email_verification_token
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                    """, (
                        username.lower(), email.lower(), password_hash, salt,
                        first_name, last_name, account_type, oauth_provider, oauth_id, verification_token
                    ))
                    
                    user_id = cur.fetchone()[0]
                conn.commit()
            
            # Log registration
            self._log_action(user_id, 'user_registered', {
                'username': username,
                'email': email,
                'account_type': account_type,
                'oauth_provider': oauth_provider
            }, ip_address, user_agent)
            
            # Send welcome email
            email_sent = self._send_welcome_email(email, username, first_name, verification_token)
            
            return {
                'success': True,
                'message': 'User registered successfully',
                'email_sent': email_sent,
                'email_verification_required': True
            }
            
        except psycopg2.IntegrityError as e:
            return {'success': False, 'error': 'User already exists'}
        except Exception as e:
            logger.error(f"Registration failed: {e}")
            return {'success': False, 'error': 'Registration failed'}
    
    def authenticate_user(self, username: str, password: str, ip_address: str = None, user_agent: str = None) -> Dict[str, Any]:
        """Authenticate user with username and password."""
        try:
            if not username or not password:
                return {'success': False, 'error': 'Missing credentials'}
            
            with self._get_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                    cur.execute("""
                        SELECT id, username, password_hash, salt, email, first_name, last_name,
                               account_type, is_active, email_verified, oauth_provider
                        FROM users 
                        WHERE username = %s
                    """, (username.lower(),))
                    
                    user = cur.fetchone()
                    
                    if not user:
                        return {'success': False, 'error': 'Invalid username or password'}
                    
                    # Check if account is active
                    if not user['is_active']:
                        return {'success': False, 'error': 'Account is disabled'}
                    
                    # Check if OAuth user
                    if user['oauth_provider']:
                        return {'success': False, 'error': 'Please use OAuth login'}
                    
                    # Verify password
                    password_hash, _ = self._hash_password(password, user['salt'])
                    
                    if password_hash != user['password_hash']:
                        self._log_action(user['id'], 'login_failed', {'reason': 'invalid_password'}, ip_address, user_agent)
                        return {'success': False, 'error': 'Invalid username or password'}
                    
                    # Update last login
                    cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user['id'],))
                    
                    # Log successful login
                    self._log_action(user['id'], 'login_success', {}, ip_address, user_agent)
                    
                conn.commit()
                
                return {
                    'success': True,
                    'user': {
                        'id': user['id'],
                        'username': user['username'],
                        'email': user['email'],
                        'first_name': user['first_name'],
                        'last_name': user['last_name'],
                        'account_type': user['account_type'],
                        'email_verified': user['email_verified']
                    }
                }
                
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            return {'success': False, 'error': 'Authentication failed'}
    
    def verify_email(self, token: str) -> Dict[str, Any]:
        """Verify user email with token."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users 
                        SET email_verified = true, email_verification_token = NULL
                        WHERE email_verification_token = %s
                        RETURNING id, username, email
                    """, (token,))
                    
                    result = cur.fetchone()
                    if not result:
                        return {'success': False, 'error': 'Invalid or expired token'}
                    
                    user_id, username, email = result
                    self._log_action(user_id, 'email_verified', {})
                    
                conn.commit()
                
                return {'success': True, 'message': 'Email verified successfully'}
                
        except Exception as e:
            logger.error(f"Email verification failed: {e}")
            return {'success': False, 'error': 'Verification failed'}
    
    def get_user_stats(self) -> Dict[str, Any]:
        """Get comprehensive user statistics."""
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # Basic stats
                    cur.execute("SELECT COUNT(*) FROM users")
                    total_users = cur.fetchone()[0]
                    
                    cur.execute("SELECT COUNT(*) FROM users WHERE is_active = true")
                    active_users = cur.fetchone()[0]
                    
                    cur.execute("SELECT COUNT(*) FROM users WHERE email_verified = true")
                    verified_users = cur.fetchone()[0]
                    
                    # Account types
                    cur.execute("""
                        SELECT account_type, COUNT(*) 
                        FROM users 
                        GROUP BY account_type
                    """)
                    account_types = dict(cur.fetchall())
                    
                    # OAuth providers
                    cur.execute("""
                        SELECT oauth_provider, COUNT(*) 
                        FROM users 
                        WHERE oauth_provider IS NOT NULL
                        GROUP BY oauth_provider
                    """)
                    oauth_providers = dict(cur.fetchall())
                    
                    # Recent registrations
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM users 
                        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                    """)
                    recent_registrations = cur.fetchone()[0]
                    
                    return {
                        'total_users': total_users,
                        'active_users': active_users,
                        'verified_users': verified_users,
                        'inactive_users': total_users - active_users,
                        'account_types': account_types,
                        'oauth_providers': oauth_providers,
                        'recent_registrations_7_days': recent_registrations
                    }
                    
        except Exception as e:
            logger.error(f"Failed to get user stats: {e}")
            return {}

    def migrate_from_json(self, json_file: str = 'users.json') -> Dict[str, Any]:
        """Migrate users from JSON file to PostgreSQL."""
        try:
            if not os.path.exists(json_file):
                return {'success': False, 'error': 'JSON file not found'}
            
            with open(json_file, 'r') as f:
                json_users = json.load(f)
            
            migrated_count = 0
            errors = []
            
            for username, user_data in json_users.items():
                try:
                    with self._get_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO users (
                                    username, email, password_hash, salt, first_name, last_name,
                                    account_type, is_active, created_at, last_login, settings
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                                ON CONFLICT (username) DO NOTHING
                            """, (
                                user_data.get('username', username),
                                user_data.get('email', ''),
                                user_data.get('password_hash', ''),
                                user_data.get('salt', ''),
                                user_data.get('first_name', ''),
                                user_data.get('last_name', ''),
                                user_data.get('account_type', 'free'),
                                user_data.get('is_active', True),
                                user_data.get('created_at'),
                                user_data.get('last_login'),
                                json.dumps(user_data.get('settings', {}))
                            ))
                            
                            if cur.rowcount > 0:
                                migrated_count += 1
                        conn.commit()
                        
                except Exception as e:
                    errors.append(f"User {username}: {str(e)}")
            
            return {
                'success': True,
                'migrated_count': migrated_count,
                'total_users': len(json_users),
                'errors': errors
            }
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            return {'success': False, 'error': str(e)}


# Initialize database if run directly
if __name__ == "__main__":
    db = PostgreSQLDatabase()
    print("PostgreSQL database initialized successfully")
    print("User statistics:", db.get_user_stats())
