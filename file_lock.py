"""
跨平台文件锁模块
支持 Windows 和 Unix/Linux/Mac 系统
"""

import os
import sys
import time
import random
import logging

# 判断操作系统类型
is_windows = sys.platform.startswith('win')

# Windows 系统使用 msvcrt 模块
if is_windows:
    import msvcrt
    import tempfile
    
    def acquire_lock(lock_file, timeout=60, delay=0.1):
        """
        在 Windows 上获取文件锁
        
        参数:
        lock_file (str): 锁文件路径
        timeout (int): 超时时间（秒）
        delay (float): 重试延迟（秒）
        
        返回:
        锁文件句柄或 None（如果获取锁失败）
        """
        lock_dir = os.path.dirname(lock_file)
        if lock_dir and not os.path.exists(lock_dir):
            os.makedirs(lock_dir)
            
        end_time = time.time() + timeout
        lock_file_fd = None
        
        while time.time() < end_time:
            try:
                # 以写入模式打开文件
                lock_file_fd = open(lock_file, 'w+')
                
                # 尝试锁定文件
                msvcrt.locking(lock_file_fd.fileno(), msvcrt.LK_NBLCK, 1)
                
                # 写入进程ID
                lock_file_fd.write(str(os.getpid()))
                lock_file_fd.flush()
                
                # 返回锁文件句柄
                return lock_file_fd
            except (IOError, OSError):
                # 如果有异常，关闭文件并重试
                if lock_file_fd:
                    try:
                        lock_file_fd.close()
                    except:
                        pass
                lock_file_fd = None
                
                # 随机延迟，避免多个进程同时重试
                time.sleep(delay + random.random() * 0.05)
        
        # 超时后返回 None
        logging.warning(f"获取文件锁超时: {lock_file}")
        return None

    def release_lock(lock_fd):
        """
        在 Windows 上释放文件锁
        
        参数:
        lock_fd: 锁文件句柄
        """
        if lock_fd:
            try:
                # 获取文件描述符并解锁
                fd = lock_fd.fileno()
                lock_fd.seek(0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                lock_fd.close()
                
                # 尝试删除锁文件
                try:
                    os.remove(lock_fd.name)
                except (IOError, OSError):
                    pass
            except (IOError, OSError):
                pass

# Unix/Linux/Mac 系统使用 fcntl 模块
else:
    import fcntl
    
    def acquire_lock(lock_file, timeout=60, delay=0.1):
        """
        在 Unix/Linux/Mac 上获取文件锁
        
        参数:
        lock_file (str): 锁文件路径
        timeout (int): 超时时间（秒）
        delay (float): 重试延迟（秒）
        
        返回:
        锁文件句柄或 None（如果获取锁失败）
        """
        lock_dir = os.path.dirname(lock_file)
        if lock_dir and not os.path.exists(lock_dir):
            os.makedirs(lock_dir)
            
        end_time = time.time() + timeout
        lock_file_fd = None
        
        while time.time() < end_time:
            try:
                # 以写入模式打开文件
                lock_file_fd = open(lock_file, 'w+')
                
                # 尝试获取非阻塞的排他锁
                fcntl.flock(lock_file_fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                
                # 写入进程ID
                lock_file_fd.write(str(os.getpid()))
                lock_file_fd.flush()
                
                # 返回锁文件句柄
                return lock_file_fd
            except (IOError, OSError):
                # 如果有异常，关闭文件并重试
                if lock_file_fd:
                    try:
                        lock_file_fd.close()
                    except:
                        pass
                lock_file_fd = None
                
                # 随机延迟，避免多个进程同时重试
                time.sleep(delay + random.random() * 0.05)
        
        # 超时后返回 None
        logging.warning(f"获取文件锁超时: {lock_file}")
        return None

    def release_lock(lock_fd):
        """
        在 Unix/Linux/Mac 上释放文件锁
        
        参数:
        lock_fd: 锁文件句柄
        """
        if lock_fd:
            try:
                # 解锁并关闭文件
                fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
                lock_fd.close()
                
                # 尝试删除锁文件
                try:
                    os.remove(lock_fd.name)
                except (IOError, OSError):
                    pass
            except (IOError, OSError):
                pass


class FileLock:
    """
    跨平台文件锁类，支持上下文管理器
    """
    def __init__(self, lock_file, timeout=60, delay=0.1):
        self.lock_file = lock_file
        self.timeout = timeout
        self.delay = delay
        self.lock_fd = None
    
    def acquire(self):
        """获取锁"""
        self.lock_fd = acquire_lock(self.lock_file, self.timeout, self.delay)
        return self.lock_fd is not None
    
    def release(self):
        """释放锁"""
        release_lock(self.lock_fd)
        self.lock_fd = None
    
    def __enter__(self):
        """上下文管理器入口"""
        if not self.acquire():
            raise TimeoutError(f"无法在指定时间内获取文件锁: {self.lock_file}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.release()
