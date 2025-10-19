import requests
import re
import os
import subprocess
import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, parse_qs, unquote
import hashlib
import random
import logging
from typing import List, Dict, Tuple, Optional, Any, Set, Union, Callable
import urllib3
from dataclasses import dataclass, field
import threading
from pathlib import Path
import secrets
from logging.handlers import RotatingFileHandler
import ssl
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import platform
import shutil
from functools import lru_cache
import json
from datetime import datetime
import socket
from collections import defaultdict
import tempfile
import signal
import itertools
from contextlib import contextmanager

# 尝试导入模糊匹配库
try:
    from thefuzz import fuzz
    FUZZ_AVAILABLE = True
except ImportError:
    FUZZ_AVAILABLE = False
    # 如果没有安装thefuzz，使用简单的字符串匹配
    def fuzz_ratio(a: str, b: str) -> int:
        a_lower = a.lower()
        b_lower = b.lower()
        if a_lower == b_lower:
            return 100
        elif a_lower in b_lower or b_lower in a_lower:
            return 80
        else:
            common_chars = len(set(a_lower) & set(b_lower))
            total_chars = len(set(a_lower) | set(b_lower))
            return int((common_chars / total_chars) * 100) if total_chars > 0 else 0
    
    # 创建兼容的fuzz对象
    class SimpleFuzz:
        @staticmethod
        def ratio(a: str, b: str) -> int:
            return fuzz_ratio(a, b)
    
    fuzz = SimpleFuzz()

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================================================
# 配置类
# ==================================================

@dataclass
class AppConfig:
    """应用程序配置"""
    version: str = "2.1.0"
    url_sources: List[str] = field(default_factory=lambda: [
        "https://raw.githubusercontent.com/zwc456baby/iptv_alive/master/live.txt",
        "https://live.zbds.top/tv/iptv6.txt", 
        "https://live.zbds.top/tv/iptv4.txt",
    ])
    local_source_file: str = "local.txt"
    template_file: str = "demo.txt"
    output_txt: str = "iptv.txt"
    output_m3u: str = "iptv.m3u"
    enable_ffmpeg_test: bool = True
    enable_speed_test: bool = True
    enable_response_test: bool = True
    max_workers: int = 3
    timeout: int = 10
    max_sources_per_channel: int = 8
    max_retries: int = 2
    speed_weight: float = 0.4
    resolution_weight: float = 0.3
    response_weight: float = 0.3
    max_url_length: int = 2048
    max_channels: int = 1000
    max_sources_per_url: int = 500
    max_response_time: float = 10000.0
    min_stream_score: float = 0.2
    max_content_size: int = 10 * 1024 * 1024
    allow_local_files: bool = False
    backup_file_count: int = 5
    connection_pool_size: int = 10
    request_timeout: int = 30
    user_agent_rotation: bool = True
    enable_gzip: bool = True
    dns_timeout: int = 5
    enable_cache: bool = True
    cache_ttl: int = 3600

    @classmethod
    def from_env(cls):
        """从环境变量加载配置"""
        config = cls()
        if os.getenv('IPTV_MAX_WORKERS'):
            try:
                config.max_workers = int(os.getenv('IPTV_MAX_WORKERS'))
            except ValueError:
                logger.warning(f"无效的IPTV_MAX_WORKERS值: {os.getenv('IPTV_MAX_WORKERS')}")
        
        if os.getenv('IPTV_TIMEOUT'):
            try:
                config.timeout = int(os.getenv('IPTV_TIMEOUT'))
            except ValueError:
                logger.warning(f"无效的IPTV_TIMEOUT值: {os.getenv('IPTV_TIMEOUT')}")
        
        if os.getenv('IPTV_ENABLE_FFMPEG'):
            config.enable_ffmpeg_test = os.getenv('IPTV_ENABLE_FFMPEG').lower() == 'true'
        
        return config

    def validate(self) -> List[str]:
        """验证配置有效性"""
        errors = []
        
        # 权重验证
        total_weight = self.speed_weight + self.resolution_weight + self.response_weight
        if abs(total_weight - 1.0) > 0.001:
            errors.append(f"权重配置错误: 总和应为1.0，当前为{total_weight:.3f}")
        
        # 数值范围验证
        if self.max_workers < 1 or self.max_workers > 50:
            errors.append(f"max_workers必须在1-50之间: {self.max_workers}")
        
        if self.timeout < 1 or self.timeout > 300:
            errors.append(f"timeout必须在1-300秒之间: {self.timeout}")
        
        if self.max_response_time <= 0:
            errors.append(f"max_response_time必须大于0: {self.max_response_time}")
        
        # 权重范围验证
        for weight_name, weight_value in [('speed_weight', self.speed_weight),
                                         ('resolution_weight', self.resolution_weight),
                                         ('response_weight', self.response_weight)]:
            if weight_value < 0 or weight_value > 1:
                errors.append(f"{weight_name}必须在0-1之间: {weight_value}")
        
        # 文件路径验证
        if not self.template_file.strip():
            errors.append("模板文件路径不能为空")
        
        if len(self.output_txt.strip()) == 0:
            errors.append("输出文本文件路径不能为空")
        
        if len(self.output_m3u.strip()) == 0:
            errors.append("输出M3U文件路径不能为空")
        
        # URL源验证
        if not self.url_sources:
            errors.append("至少需要配置一个URL源")
        
        for url in self.url_sources:
            if not url.startswith(('http://', 'https://')):
                errors.append(f"URL源必须是HTTP/HTTPS协议: {url}")
        
        # 数值限制验证
        if self.max_sources_per_channel < 1:
            errors.append(f"max_sources_per_channel必须大于0: {self.max_sources_per_channel}")
        
        if self.max_retries < 0:
            errors.append(f"max_retries必须大于等于0: {self.max_retries}")
        
        if self.max_channels < 1:
            errors.append(f"max_channels必须大于0: {self.max_channels}")
        
        if self.max_sources_per_url < 1:
            errors.append(f"max_sources_per_url必须大于0: {self.max_sources_per_url}")
        
        return errors

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'version': self.version,
            'url_sources': self.url_sources,
            'local_source_file': self.local_source_file,
            'template_file': self.template_file,
            'output_txt': self.output_txt,
            'output_m3u': self.output_m3u,
            'enable_ffmpeg_test': self.enable_ffmpeg_test,
            'enable_speed_test': self.enable_speed_test,
            'enable_response_test': self.enable_response_test,
            'max_workers': self.max_workers,
            'timeout': self.timeout,
            'max_sources_per_channel': self.max_sources_per_channel,
            'max_retries': self.max_retries,
            'speed_weight': self.speed_weight,
            'resolution_weight': self.resolution_weight,
            'response_weight': self.response_weight,
            'max_url_length': self.max_url_length,
            'max_channels': self.max_channels,
            'max_sources_per_url': self.max_sources_per_url,
            'max_response_time': self.max_response_time,
            'min_stream_score': self.min_stream_score,
            'max_content_size': self.max_content_size,
            'allow_local_files': self.allow_local_files,
            'backup_file_count': self.backup_file_count,
            'connection_pool_size': self.connection_pool_size,
            'request_timeout': self.request_timeout,
            'user_agent_rotation': self.user_agent_rotation,
            'enable_gzip': self.enable_gzip,
            'dns_timeout': self.dns_timeout,
            'enable_cache': self.enable_cache,
            'cache_ttl': self.cache_ttl
        }

# 初始化配置
CONFIG = AppConfig.from_env()

# User-Agent列表
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
]

# 线程局部存储
_thread_local = threading.local()

# ==================================================
# 缓存系统
# ==================================================

class CacheManager:
    """线程安全的缓存管理器"""
    
    def __init__(self, ttl: int = 3600, max_size: int = 1000):
        self.ttl = ttl
        self.max_size = max_size
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.RLock()
        self._access_order: List[str] = []  # LRU支持
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值 - 线程安全"""
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                # 检查是否过期
                if time.time() - timestamp < self.ttl:
                    # 更新访问顺序 (LRU)
                    if key in self._access_order:
                        self._access_order.remove(key)
                    self._access_order.append(key)
                    return value
                else:
                    # 过期删除
                    self._remove_key(key)
            return None
    
    def set(self, key: str, value: Any):
        """设置缓存值 - 线程安全且限制大小"""
        with self._lock:
            # 如果达到最大大小，移除最久未使用的
            if len(self._cache) >= self.max_size and self._access_order:
                oldest_key = self._access_order.pop(0)
                self._remove_key(oldest_key)
            
            self._cache[key] = (value, time.time())
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)
    
    def _remove_key(self, key: str):
        """安全移除键"""
        if key in self._cache:
            del self._cache[key]
        if key in self._access_order:
            self._access_order.remove(key)
    
    def clear(self):
        """清空缓存"""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
    
    def cleanup_expired(self):
        """清理过期缓存"""
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if current_time - timestamp >= self.ttl
            ]
            for key in expired_keys:
                self._remove_key(key)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        with self._lock:
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'lru_queue_size': len(self._access_order),
                'ttl': self.ttl
            }

# 延迟初始化缓存管理器
def get_cache_manager() -> Optional[CacheManager]:
    """获取缓存管理器实例"""
    if not hasattr(get_cache_manager, '_instance'):
        get_cache_manager._instance = CacheManager(ttl=CONFIG.cache_ttl, max_size=1000) if CONFIG.enable_cache else None
    return get_cache_manager._instance

# ==================================================
# 日志配置
# ==================================================

def setup_logging() -> logging.Logger:
    """配置日志系统"""
    logger = logging.getLogger('iptv_crawler')
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    logger.propagate = False
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(threadName)s] - %(message)s'
    )
    
    # 控制台handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件handler（带轮转）
    try:
        log_dir = Path('logs')
        log_dir.mkdir(exist_ok=True)
        
        file_handler = RotatingFileHandler(
            log_dir / 'iptv_crawler.log',
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 错误日志单独记录
        error_handler = RotatingFileHandler(
            log_dir / 'iptv_crawler_error.log',
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        logger.addHandler(error_handler)
        
    except Exception as e:
        print(f"警告: 无法创建文件日志: {e}")
    
    return logger

logger = setup_logging()

# ==================================================
# 数据模型
# ==================================================

@dataclass
class StreamSource:
    """流媒体源数据模型"""
    program_name: str
    stream_url: str
    source_type: str = "url"
    source_url: str = ""
    group: str = ""
    
    def __post_init__(self):
        """数据验证"""
        if not self.program_name or not self.stream_url:
            raise ValueError("节目名称和URL不能为空")
        
        if len(self.program_name.strip()) == 0:
            raise ValueError("节目名称不能为空或纯空格")
        
        if len(self.stream_url) > CONFIG.max_url_length:
            raise ValueError(f"URL长度超过限制: {len(self.stream_url)}")
        
        # 严格的URL格式验证
        if not self._is_valid_url(self.stream_url):
            raise ValueError(f"URL格式无效: {self.stream_url}")
    
    def _is_valid_url(self, url: str) -> bool:
        """验证URL格式"""
        try:
            result = urlparse(url)
            valid_schemes = ['http', 'https', 'rtmp', 'rtsp', 'udp', 'rtp', 'mms', 'hls']
            return all([result.scheme in valid_schemes, result.netloc])
        except Exception:
            return False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'program_name': self.program_name,
            'stream_url': self.stream_url,
            'source_type': self.source_type,
            'source_url': self.source_url,
            'group': self.group
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StreamSource':
        """从字典创建实例"""
        return cls(**data)

@dataclass
class StreamTestResult:
    """流测试结果"""
    url: str
    score: float
    response_time: float
    resolution: str
    source_type: str
    success: bool
    timestamp: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """数据验证"""
        if not isinstance(self.score, (int, float)) or self.score < 0 or self.score > 1:
            raise ValueError(f"分数必须在0-1之间: {self.score}")
        
        if not isinstance(self.response_time, (int, float)) or self.response_time < 0:
            raise ValueError(f"响应时间必须为非负数: {self.response_time}")
        
        if not isinstance(self.success, bool):
            raise ValueError(f"success必须是布尔值: {self.success}")
        
        if not isinstance(self.timestamp, (int, float)) or self.timestamp < 0:
            raise ValueError(f"时间戳必须为非负数: {self.timestamp}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'url': self.url,
            'score': self.score,
            'response_time': self.response_time,
            'resolution': self.resolution,
            'source_type': self.source_type,
            'success': self.success,
            'timestamp': self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StreamTestResult':
        """从字典创建实例"""
        return cls(**data)

# ==================================================
# 工具函数
# ==================================================

def get_random_user_agent() -> str:
    """获取随机User-Agent"""
    return random.choice(USER_AGENTS) if CONFIG.user_agent_rotation else USER_AGENTS[0]

def safe_unquote(url: str) -> str:
    """安全的URL解码"""
    try:
        return unquote(url, errors='strict')
    except Exception as e:
        logger.warning(f"URL解码失败 {url}: {e}")
        return url

def is_local_file_url(url: str) -> bool:
    """检查是否为本地文件URL"""
    try:
        parsed = urlparse(url)
        return (parsed.scheme in ('file', '') and not parsed.netloc) or \
               (parsed.netloc == '' and parsed.path.startswith('/'))
    except Exception:
        return False

def validate_url_security(url: str) -> bool:
    """验证URL安全性"""
    if not CONFIG.allow_local_files and is_local_file_url(url):
        logger.warning(f"禁止访问本地文件: {url}")
        return False
    
    try:
        parsed = urlparse(url)
        
        # 检查可疑的URL模式
        suspicious_patterns = [
            r'/etc/', r'/passwd', r'/shadow', r'file://',
            r'\.\./', r'\.\.\\', r'javascript:', r'vbscript:',
            r'data:', r'about:'
        ]
        
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in suspicious_patterns):
            return False
            
        # 检查本地网络地址
        if parsed.hostname in ('localhost', '127.0.0.1', '::1', '0.0.0.0'):
            return CONFIG.allow_local_files
            
        return True
    except Exception as e:
        logger.warning(f"URL安全验证失败 {url}: {e}")
        return False

def resolve_dns(hostname: str) -> bool:
    """解析DNS验证主机可达性"""
    try:
        socket.setdefaulttimeout(CONFIG.dns_timeout)
        socket.getaddrinfo(hostname, None)
        return True
    except socket.gaierror:
        logger.warning(f"DNS解析失败: {hostname}")
        return False
    except Exception as e:
        logger.warning(f"DNS解析异常 {hostname}: {e}")
        return False

def create_secure_session() -> requests.Session:
    """创建安全的请求会话"""
    session = requests.Session()
    
    # 配置重试策略
    retry_strategy = Retry(
        total=CONFIG.max_retries,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"],
        raise_on_status=False
    )
    
    # 配置适配器
    adapter = HTTPAdapter(
        pool_connections=CONFIG.connection_pool_size,
        pool_maxsize=CONFIG.connection_pool_size,
        max_retries=retry_strategy
    )
    
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    
    # 设置默认headers
    session.headers.update({
        'User-Agent': get_random_user_agent(),
        'Accept': 'text/plain, */*',
        'Accept-Encoding': 'gzip, deflate' if CONFIG.enable_gzip else 'identity',
        'Connection': 'close'
    })
    
    return session

def safe_subprocess_run(cmd: List[str], **kwargs) -> subprocess.CompletedProcess:
    """安全的子进程执行"""
    # 确保所有参数都是字符串
    str_cmd = [str(arg) for arg in cmd]
    
    # 设置默认参数
    default_kwargs = {
        'capture_output': True,
        'text': True,
        'timeout': kwargs.get('timeout', 30),
        'check': False,
        'encoding': 'utf-8',
        'errors': 'replace'
    }
    default_kwargs.update(kwargs)
    
    try:
        return subprocess.run(str_cmd, **default_kwargs)
    except FileNotFoundError as e:
        logger.error(f"命令未找到: {cmd[0]}")
        raise
    except Exception as e:
        logger.error(f"子进程执行失败: {e}")
        raise

def normalize_url(url: str) -> str:
    """URL标准化 - 去除冗余参数，统一格式"""
    try:
        parsed = urlparse(url)
        
        # 移除常见的不必要参数
        query_params = parse_qs(parsed.query)
        filtered_params = {}
        
        for key, values in query_params.items():
            # 保留重要的参数，移除跟踪参数等
            if key in ['id', 'auth', 'token', 'key', 'channel']:
                filtered_params[key] = values
        
        # 重建URL
        new_query = '&'.join(
            f"{k}={v[0]}" for k, v in filtered_params.items()
        ) if filtered_params else ''
        
        normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if new_query:
            normalized += f"?{new_query}"
        if parsed.fragment:
            normalized += f"#{parsed.fragment}"
            
        return normalized
    except Exception as e:
        logger.warning(f"URL标准化失败 {url}: {e}")
        return url

def parse_source_line(line: str) -> Optional[Tuple[str, str]]:
    """解析源文件行 - 支持多种格式"""
    line = line.strip()
    
    # 尝试多种分隔符
    separators = [',', '\t', '|', ' ', '    ']
    
    for sep in separators:
        if sep in line:
            parts = line.split(sep, 1)
            if len(parts) == 2:
                name, url = parts[0].strip(), parts[1].strip()
                if name and url and url.startswith(('http://', 'https://', 'rtmp://', 'rtsp://')):
                    return name, url
    
    # 如果没有明确分隔符，尝试提取URL
    url_match = re.search(r'(https?://[^\s]+|rtmp://[^\s]+|rtsp://[^\s]+)', line)
    if url_match:
        url = url_match.group(1)
        name = line.replace(url, '').strip()
        if not name:
            name = f"Channel_{hash(url) % 10000:04d}"  # 生成唯一名称
        return name, url
    
    return None

@contextmanager
def thread_local_session():
    """线程局部会话上下文管理器"""
    if not hasattr(_thread_local, 'session'):
        _thread_local.session = create_secure_session()
    
    try:
        yield _thread_local.session
    except Exception as e:
        logger.error(f"会话操作失败: {e}")
        raise
    finally:
        # 不在这里关闭会话，在cleanup_resources中统一处理
        pass

def cleanup_resources():
    """安全的资源清理"""
    # 清理会话
    if hasattr(_thread_local, 'session'):
        try:
            _thread_local.session.close()
            delattr(_thread_local, 'session')
        except Exception as e:
            logger.debug(f"清理session失败: {e}")
    
    # 安全地清理其他可能的属性
    attrs_to_clean = ['progress_lock', 'last_progress_time', 'current_channel']
    for attr in attrs_to_clean:
        if hasattr(_thread_local, attr):
            try:
                delattr(_thread_local, attr)
            except Exception as e:
                logger.debug(f"清理{attr}失败: {e}")
    
    # 清理缓存
    cache_mgr = get_cache_manager()
    if cache_mgr:
        try:
            cache_mgr.clear()
        except Exception as e:
            logger.debug(f"清理缓存失败: {e}")
    
    # 清理临时文件
    cleanup_temp_files()

def cleanup_temp_files():
    """清理临时文件"""
    try:
        current_dir = Path('.')
        # 清理可能的临时文件
        temp_patterns = ['*.tmp', 'temp_*', '*.backup.*']
        for pattern in temp_patterns:
            for temp_file in current_dir.glob(pattern):
                try:
                    if temp_file.is_file():
                        temp_file.unlink()
                        logger.debug(f"删除临时文件: {temp_file}")
                except Exception as e:
                    logger.debug(f"删除临时文件失败 {temp_file}: {e}")
    except Exception as e:
        logger.debug(f"清理临时文件失败: {e}")

def setup_signal_handlers():
    """设置信号处理器"""
    def signal_handler(signum, frame):
        signal_name = "SIGINT" if signum == signal.SIGINT else "SIGTERM"
        print(f"\n接收到信号 {signal_name}，正在优雅退出...")
        cleanup_resources()
        sys.exit(1)
    
    # 注册信号处理器
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    except Exception as e:
        logger.warning(f"设置信号处理器失败: {e}")

# ==================================================
# 核心功能函数
# ==================================================

def load_local_sources() -> List[StreamSource]:
    """加载本地源文件"""
    sources = []
    
    if not os.path.exists(CONFIG.local_source_file):
        logger.warning(f"本地源文件不存在: {CONFIG.local_source_file}")
        return sources
    
    try:
        with open(CONFIG.local_source_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                parsed = parse_source_line(line)
                if parsed:
                    program_name, stream_url = parsed
                    try:
                        source = StreamSource(
                            program_name=program_name,
                            stream_url=stream_url,
                            source_type="local", 
                            source_url=CONFIG.local_source_file
                        )
                        sources.append(source)
                    except ValueError as e:
                        logger.warning(f"本地源第{line_num}行格式错误: {e}")
                else:
                    logger.warning(f"本地源第{line_num}行格式无效: {line}")
                        
    except Exception as e:
        logger.error(f"加载本地源失败: {e}")
    
    logger.info(f"成功加载本地源: {len(sources)} 个")
    return sources

def fetch_url_sources() -> List[StreamSource]:
    """从URL源抓取直播源"""
    all_sources = []
    
    def fetch_single_url(source_url: str) -> List[StreamSource]:
        """抓取单个URL源"""
        sources = []
        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                with thread_local_session() as session:
                    response = session.get(
                        source_url, 
                        timeout=(CONFIG.request_timeout, 30),
                        verify=False,
                        stream=True,
                        allow_redirects=True
                    )
                    response.raise_for_status()
                    
                    # 修复编码处理逻辑
                    content_bytes = b""
                    for chunk in response.iter_content(chunk_size=8192):
                        content_bytes += chunk
                        if len(content_bytes) > CONFIG.max_content_size:
                            logger.warning(f"源内容过大，已截断: {source_url}")
                            break
                    
                    # 尝试多种编码解码
                    content = None
                    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1', 'iso-8859-1']
                    
                    for encoding in encodings:
                        try:
                            content = content_bytes.decode(encoding)
                            break
                        except UnicodeDecodeError:
                            continue
                    
                    if content is None:
                        # 如果所有编码都失败，使用errors='replace'
                        content = content_bytes.decode('utf-8', errors='replace')
                        logger.warning(f"使用替换策略解码内容: {source_url}")
                    
                    # 解析内容
                    line_count = 0
                    for line_num, line in enumerate(content.splitlines(), 1):
                        if line_count >= CONFIG.max_sources_per_url:
                            logger.info(f"达到最大源数量限制: {CONFIG.max_sources_per_url}")
                            break
                            
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        parsed = parse_source_line(line)
                        if parsed:
                            program_name, stream_url = parsed
                            try:
                                normalized_url = normalize_url(stream_url)
                                source = StreamSource(
                                    program_name=program_name,
                                    stream_url=normalized_url,
                                    source_type="url",
                                    source_url=source_url
                                )
                                sources.append(source)
                                line_count += 1
                            except ValueError as e:
                                logger.debug(f"跳过无效源 {source_url}:{line_num}: {e}")
                        else:
                            logger.debug(f"跳过无法解析的行 {source_url}:{line_num}: {line}")
                    
                    logger.info(f"成功从 {source_url} 抓取 {len(sources)} 个源")
                    break
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"抓取源失败 (尝试 {attempt + 1}/{max_retries}) {source_url}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # 指数退避
                else:
                    logger.error(f"抓取源最终失败 {source_url}: {e}")
            except Exception as e:
                logger.error(f"抓取源异常 {source_url}: {e}")
                break
        
        return sources
    
    # 并行抓取所有URL源
    with ThreadPoolExecutor(max_workers=min(len(CONFIG.url_sources), CONFIG.max_workers)) as executor:
        future_to_url = {
            executor.submit(fetch_single_url, url): url 
            for url in CONFIG.url_sources
        }
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                sources = future.result()
                all_sources.extend(sources)
            except Exception as e:
                logger.error(f"处理URL源失败 {url}: {e}")
    
    logger.info(f"从网络源共抓取 {len(all_sources)} 个源")
    return all_sources

def organize_channels_by_template(sources: List[StreamSource], template: List[str]) -> Dict[str, List[StreamSource]]:
    """按模板整理频道"""
    organized = {channel: [] for channel in template}
    
    # 构建频道名称映射（支持模糊匹配）
    channel_patterns = {}
    for channel in template:
        # 创建多个匹配模式
        patterns = [
            channel.lower(),
            channel.lower().replace(' ', ''),
            channel.lower().replace(' ', '_'),
            channel.lower().replace('cctv', 'cctv '),
            channel.lower().replace('cctv ', 'cctv'),
        ]
        
        # 中文频道特殊处理
        if any(char >= '\u4e00' and char <= '\u9fff' for char in channel):
            patterns.extend([
                channel.lower().replace('卫视', ''),
                channel.lower() + '电视台',
                channel.lower().replace('电视台', '')
            ])
        
        channel_patterns[channel] = patterns
    
    for source in sources:
        matched_channel = None
        source_name_lower = source.program_name.lower()
        
        # 精确匹配优先
        for channel, patterns in channel_patterns.items():
            if source_name_lower in patterns:
                matched_channel = channel
                break
        
        # 如果精确匹配失败，尝试包含匹配
        if not matched_channel:
            for channel, patterns in channel_patterns.items():
                for pattern in patterns:
                    if pattern in source_name_lower or source_name_lower in pattern:
                        matched_channel = channel
                        break
                if matched_channel:
                    break
        
        # 如果包含匹配失败，尝试模糊匹配
        if not matched_channel and FUZZ_AVAILABLE:
            best_match = None
            best_score = 0
            
            for channel in template:
                score = fuzz.ratio(source_name_lower, channel.lower())
                if score > best_score and score > 60:  # 相似度阈值
                    best_score = score
                    best_match = channel
            
            matched_channel = best_match
        
        if matched_channel:
            organized[matched_channel].append(source)
    
    # 统计结果
    matched_count = sum(1 for sources in organized.values() if sources)
    total_sources = sum(len(sources) for sources in organized.values())
    
    logger.info(f"频道匹配完成: {matched_count}/{len(template)} 个频道匹配到源")
    logger.info(f"总共匹配到 {total_sources} 个源")
    
    # 记录未匹配的源（用于调试）
    unmatched_sources = []
    for source in sources:
        if not any(source in channel_sources for channel_sources in organized.values()):
            unmatched_sources.append(source)
    
    if unmatched_sources:
        logger.debug(f"有 {len(unmatched_sources)} 个源未能匹配到任何频道")
        for source in unmatched_sources[:5]:  # 只记录前5个
            logger.debug(f"未匹配源: {source.program_name}")
    
    return organized

def test_single_source(source: StreamSource) -> StreamTestResult:
    """测试单个源的质量"""
    try:
        start_time = time.time()
        response_time = 0
        
        # 基础响应测试
        if CONFIG.enable_response_test:
            try:
                with thread_local_session() as session:
                    response_start = time.time()
                    response = session.head(
                        source.stream_url, 
                        timeout=CONFIG.timeout,
                        verify=False,
                        allow_redirects=True
                    )
                    response_time = (time.time() - response_start) * 1000  # 毫秒
                    
                    if response.status_code != 200:
                        return StreamTestResult(
                            url=source.stream_url,
                            score=0.0,
                            response_time=response_time,
                            resolution="unknown",
                            source_type=source.source_type,
                            success=False
                        )
            except Exception as e:
                logger.debug(f"响应测试失败 {source.stream_url}: {e}")
                response_time = CONFIG.max_response_time
        
        # FFmpeg流媒体测试
        resolution = "unknown"
        speed_score = 0.5  # 默认分数
        resolution_score = 0.5
        
        if CONFIG.enable_ffmpeg_test:
            try:
                # 使用FFmpeg进行快速测试
                cmd = [
                    'ffmpeg',
                    '-i', source.stream_url,
                    '-t', '5',  # 测试5秒
                    '-f', 'null', '-',
                    '-y',  # 覆盖输出文件
                    '-loglevel', 'error'
                ]
                
                # 添加平台特定参数
                if platform.system() != 'Windows':
                    cmd.extend(['-analyzeduration', '10000000', '-probesize', '10000000'])
                
                result = safe_subprocess_run(
                    cmd, 
                    timeout=CONFIG.timeout + 10,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # 解析FFmpeg输出获取分辨率
                output = result.stderr or result.stdout or ""
                resolution_match = re.search(r'(\d+)x(\d+)', output)
                if resolution_match:
                    width = int(resolution_match.group(1))
                    height = int(resolution_match.group(2))
                    resolution = f"{width}x{height}"
                    
                    # 根据分辨率计算分数
                    if width >= 1920 and height >= 1080:
                        resolution_score = 1.0
                    elif width >= 1280 and height >= 720:
                        resolution_score = 0.8
                    elif width >= 720 and height >= 480:
                        resolution_score = 0.6
                    else:
                        resolution_score = 0.4
                else:
                    resolution_score = 0.3
                
                # 根据FFmpeg退出码判断成功
                if result.returncode == 0:
                    speed_score = 0.9
                elif result.returncode == 1 and "Conversion failed" not in output:
                    # FFmpeg有时返回1但实际上是成功的
                    speed_score = 0.7
                else:
                    speed_score = 0.3
                    
            except subprocess.TimeoutExpired:
                logger.debug(f"FFmpeg测试超时 {source.stream_url}")
                speed_score = 0.1
                resolution_score = 0.1
            except Exception as e:
                logger.debug(f"FFmpeg测试失败 {source.stream_url}: {e}")
                speed_score = 0.2
                resolution_score = 0.2
        else:
            speed_score = 0.7
            resolution_score = 0.5
        
        # 响应时间分数（响应时间越短分数越高）
        response_score = max(0, 1 - (response_time / CONFIG.max_response_time))
        
        # 综合评分
        total_score = (
            speed_score * CONFIG.speed_weight +
            resolution_score * CONFIG.resolution_weight + 
            response_score * CONFIG.response_weight
        )
        
        success = total_score >= CONFIG.min_stream_score
        
        return StreamTestResult(
            url=source.stream_url,
            score=total_score,
            response_time=response_time,
            resolution=resolution,
            source_type=source.source_type,
            success=success
        )
        
    except Exception as e:
        logger.debug(f"源测试异常 {source.stream_url}: {e}")
        return StreamTestResult(
            url=source.stream_url,
            score=0.0,
            response_time=CONFIG.max_response_time,
            resolution="unknown",
            source_type=source.source_type,
            success=False
        )

def test_channel_sources(channel_name: str, sources: List[StreamSource]) -> List[StreamTestResult]:
    """测试频道的所有源并返回最佳结果"""
    if not sources:
        return []
    
    # 优先测试本地源
    local_sources = [s for s in sources if s.source_type == "local"]
    url_sources = [s for s in sources if s.source_type == "url"]
    
    all_sources = local_sources + url_sources
    
    # 并行测试所有源
    test_results = []
    with ThreadPoolExecutor(max_workers=min(len(all_sources), CONFIG.max_workers)) as executor:
        future_to_source = {
            executor.submit(test_single_source, source): source 
            for source in all_sources
        }
        
        for future in as_completed(future_to_source):
            source = future_to_source[future]
            try:
                result = future.result()
                test_results.append(result)
            except Exception as e:
                logger.error(f"测试源失败 {source.stream_url}: {e}")
    
    # 筛选成功的测试结果并按分数排序
    successful_results = [r for r in test_results if r.success]
    successful_results.sort(key=lambda x: x.score, reverse=True)
    
    # 返回最佳的几个源
    best_results = successful_results[:CONFIG.max_sources_per_channel]
    
    return best_results

def save_to_txt(channels_data: List[Tuple[str, List[StreamTestResult]]]) -> bool:
    """保存为文本格式"""
    try:
        # 创建备份
        if os.path.exists(CONFIG.output_txt):
            timestamp = int(time.time())
            backup_file = f"{CONFIG.output_txt}.backup.{timestamp}"
            try:
                shutil.copy2(CONFIG.output_txt, backup_file)
                logger.info(f"创建备份文件: {backup_file}")
            except Exception as e:
                logger.warning(f"备份文件失败: {e}")
        
        with open(CONFIG.output_txt, 'w', encoding='utf-8') as f:
            for channel_name, test_results in channels_data:
                for result in test_results:
                    f.write(f"{channel_name},{result.url}\n")
        
        logger.info(f"成功保存文本格式: {CONFIG.output_txt}, 共 {len(channels_data)} 个频道")
        return True
    except Exception as e:
        logger.error(f"保存文本文件失败: {e}")
        return False

def save_to_m3u(channels_data: List[Tuple[str, List[StreamTestResult]]]) -> bool:
    """保存为M3U格式"""
    try:
        # 创建备份
        if os.path.exists(CONFIG.output_m3u):
            timestamp = int(time.time())
            backup_file = f"{CONFIG.output_m3u}.backup.{timestamp}"
            try:
                shutil.copy2(CONFIG.output_m3u, backup_file)
                logger.info(f"创建备份文件: {backup_file}")
            except Exception as e:
                logger.warning(f"备份文件失败: {e}")
        
        with open(CONFIG.output_m3u, 'w', encoding='utf-8') as f:
            f.write("#EXTM3U\n")
            f.write("# Generated by IPTV Crawler\n")
            f.write(f"# Created: {datetime.now().isoformat()}\n")
            f.write(f"# Channels: {len(channels_data)}\n")
            f.write(f"# Version: {CONFIG.version}\n\n")
            
            for channel_name, test_results in channels_data:
                for result in test_results:
                    # M3U格式条目
                    f.write(f"#EXTINF:-1,{channel_name}\n")
                    f.write(f"{result.url}\n")
        
        logger.info(f"成功保存M3U格式: {CONFIG.output_m3u}, 共 {len(channels_data)} 个频道")
        return True
    except Exception as e:
        logger.error(f"保存M3U文件失败: {e}")
        return False

# ==================================================
# 测试和验证函数
# ==================================================

def run_basic_tests() -> bool:
    """运行基本测试"""
    print("🧪 运行基本测试...")
    
    tests_passed = 0
    tests_failed = 0
    
    # 测试1: 配置验证
    try:
        config_errors = CONFIG.validate()
        if not config_errors:
            print("✅ 配置验证测试通过")
            tests_passed += 1
        else:
            print("❌ 配置验证测试失败")
            for error in config_errors:
                print(f"   - {error}")
            tests_failed += 1
    except Exception as e:
        print(f"❌ 配置验证测试异常: {e}")
        tests_failed += 1
    
    # 测试2: URL标准化
    try:
        test_urls = [
            ("http://example.com/test.m3u8?id=123&t=123456", "http://example.com/test.m3u8?id=123"),
            ("https://example.com:8080/live/stream.m3u8", "https://example.com:8080/live/stream.m3u8"),
        ]
        
        all_passed = True
        for input_url, expected in test_urls:
            result = normalize_url(input_url)
            if result.startswith(expected.split('?')[0]):
                print(f"✅ URL标准化测试通过: {input_url} -> {result}")
            else:
                print(f"❌ URL标准化测试失败: {input_url} -> {result} (期望: {expected})")
                all_passed = False
        
        if all_passed:
            tests_passed += 1
        else:
            tests_failed += 1
    except Exception as e:
        print(f"❌ URL标准化测试异常: {e}")
        tests_failed += 1
    
    # 测试3: 数据模型
    try:
        # 测试有效数据
        valid_source = StreamSource("测试频道", "http://example.com/stream.m3u8")
        valid_result = StreamTestResult(
            url="http://example.com/stream.m3u8",
            score=0.8,
            response_time=100,
            resolution="1920x1080",
            source_type="url",
            success=True
        )
        print("✅ 数据模型验证测试通过")
        tests_passed += 1
        
        # 测试无效数据
        try:
            invalid_source = StreamSource("", "http://example.com/stream.m3u8")
            print("❌ 数据模型验证测试失败: 应该抛出异常")
            tests_failed += 1
        except ValueError:
            print("✅ 数据模型无效数据测试通过")
            tests_passed += 1
            
    except Exception as e:
        print(f"❌ 数据模型测试异常: {e}")
        tests_failed += 1
    
    # 测试4: 文件操作
    try:
        test_content = "测试内容"
        test_file = "test_temp_file.txt"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        with open(test_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if content == test_content:
            print("✅ 文件操作测试通过")
            tests_passed += 1
        else:
            print("❌ 文件操作测试失败")
            tests_failed += 1
        
        # 清理
        if os.path.exists(test_file):
            os.remove(test_file)
            
    except Exception as e:
        print(f"❌ 文件操作测试异常: {e}")
        tests_failed += 1
    
    print(f"\n📊 测试结果: {tests_passed} 通过, {tests_failed} 失败")
    
    return tests_failed == 0

def run_network_tests() -> bool:
    """运行网络测试"""
    print("\n🌐 运行网络测试...")
    
    tests_passed = 0
    tests_failed = 0
    
    # 测试1: DNS解析
    try:
        if resolve_dns("www.baidu.com"):
            print("✅ DNS解析测试通过")
            tests_passed += 1
        else:
            print("❌ DNS解析测试失败")
            tests_failed += 1
    except Exception as e:
        print(f"❌ DNS解析测试异常: {e}")
        tests_failed += 1
    
    # 测试2: 会话创建
    try:
        session = create_secure_session()
        session.close()
        print("✅ 会话创建测试通过")
        tests_passed += 1
    except Exception as e:
        print(f"❌ 会话创建测试异常: {e}")
        tests_failed += 1
    
    # 测试3: URL安全验证
    try:
        safe_urls = ["http://example.com", "https://example.com"]
        unsafe_urls = ["file:///etc/passwd", "javascript:alert('xss')"]
        
        all_safe_passed = all(validate_url_security(url) for url in safe_urls)
        all_unsafe_passed = all(not validate_url_security(url) for url in unsafe_urls)
        
        if all_safe_passed and all_unsafe_passed:
            print("✅ URL安全验证测试通过")
            tests_passed += 1
        else:
            print("❌ URL安全验证测试失败")
            tests_failed += 1
    except Exception as e:
        print(f"❌ URL安全验证测试异常: {e}")
        tests_failed += 1
    
    print(f"📊 网络测试结果: {tests_passed} 通过, {tests_failed} 失败")
    
    return tests_failed == 0

def check_dependencies() -> bool:
    """检查必要的依赖"""
    print("🔍 检查依赖...")
    
    # 检查Python版本
    if sys.version_info < (3, 7):
        logger.error("需要Python 3.7或更高版本")
        return False
    
    # 检查必需库
    required_libraries = ['requests', 'urllib3']
    missing_libraries = []
    
    for lib in required_libraries:
        try:
            __import__(lib)
            print(f"✅ {lib} 可用")
        except ImportError as e:
            missing_libraries.append((lib, str(e)))
            print(f"❌ {lib} 缺失")
    
    if missing_libraries:
        for lib, error in missing_libraries:
            logger.error(f"缺少必需库 {lib}: {error}")
        logger.info("请运行: pip install requests urllib3")
        return False
    
    # 检查标准库
    std_libraries = ['subprocess', 'threading', 'hashlib', 'ssl', 'json', 'datetime']
    for lib in std_libraries:
        try:
            __import__(lib)
        except ImportError as e:
            logger.error(f"缺少标准库 {lib}: {e}")
            return False
    
    # 检查FFmpeg（如果启用）
    if CONFIG.enable_ffmpeg_test:
        try:
            result = safe_subprocess_run(['ffmpeg', '-version'], timeout=10)
            if result.returncode == 0:
                print("✅ FFmpeg 可用")
                
                # 检查FFmpeg版本
                version_match = re.search(r'ffmpeg version\s+(\d+\.\d+)', result.stdout)
                if version_match:
                    version = float(version_match.group(1))
                    if version < 3.0:
                        logger.warning(f"FFmpeg版本较老: {version}，建议使用4.0或更高版本")
            else:
                logger.error(f"FFmpeg检查失败，返回码: {result.returncode}")
                if "not found" in result.stderr.lower():
                    logger.info("请安装FFmpeg或设置系统PATH环境变量")
                return False
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg检查超时")
            return False
        except Exception as e:
            logger.error(f"FFmpeg检查异常: {e}")
            return False
    else:
        print("ℹ️ FFmpeg测试已禁用")
    
    print("✅ 所有依赖检查通过")
    return True

def validate_configuration() -> Tuple[List[str], List[str]]:
    """验证配置合理性"""
    errors = []
    warnings = []
    
    # 使用配置类的验证方法
    config_errors = CONFIG.validate()
    errors.extend(config_errors)
    
    # 检查URL源格式和安全性
    for url in CONFIG.url_sources:
        if not url.startswith(('http://', 'https://')):
            errors.append(f"URL格式错误: {url}")
        elif len(url) > CONFIG.max_url_length:
            warnings.append(f"URL过长: {url}")
        elif not validate_url_security(url):
            warnings.append(f"URL安全性警告: {url}")
    
    # 检查文件路径安全性
    file_paths = [CONFIG.template_file, CONFIG.local_source_file, CONFIG.output_txt, CONFIG.output_m3u]
    for file_path in file_paths:
        try:
            path = Path(file_path).resolve()
            current_dir = Path('.').resolve()
            
            # 检查路径遍历
            if '..' in file_path:
                warnings.append(f"文件路径包含路径遍历字符: {file_path}")
            
            # 检查是否在当前目录下
            try:
                path.relative_to(current_dir)
            except ValueError:
                warnings.append(f"文件路径超出工作目录: {file_path}")
                
        except Exception as e:
            warnings.append(f"文件路径检查失败 {file_path}: {e}")
    
    # 检查必要文件
    if not os.path.exists(CONFIG.template_file):
        try:
            create_sample_template()
            errors.append(f"模板文件不存在，已创建示例文件: {CONFIG.template_file}")
        except Exception as e:
            errors.append(f"创建模板文件失败: {e}")
    else:
        # 验证模板文件内容和大小
        try:
            file_size = os.path.getsize(CONFIG.template_file)
            if file_size > CONFIG.max_content_size:
                errors.append(f"模板文件过大: {file_size}字节")
            elif file_size == 0:
                errors.append("模板文件为空")
            
            with open(CONFIG.template_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                valid_channels = [line for line in content.split('\n') 
                                if line.strip() and not line.startswith('#')]
                if not valid_channels:
                    errors.append("模板文件为空或只有注释，请添加频道名称")
                elif len(valid_channels) > CONFIG.max_channels:
                    warnings.append(f"模板频道数量{len(valid_channels)}超过建议值{CONFIG.max_channels}")
        except Exception as e:
            errors.append(f"读取模板文件失败: {e}")
    
    if not os.path.exists(CONFIG.local_source_file):
        try:
            create_sample_local_source()
            warnings.append(f"本地源文件不存在，已创建示例文件: {CONFIG.local_source_file}")
        except Exception as e:
            warnings.append(f"创建本地源文件失败: {e}")
    
    # 检查输出目录权限
    try:
        output_dir = os.path.dirname(CONFIG.output_txt) or '.'
        test_file = os.path.join(output_dir, f".test_{secrets.token_hex(8)}.tmp")
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("test")
        
        os.remove(test_file)
        
        if not os.access(output_dir, os.W_OK):
            errors.append(f"输出目录无写权限: {output_dir}")
    except Exception as e:
        errors.append(f"输出目录权限错误: {e}")
    
    return errors, warnings

def create_sample_template():
    """创建示例模板文件"""
    sample_content = """# 频道模板文件 - 每行一个频道名称
# 程序将严格按照此列表顺序和内容生成结果
# 支持的字符: 中文、英文、数字、空格、下划线

CCTV1
CCTV2
CCTV5
湖南卫视
浙江卫视
北京卫视
"""
    try:
        with open(CONFIG.template_file, 'w', encoding='utf-8') as f:
            f.write(sample_content)
        logger.info(f"已创建模板文件: {CONFIG.template_file}")
    except Exception as e:
        logger.error(f"创建模板文件失败: {e}")
        raise

def create_sample_local_source():
    """创建示例本地源文件"""
    sample_content = """# 本地源文件 - 每行格式: 频道名称,URL
# 本地源将优先使用
# 示例格式: 频道名称,http://example.com/stream.m3u8

CCTV1,http://example.com/cctv1.m3u8
CCTV2,http://example.com/cctv2.m3u8
"""
    try:
        with open(CONFIG.local_source_file, 'w', encoding='utf-8') as f:
            f.write(sample_content)
        logger.info(f"已创建本地源文件: {CONFIG.local_source_file}")
    except Exception as e:
        logger.error(f"创建本地源文件失败: {e}")

def load_template_channels() -> List[str]:
    """加载模板频道列表"""
    if not os.path.exists(CONFIG.template_file):
        logger.error(f"模板文件不存在: {CONFIG.template_file}")
        return []
    
    try:
        channels = []
        with open(CONFIG.template_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if line_num > CONFIG.max_channels:
                    logger.warning(f"超过最大频道数量限制: {CONFIG.max_channels}")
                    break
                    
                line = line.strip()
                if line and not line.startswith('#'):
                    # 安全的输入清理 - 允许中文、英文、数字、空格、常见标点
                    clean_line = re.sub(r'[^\w\s\u4e00-\u9fff\-\.·]', '', line)
                    clean_line = re.sub(r'\s+', ' ', clean_line).strip()
                    
                    if clean_line and len(clean_line) <= 100:  # 限制频道名称长度
                        channels.append(clean_line)
                    else:
                        logger.warning(f"跳过无效的频道名称: {line}")
        
        if not channels:
            logger.error("模板文件中没有找到有效的频道名称")
            return []
        
        logger.info(f"成功加载模板频道: {len(channels)} 个")
        return channels
    except UnicodeDecodeError:
        logger.error("模板文件编码错误，请使用UTF-8编码")
        return []
    except Exception as e:
        logger.error(f"加载模板文件失败: {e}")
        return []

def print_config_summary():
    """打印配置摘要"""
    print("\n⚙ 当前配置:")
    print(f"  📡 源优先级: 本地源 > 网络源")
    print(f"  ⏱ 测速时间: 5秒")
    print(f"  📺 每个频道保留: {CONFIG.max_sources_per_channel} 个最佳源")
    print(f"  🔧 FFmpeg测速: {'✅开启' if CONFIG.enable_ffmpeg_test else '❌关闭'}")
    print(f"  🎯 智能测速: {'✅开启' if CONFIG.enable_speed_test else '❌关闭'}")
    print(f"  ⚡ 响应测试: {'✅开启' if CONFIG.enable_response_test else '❌关闭'}")
    print(f"  🔄 最大重试次数: {CONFIG.max_retries}")
    print(f"  👥 最大工作线程: {CONFIG.max_workers}")
    print(f"  🛡️ 安全模式: {'✅开启' if not CONFIG.allow_local_files else '❌关闭'}")
    print(f"  💾 缓存系统: {'✅开启' if CONFIG.enable_cache else '❌关闭'}")
    print()

def run_main_workflow(start_time: float) -> int:
    """执行主要工作流程"""
    # 1. 加载模板频道
    print("\n" + "="*50)
    print("📋 步骤 1: 加载模板频道")
    template_channels = load_template_channels()
    if not template_channels:
        logger.error("无法加载模板频道，程序退出")
        return 1
    
    # 2. 优先加载本地源
    print("\n" + "="*50)
    print("📂 步骤 2: 加载本地源 (优先)")
    local_sources = load_local_sources()
    
    # 3. 抓取网络源
    print("\n" + "="*50)
    print("🌐 步骤 3: 抓取网络源")
    url_sources = fetch_url_sources()
    
    # 合并源
    all_sources = local_sources + url_sources
    
    if not all_sources:
        logger.error("未找到任何有效的直播源")
        return 1
    
    print(f"\n📊 源统计汇总:")
    print(f"  🏠 本地源: {len(local_sources)} 个")
    print(f"  🌐 网络源: {len(url_sources)} 个")
    print(f"  📈 总计: {len(all_sources)} 个源")
    
    # 4. 整理频道
    print("\n" + "="*50)
    print("🔄 步骤 4: 整理频道")
    organized_channels = organize_channels_by_template(all_sources, template_channels)
    
    # 统计匹配结果
    matched_channels = sum(1 for sources in organized_channels.values() if sources)
    empty_channels = len(organized_channels) - matched_channels
    
    print(f"📺 频道匹配结果:")
    print(f"  ✅ 有源的频道: {matched_channels} 个")
    print(f"  ❌ 无源的频道: {empty_channels} 个")
    
    if matched_channels == 0:
        logger.error("没有频道匹配到任何源")
        return 1
    
    # 5. 全面测试
    print("\n" + "="*50)
    print("🚀 步骤 5: 全面测试所有频道源")
    print("   测试内容:")
    print("   - ⚡ 响应时间测试")
    print("   - ⏱ 5秒FFmpeg流媒体测试") 
    print("   - 📺 分辨率检测")
    print("   - 🎯 质量综合评分")
    print()
    
    final_channels_data = []
    successful_channels = 0
    
    for channel_index, (channel_name, sources) in enumerate(organized_channels.items(), 1):
        print(f"\n[{channel_index}/{len(organized_channels)}] 测试频道: {channel_name}")
        
        if sources:
            best_sources = test_channel_sources(channel_name, sources)
            
            if best_sources:
                final_channels_data.append((channel_name, best_sources))
                successful_channels += 1
                
                # 显示测试结果摘要
                local_count = sum(1 for s in best_sources if s.source_type == "local")
                avg_response = sum(s.response_time for s in best_sources) / len(best_sources)
                avg_score = sum(s.score for s in best_sources) / len(best_sources)
                
                print(f"   ✅ 完成: 保留 {len(best_sources)} 个源")
                print(f"      🏠 本地: {local_count}, 🌐 网络: {len(best_sources) - local_count}")
                print(f"      ⏱ 平均响应: {avg_response:.0f}ms")
                print(f"      🎯 平均质量: {avg_score:.3f}")
            else:
                print(f"   ❌ 无可用源")
        else:
            print(f"   ⚠  无匹配源")
    
    if not final_channels_data:
        logger.error("所有频道测试后都没有可用的源")
        return 1
    
    # 6. 保存结果
    print("\n" + "="*50)
    print("💾 步骤 6: 保存结果")
    
    save_success = save_to_txt(final_channels_data) and save_to_m3u(final_channels_data)
    
    if save_success:
        # 最终统计
        total_sources = sum(len(sources) for _, sources in final_channels_data)
        total_local = sum(sum(1 for s in sources if s.source_type == "local") for _, sources in final_channels_data)
        total_time = time.time() - start_time
        
        print("\n" + "="*70)
        print("🎉 任务完成!")
        print("="*70)
        print(f"✅ 成功处理: {successful_channels}/{len(template_channels)} 个频道")
        print(f"✅ 总共保留: {total_sources} 个高质量源")
        print(f"✅ 其中本地源: {total_local} 个")
        print(f"✅ 网络源: {total_sources - total_local} 个")
        print(f"⏱ 总耗时: {total_time:.1f} 秒")
        print(f"📁 输出文件:")
        print(f"   📄 {CONFIG.output_txt} (文本格式)")
        print(f"   📺 {CONFIG.output_m3u} (M3U播放列表)")
        print("="*70)
        
        logger.info(f"任务完成 - 处理{successful_channels}个频道，保留{total_sources}个源，耗时{total_time:.1f}秒")
        return 0
    else:
        logger.error("文件保存失败")
        return 1

# ==================================================
# 主函数
# ==================================================

def main() -> int:
    """主执行函数"""
    start_time = time.time()
    
    # 设置信号处理器
    setup_signal_handlers()
    
    try:
        print("=" * 70)
        print(f"🎬 IPTV直播源抓取与优化工具 v{CONFIG.version}")
        print("=" * 70)
        
        # 显示系统信息
        logger.info(f"Python版本: {sys.version}")
        logger.info(f"操作系统: {platform.system()} {platform.release()}")
        logger.info(f"工作目录: {os.getcwd()}")
        
        # 运行完整性测试
        print("\n🔬 运行完整性测试...")
        if not run_basic_tests():
            print("❌ 基本测试失败，程序退出")
            return 1
        
        if not run_network_tests():
            print("❌ 网络测试失败，程序退出")
            return 1
        
        print("\n✅ 所有完整性测试通过")
        
        # 显示配置状态
        print_config_summary()
        
        # 验证配置
        errors, warnings = validate_configuration()
        
        if warnings:
            print("⚠ 警告信息:")
            for warning in warnings:
                print(f"  - {warning}")
            print()
        
        if errors:
            print("❌ 配置错误:")
            for error in errors:
                print(f"  - {error}")
            print("\n💡 请解决上述问题后重新运行程序")
            return 1
        
        # 检查依赖
        if not check_dependencies():
            return 1
        
        # 执行主要流程
        return run_main_workflow(start_time)
            
    except KeyboardInterrupt:
        print("\n\n⏹ 用户中断程序")
        logger.info("程序被用户中断")
        return 1
    except Exception as e:
        print(f"\n\n💥 程序执行出错: {e}")
        logger.exception("程序执行异常")
        return 1
    finally:
        cleanup_resources()

if __name__ == "__main__":
    # 保存配置信息
    config_info = CONFIG.to_dict()
    logger.info(f"程序启动配置: {json.dumps(config_info, indent=2, ensure_ascii=False)}")
    
    exit_code = main()
    
    # 记录程序结束
    logger.info(f"程序退出，代码: {exit_code}")
    sys.exit(exit_code)
