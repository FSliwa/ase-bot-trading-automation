#!/usr/bin/env python3
"""
ASE-Bot Authentication System
System logowania i rejestracji użytkowników z bazą danych SQLite
"""

import sqlite3
import hashlib
import secrets
import json
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import jwt
import os
from typing import Optional, Dict, Tuple

class AuthenticationSystem:
    def __init__(self, db_path='trading.db'):
        self.db_path = db_path
        self.secret_key = os.environ.get('JWT_SECRET', 'dev-secret-key-change-in-production')
        self.init_database()
    
    def init_database(self):
        """Initialize or update database schema"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create enhanced users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users_auth (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    email_verified BOOLEAN DEFAULT 0,
                    verification_token TEXT,
                    reset_token TEXT,
                    reset_token_expires TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    is_admin BOOLEAN DEFAULT 0,
                    two_factor_secret TEXT,
                    two_factor_enabled BOOLEAN DEFAULT 0,
                    login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    profile_data TEXT
                )
            ''')
            
            # Create sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    FOREIGN KEY (user_id) REFERENCES users_auth(id)
                )
            ''')
            
            # Create audit log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS auth_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    action TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    success BOOLEAN,
                    error_message TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """Hash password with salt"""
        if not salt:
            salt = secrets.token_hex(32)
        
        password_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # iterations
        )
        
        return password_hash.hex(), salt
    
    def verify_password(self, password: str, password_hash: str, salt: str) -> bool:
        """Verify password against hash"""
        test_hash, _ = self.hash_password(password, salt)
        return test_hash == password_hash
    
    def validate_email(self, email: str) -> bool:
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    def validate_password(self, password: str) -> Tuple[bool, str]:
        """Validate password strength"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        if not re.search(r'[A-Z]', password):
            return False, "Password must contain at least one uppercase letter"
        if not re.search(r'[a-z]', password):
            return False, "Password must contain at least one lowercase letter"
        if not re.search(r'[0-9]', password):
            return False, "Password must contain at least one number"
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            return False, "Password must contain at least one special character"
        return True, "Password is strong"
    
    def register_user(self, username: str, email: str, password: str) -> Dict:
        """Register new user"""
        try:
            # Validate input
            if not self.validate_email(email):
                return {"success": False, "error": "Invalid email format"}
            
            is_valid, msg = self.validate_password(password)
            if not is_valid:
                return {"success": False, "error": msg}
            
            # Hash password
            password_hash, salt = self.hash_password(password)
            verification_token = secrets.token_urlsafe(32)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Check if user exists
                cursor.execute(
                    "SELECT id FROM users_auth WHERE email = ? OR username = ?",
                    (email, username)
                )
                if cursor.fetchone():
                    return {"success": False, "error": "User already exists"}
                
                # Insert new user
                cursor.execute('''
                    INSERT INTO users_auth (
                        username, email, password_hash, salt, 
                        verification_token, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (username, email, password_hash, salt, 
                     verification_token, datetime.now()))
                
                user_id = cursor.lastrowid
                conn.commit()
                
                # Log registration
                self.log_auth_action(user_id, "register", True)
                
                return {
                    "success": True,
                    "user_id": user_id,
                    "verification_token": verification_token,
                    "message": "User registered successfully"
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def login(self, email: str, password: str, ip_address: str = None, 
              user_agent: str = None) -> Dict:
        """Login user"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Get user
                cursor.execute('''
                    SELECT id, username, password_hash, salt, email_verified,
                           is_active, login_attempts, locked_until
                    FROM users_auth WHERE email = ?
                ''', (email,))
                
                user = cursor.fetchone()
                
                if not user:
                    self.log_auth_action(None, "login", False, ip_address, 
                                        user_agent, "User not found")
                    return {"success": False, "error": "Invalid credentials"}
                
                user_id, username, password_hash, salt, email_verified, \
                is_active, login_attempts, locked_until = user
                
                # Check if account is locked
                if locked_until:
                    locked_time = datetime.fromisoformat(locked_until)
                    if locked_time > datetime.now():
                        return {"success": False, 
                               "error": f"Account locked until {locked_until}"}
                
                # Check if active
                if not is_active:
                    return {"success": False, "error": "Account is disabled"}
                
                # Verify password
                if not self.verify_password(password, password_hash, salt):
                    # Increment login attempts
                    login_attempts += 1
                    if login_attempts >= 5:
                        # Lock account for 30 minutes
                        locked_until = datetime.now() + timedelta(minutes=30)
                        cursor.execute('''
                            UPDATE users_auth 
                            SET login_attempts = ?, locked_until = ?
                            WHERE id = ?
                        ''', (login_attempts, locked_until, user_id))
                    else:
                        cursor.execute('''
                            UPDATE users_auth SET login_attempts = ?
                            WHERE id = ?
                        ''', (login_attempts, user_id))
                    
                    conn.commit()
                    self.log_auth_action(user_id, "login", False, ip_address,
                                        user_agent, "Invalid password")
                    return {"success": False, "error": "Invalid credentials"}
                
                # Check if email is verified
                if not email_verified:
                    return {"success": False, "error": "Please verify your email first"}
                
                # Generate JWT token
                token_data = {
                    "user_id": user_id,
                    "username": username,
                    "email": email,
                    "exp": datetime.now() + timedelta(hours=24),
                    "iat": datetime.now()
                }
                
                token = jwt.encode(token_data, self.secret_key, algorithm="HS256")
                
                # Create session
                session_token = secrets.token_urlsafe(32)
                expires_at = datetime.now() + timedelta(hours=24)
                
                cursor.execute('''
                    INSERT INTO user_sessions (
                        user_id, token, ip_address, user_agent, expires_at
                    ) VALUES (?, ?, ?, ?, ?)
                ''', (user_id, session_token, ip_address, user_agent, expires_at))
                
                # Update last login and reset attempts
                cursor.execute('''
                    UPDATE users_auth 
                    SET last_login = ?, login_attempts = 0, locked_until = NULL
                    WHERE id = ?
                ''', (datetime.now(), user_id))
                
                conn.commit()
                
                self.log_auth_action(user_id, "login", True, ip_address, user_agent)
                
                return {
                    "success": True,
                    "user_id": user_id,
                    "username": username,
                    "token": token,
                    "session_token": session_token,
                    "expires_at": expires_at.isoformat()
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def verify_email(self, token: str) -> Dict:
        """Verify user email with token"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT id FROM users_auth 
                    WHERE verification_token = ? AND email_verified = 0
                ''', (token,))
                
                user = cursor.fetchone()
                
                if not user:
                    return {"success": False, "error": "Invalid or expired token"}
                
                cursor.execute('''
                    UPDATE users_auth 
                    SET email_verified = 1, verification_token = NULL
                    WHERE id = ?
                ''', (user[0],))
                
                conn.commit()
                
                self.log_auth_action(user[0], "email_verification", True)
                
                return {"success": True, "message": "Email verified successfully"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def logout(self, session_token: str) -> Dict:
        """Logout user by invalidating session"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    UPDATE user_sessions 
                    SET is_active = 0 
                    WHERE token = ?
                ''', (session_token,))
                
                if cursor.rowcount > 0:
                    conn.commit()
                    return {"success": True, "message": "Logged out successfully"}
                else:
                    return {"success": False, "error": "Invalid session"}
                    
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_user_by_session(self, session_token: str) -> Optional[Dict]:
        """Get user info from session token"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                cursor.execute('''
                    SELECT u.id, u.username, u.email, u.is_admin, u.created_at
                    FROM users_auth u
                    JOIN user_sessions s ON u.id = s.user_id
                    WHERE s.token = ? AND s.is_active = 1 
                    AND s.expires_at > ?
                ''', (session_token, datetime.now()))
                
                user = cursor.fetchone()
                
                if user:
                    return {
                        "id": user[0],
                        "username": user[1],
                        "email": user[2],
                        "is_admin": bool(user[3]),
                        "created_at": user[4]
                    }
                return None
                
        except Exception as e:
            print(f"Error getting user by session: {e}")
            return None
    
    def log_auth_action(self, user_id: Optional[int], action: str, 
                       success: bool, ip_address: str = None,
                       user_agent: str = None, error_message: str = None):
        """Log authentication action"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO auth_audit_log (
                        user_id, action, ip_address, user_agent, 
                        success, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, action, ip_address, user_agent, 
                     success, error_message))
                conn.commit()
        except Exception as e:
            print(f"Error logging auth action: {e}")


class EmailService:
    def __init__(self):
        # Email configuration (use environment variables in production)
        self.smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_username = os.environ.get('SMTP_USERNAME', 'noreply@ase-bot.live')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', 'your-password')
        self.from_email = os.environ.get('FROM_EMAIL', 'ASE-Bot <noreply@ase-bot.live>')
        
    def send_verification_email(self, to_email: str, username: str, 
                               verification_token: str) -> bool:
        """Send email verification"""
        try:
            verification_link = f"http://localhost:4000/verify?token={verification_token}"
            
            subject = "Verify your ASE-Bot account"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                          padding: 30px; text-align: center; color: white;">
                    <h1>Welcome to ASE-Bot!</h1>
                </div>
                <div style="padding: 30px; background: #f7f7f7;">
                    <h2>Hello {username},</h2>
                    <p>Thank you for registering with ASE-Bot Trading Platform.</p>
                    <p>Please verify your email address by clicking the button below:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{verification_link}" 
                           style="background: #667eea; color: white; padding: 15px 30px;
                                  text-decoration: none; border-radius: 5px; display: inline-block;">
                            Verify Email Address
                        </a>
                    </div>
                    <p>Or copy this link to your browser:</p>
                    <p style="background: white; padding: 10px; word-break: break-all;">
                        {verification_link}
                    </p>
                    <p>This link will expire in 24 hours.</p>
                    <hr>
                    <p style="color: #666; font-size: 12px;">
                        If you didn't create an account, please ignore this email.
                    </p>
                </div>
            </body>
            </html>
            """
            
            return self.send_email(to_email, subject, html_body)
            
        except Exception as e:
            print(f"Error sending verification email: {e}")
            return False
    
    def send_password_reset_email(self, to_email: str, username: str, 
                                 reset_token: str) -> bool:
        """Send password reset email"""
        try:
            reset_link = f"http://localhost:4000/reset-password?token={reset_token}"
            
            subject = "Reset your ASE-Bot password"
            
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <div style="background: #ff6b6b; padding: 30px; text-align: center; color: white;">
                    <h1>Password Reset Request</h1>
                </div>
                <div style="padding: 30px; background: #f7f7f7;">
                    <h2>Hello {username},</h2>
                    <p>We received a request to reset your password.</p>
                    <p>Click the button below to set a new password:</p>
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{reset_link}" 
                           style="background: #ff6b6b; color: white; padding: 15px 30px;
                                  text-decoration: none; border-radius: 5px; display: inline-block;">
                            Reset Password
                        </a>
                    </div>
                    <p>This link will expire in 1 hour.</p>
                    <p>If you didn't request this, please ignore this email.</p>
                </div>
            </body>
            </html>
            """
            
            return self.send_email(to_email, subject, html_body)
            
        except Exception as e:
            print(f"Error sending password reset email: {e}")
            return False
    
    def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """Send email using SMTP"""
        try:
            # Create message
            message = MIMEMultipart("alternative")
            message["From"] = self.from_email
            message["To"] = to_email
            message["Subject"] = subject
            
            # Create HTML part
            html_part = MIMEText(html_body, "html")
            message.attach(html_part)
            
            # For testing - save email to file instead of sending
            if os.environ.get('EMAIL_MODE') == 'test':
                filename = f"email_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
                with open(filename, 'w') as f:
                    f.write(f"To: {to_email}\nSubject: {subject}\n\n{html_body}")
                print(f"📧 Test email saved to {filename}")
                return True
            
            # Send email via SMTP
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls(context=context)
                server.login(self.smtp_username, self.smtp_password)
                server.send_message(message)
            
            print(f"✅ Email sent to {to_email}")
            return True
            
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            return False
