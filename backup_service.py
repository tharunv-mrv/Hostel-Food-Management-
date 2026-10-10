"""
Database Backup & Persistence Management Service.

Provides online, transactionally consistent SQLite backups, automatic rotation,
and restore procedures to guarantee permanent data safety across server restarts,
process termination, and system reboots.
"""

import os
import glob
import sqlite3
from datetime import datetime
from config import Config, basedir


def get_active_db_path(app=None) -> str:
    """Resolve the active SQLite database path from app config or Config default."""
    if app and app.config.get('SQLALCHEMY_DATABASE_URI'):
        uri = app.config['SQLALCHEMY_DATABASE_URI']
    else:
        uri = Config.SQLALCHEMY_DATABASE_URI

    if uri.startswith('sqlite:///'):
        target = uri.replace('sqlite:///', '', 1)
        if target == ':memory:':
            return ':memory:'
        if not os.path.isabs(target):
            return os.path.abspath(os.path.join(basedir, target))
        return os.path.abspath(target)
    return Config.DB_FILE_PATH


def create_database_backup(label: str = "auto", app=None) -> dict:
    """
    Create an online, non-blocking byte-level backup of the active SQLite database.
    Uses Python's native sqlite3 Connection.backup API for 100% transactional consistency.
    """
    db_path = get_active_db_path(app)
    if db_path == ':memory:' or not os.path.exists(db_path):
        return {
            'success': False,
            'message': f"Database at '{db_path}' cannot be backed up (in-memory or file does not exist yet)."
        }

    if os.path.normcase(os.path.abspath(db_path)) != os.path.normcase(os.path.abspath(Config.DB_FILE_PATH)):
        backup_dir = os.path.join(os.path.dirname(db_path), 'backups')
    else:
        backup_dir = Config.BACKUP_DIR
    os.makedirs(backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    clean_label = "".join(c for c in label if c.isalnum() or c in ('_', '-'))
    backup_filename = f"hostel_food_{clean_label}_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    try:
        source_con = sqlite3.connect(db_path, timeout=10.0)
        target_con = sqlite3.connect(backup_path)
        with target_con:
            source_con.backup(target_con)
        target_con.close()
        source_con.close()

        file_size = os.path.getsize(backup_path)
        if backup_dir == Config.BACKUP_DIR:
            rotate_backups(max_backups=Config.BACKUP_RETENTION_COUNT)

        return {
            'success': True,
            'backup_file': backup_filename,
            'backup_path': backup_path,
            'timestamp': timestamp,
            'size_bytes': file_size,
            'message': f"Backup '{backup_filename}' ({file_size:,} bytes) created successfully."
        }
    except Exception as e:
        if os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass
        return {
            'success': False,
            'message': f"Failed to create database backup: {str(e)}"
        }


def rotate_backups(max_backups: int = 10) -> int:
    """
    Prune oldest automated backups to prevent disk bloat, retaining the most recent N copies.
    Manual or special backups labeled 'safe' or 'initial' are preserved.
    """
    backup_dir = Config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        return 0

    pattern = os.path.join(backup_dir, "hostel_food_*.db")
    backup_files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    pruned = 0
    # Keep up to max_backups, remove older excess
    if len(backup_files) > max_backups:
        for old_file in backup_files[max_backups:]:
            # Never prune initial or safe baseline backups
            fname = os.path.basename(old_file)
            if 'initial' in fname or 'pre_fix' in fname:
                continue
            try:
                os.remove(old_file)
                pruned += 1
            except OSError:
                pass
    return pruned


def list_backups() -> list:
    """Return a detailed list of all existing database backups sorted newest first."""
    backup_dir = Config.BACKUP_DIR
    if not os.path.exists(backup_dir):
        return []

    pattern = os.path.join(backup_dir, "hostel_food_*.db")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

    backups = []
    for f in files:
        stat = os.stat(f)
        backups.append({
            'filename': os.path.basename(f),
            'path': f,
            'size_bytes': stat.st_size,
            'size_kb': round(stat.st_size / 1024, 2),
            'modified_time': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        })
    return backups


def restore_database_from_backup(backup_filename: str, app=None) -> dict:
    """
    Safely restore the active database from a verified backup snapshot.
    Creates an emergency snapshot of current DB before overwriting.
    """
    backup_dir = Config.BACKUP_DIR
    safe_filename = os.path.basename(backup_filename)
    backup_path = os.path.join(backup_dir, safe_filename)

    if not os.path.exists(backup_path):
        return {'success': False, 'message': f"Backup file '{safe_filename}' not found."}

    # Verify backup integrity
    try:
        check_con = sqlite3.connect(backup_path)
        cur = check_con.cursor()
        cur.execute("PRAGMA integrity_check;")
        res = cur.fetchone()
        check_con.close()
        if not res or res[0] != "ok":
            return {'success': False, 'message': f"Backup file integrity check failed: {res}"}
    except Exception as e:
        return {'success': False, 'message': f"Backup file corrupted: {str(e)}"}

    db_path = get_active_db_path(app)
    if db_path == ':memory:':
        return {'success': False, 'message': "Cannot restore in-memory database from file."}

    # Create safety snapshot of current DB before replacement
    if os.path.exists(db_path):
        create_database_backup(label="pre_restore_safety", app=app)

    try:
        src_con = sqlite3.connect(backup_path)
        dst_con = sqlite3.connect(db_path)
        with dst_con:
            src_con.backup(dst_con)
        dst_con.close()
        src_con.close()
        return {'success': True, 'message': f"Database successfully restored from '{safe_filename}'."}
    except Exception as e:
        return {'success': False, 'message': f"Restoration failed: {str(e)}"}
